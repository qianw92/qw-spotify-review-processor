"""Stage 5 — Rank (code only, no model).

Baseline required by the grading contract:
  complaint_count = members of the issue; severity_sum = sum of member severity;
  mean_severity = severity_sum / complaint_count, 6 decimals, decimal half-up;
  priority_score = severity_sum (exactly count x mean, no rounding loss).
Order: priority_score descending, then issue_id ascending. Ranks start at 1.

Can run from the database or purely from saved files (membership.csv + records.jsonl), so a reviewer can
regenerate the ranking without any API key.
"""
import csv
import json
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

COLUMNS = ["rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score"]


def mean_string(total, n):
    return str((Decimal(total) / Decimal(n)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def compute(pairs, severity):
    """pairs: iterable of (issue_id, review_id); severity: {review_id: int} for complaint/cancellation records."""
    members = defaultdict(list)
    seen = set()
    for iid, rid in pairs:
        if (iid, rid) in seen:
            raise ValueError(f"duplicate membership {iid} {rid}")
        seen.add((iid, rid))
        members[iid].append(severity[rid])
    rows = [{"issue_id": iid, "complaint_count": len(v), "severity_sum": sum(v),
             "mean_severity": mean_string(sum(v), len(v)), "priority_score": sum(v)} for iid, v in members.items()]
    rows.sort(key=lambda r: (-r["priority_score"], r["issue_id"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def write(rows, path):
    path = Path(path)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: str(r[k]) for k in COLUMNS})


def from_db(con, run_dir):
    severity = dict(con.execute("""SELECT l.review_id, l.severity FROM labels l JOIN records s USING (review_id)
                                   WHERE s.status='completed' AND l.intent IN ('complaint','cancellation')"""))
    pairs = con.execute("SELECT issue_id, review_id FROM membership").fetchall()
    rows = compute(pairs, severity)
    write(rows, Path(run_dir) / "ranking.csv")
    aggregates(con, rows, Path(run_dir) / "aggregates.csv")
    return {"issues_ranked": len(rows), "top": rows[:3]}


def from_saved(records_path, membership_path, out_path):
    """Offline: rebuild ranking from saved files only. No database, no model, no API key."""
    severity = {}
    opener = __import__("gzip").open if str(records_path).endswith(".gz") else open
    with opener(records_path, "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("status") == "completed" and r["intent"] in ("complaint", "cancellation"):
                severity[r["review_id"]] = r["severity"]
    with open(membership_path, encoding="utf-8") as f:
        pairs = [(r["issue_id"], r["review_id"]) for r in csv.DictReader(f)]
    rows = compute(pairs, severity)
    write(rows, out_path)
    return rows


def aggregates(con, rows, path):
    """Ranking columns plus descriptive context per issue (name, topic, intent split, share of complaints)."""
    total = sum(r["complaint_count"] for r in rows) or 1
    meta = {r[0]: r[1:] for r in con.execute("SELECT issue_id, topic, name, name_source FROM issues")}
    canc = dict(con.execute("""SELECT m.issue_id, COUNT(*) FROM membership m JOIN labels l USING (review_id)
                               WHERE l.intent='cancellation' GROUP BY m.issue_id"""))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS + ["topic", "name", "name_source", "cancellation_count", "share_of_complaints_pct"])
        for r in rows:
            t, name, src = meta.get(r["issue_id"], ("", "", ""))
            w.writerow([r[k] for k in COLUMNS] + [t, name, src, canc.get(r["issue_id"], 0),
                                                  f"{100 * r['complaint_count'] / total:.1f}"])
