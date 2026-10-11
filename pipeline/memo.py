"""Stage 6 — Recommend (role: memo).

The memo model receives ONLY saved aggregates and a bounded evidence pack (never the raw dataset).
Code then checks the answer: cited issue IDs exist, claim values equal the saved ranking exactly, cited
review IDs come from the evidence pack, and every number in the prose appears in the pack. A rejected
answer is regenerated once with the problems listed; after that the stage fails visibly.
"""
import csv
import json
import re
from pathlib import Path

from . import llm

ROOT = Path(__file__).resolve().parent.parent
ISSUES = json.loads((ROOT / "schema" / "issues.json").read_text())
PROMPT_VERSION = "memo-v1"
TOP_ISSUES = 10
EXAMPLES_PER_ISSUE = 3
AREAS = ["access", "usability", "playback", "billing_support"]
METRICS = ["complaint_count", "severity_sum", "mean_severity", "priority_score"]

INSTRUCTIONS = """You advise Spotify's product leadership. Using ONLY the JSON evidence pack, recommend which ONE area
should get next quarter's product effort: access, usability, playback, or billing_support.

Write `memo_markdown` (250-450 words) with these sections: ## Recommendation, ## Evidence, ## Alternatives considered,
## Limitations. Rules:
- Every issue-level number (complaint_count, severity_sum, mean_severity, priority_score) must be backed by an entry in
  `claims` and cited inline as [C1], [C2], ... Copy values exactly as they appear in `top_issues`.
- Other numbers may only be copied from the pack (area totals, shares, counts). Do not compute new numbers.
- Cite issues by issue_id (e.g. ISS-usability-ads) and 2-4 representative review IDs from the pack.
- Compare at least two alternative areas and say why they rank lower.
- Limitations must say: reviews are self-selected and historical, cancellation language is intent not observed churn,
  no revenue data, and state the pending/quarantined counts from `coverage`.
- Do not claim revenue at risk or causal retention effects. Do not invent customer facts."""


def evidence_pack(con, ranking_rows, coverage):
    meta = {r[0]: {"name": r[1], "topic": r[2]} for r in con.execute("SELECT issue_id, name, topic FROM issues")}
    area_of = {t: a for a, ts in ISSUES["areas"].items() if a != "description" for t in ts}
    total = sum(r["complaint_count"] for r in ranking_rows) or 1
    areas = {}
    for r in ranking_rows:
        a = area_of[meta[r["issue_id"]]["topic"]]
        x = areas.setdefault(a, {"complaint_count": 0, "severity_sum": 0, "issues": 0})
        x["complaint_count"] += r["complaint_count"]
        x["severity_sum"] += r["severity_sum"]
        x["issues"] += 1
    sev45 = dict(con.execute("""SELECT i.topic, COUNT(*) FROM membership m JOIN labels l USING (review_id)
                                JOIN issues i USING (issue_id) WHERE l.severity >= 4 GROUP BY i.topic"""))
    canc = dict(con.execute("""SELECT i.topic, COUNT(*) FROM membership m JOIN labels l USING (review_id)
                               JOIN issues i USING (issue_id) WHERE l.intent='cancellation' GROUP BY i.topic"""))
    for a, x in areas.items():
        topics = ISSUES["areas"][a]
        x["share_of_complaints_pct"] = f"{100 * x['complaint_count'] / total:.1f}"
        x["mean_severity"] = f"{x['severity_sum'] / x['complaint_count']:.2f}"
        x["severity_4_or_5_count"] = sum(sev45.get(t, 0) for t in topics)
        x["cancellation_intent_count"] = sum(canc.get(t, 0) for t in topics)
        x["topics"] = topics
    top = []
    for r in ranking_rows[:TOP_ISSUES]:
        ex = con.execute("""SELECT l.review_id, l.severity, l.evidence_quote FROM membership m
                            JOIN labels l USING (review_id) JOIN reviews rv USING (review_id)
                            WHERE m.issue_id=? AND l.cache_source_id IS NULL
                            ORDER BY l.severity DESC, rv.row_index LIMIT ?""", (r["issue_id"], EXAMPLES_PER_ISSUE))
        top.append({**{k: str(r[k]) for k in ("rank", "issue_id", *METRICS)}, **meta[r["issue_id"]],
                    "area": area_of[meta[r["issue_id"]]["topic"]],
                    "examples": [{"review_id": i, "severity": s, "quote": q[:200]} for i, s, q in ex]})
    return {"question": "Where should next quarter's product effort go: access, usability, playback, or billing/support?",
            "period": "Google Play reviews, 17 May 2022 to 15 Nov 2023",
            "coverage": coverage, "total_complaint_and_cancellation_records": total,
            "areas": areas, "top_issues": top,
            "ranking_rule": "priority_score = complaint_count x mean_severity = severity_sum"}


SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["recommended_area", "headline", "memo_markdown", "claims", "cited_review_ids"],
          "properties": {
              "recommended_area": {"type": "string", "enum": AREAS},
              "headline": {"type": "string"},
              "memo_markdown": {"type": "string"},
              "claims": {"type": "array", "items": {
                  "type": "object", "additionalProperties": False,
                  "required": ["claim_id", "issue_id", "metric", "value"],
                  "properties": {"claim_id": {"type": "string"}, "issue_id": {"type": "string"},
                                 "metric": {"type": "string", "enum": METRICS}, "value": {"type": "string"}}}},
              "cited_review_ids": {"type": "array", "items": {"type": "string"}}}}

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def _numbers(text):
    text = re.sub(UUID, " ", text)
    text = re.sub(r"\[C\d+\]|ISS-[a-z_]+-[a-z_]+|\bC\d+\b", " ", text)
    return {n.replace(",", "").rstrip(".") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def make_validator(pack, ranking_rows):
    computed = {r["issue_id"]: {m: str(r[m]) for m in METRICS} for r in ranking_rows}
    pack_ids = {e["review_id"] for t in pack["top_issues"] for e in t["examples"]}
    allowed_numbers = _numbers(json.dumps(pack)) | {str(i) for i in range(0, 21)}

    def validate(out):
        p = []
        memo = out["memo_markdown"]
        ids = [c["claim_id"] for c in out["claims"]]
        if len(ids) != len(set(ids)):
            p.append("duplicate claim_id")
        for c in out["claims"]:
            if c["issue_id"] not in computed:
                p.append(f"{c['claim_id']}: unknown issue {c['issue_id']}")
            elif computed[c["issue_id"]][c["metric"]] != c["value"]:
                p.append(f"{c['claim_id']}: {c['metric']} of {c['issue_id']} is "
                         f"{computed[c['issue_id']][c['metric']]}, not {c['value']}")
            if f"[{c['claim_id']}]" not in memo:
                p.append(f"{c['claim_id']} is never cited in memo_markdown")
        for cited in set(re.findall(r"\[(C\d+)\]", memo)) - set(ids):
            p.append(f"[{cited}] cited but missing from claims")
        for iid in set(re.findall(r"ISS-[a-z_]+-[a-z_]+", memo)) - set(computed):
            p.append(f"memo mentions unknown issue {iid}")
        for rid in (set(out["cited_review_ids"]) | set(re.findall(UUID, memo))) - pack_ids:
            p.append(f"review {rid} is not in the evidence pack")
        for n in sorted(_numbers(memo) - allowed_numbers):
            p.append(f"number {n} does not appear in the evidence pack")
        if not out["claims"]:
            p.append("no claims supplied")
        return p
    return validate


def run(con, run_dir, guard, ranking_rows, coverage, phase="initial"):
    run_dir = Path(run_dir)
    pack = evidence_pack(con, ranking_rows, coverage)
    (run_dir / "memo_evidence_pack.json").write_text(json.dumps(pack, indent=2, ensure_ascii=False))
    sent = sorted({e["review_id"] for t in pack["top_issues"] for e in t["examples"]})
    try:
        out, info = llm.call_json(con=con, run_dir=run_dir, guard=guard, role="memo", prompt_version=PROMPT_VERSION,
                                  instructions=INSTRUCTIONS, payload=pack, schema=SCHEMA, schema_name="decision_memo",
                                  max_output_tokens=2500, review_ids=sent,
                                  validate=make_validator(pack, ranking_rows), phase=phase)
    except llm.LLMFailed as e:
        (run_dir / "memo_check.json").write_text(json.dumps({"status": "failed", "error": str(e)}, indent=2))
        return {"status": "failed", "error": str(e)}

    top_area = max(pack["areas"].items(), key=lambda kv: kv[1]["severity_sum"] if kv[0] in AREAS else -1)[0]
    check = {"status": "passed", "checks": ["claim values match ranking", "claim IDs cited", "issue IDs exist",
                                            "review IDs from evidence pack", "numbers appear in evidence pack"],
             "recommended_area": out["recommended_area"], "area_with_highest_severity_sum": top_area,
             "agrees_with_highest_severity_sum": out["recommended_area"] == top_area,
             "model_call": info, "human_review": "pending"}
    (run_dir / "memo_check.json").write_text(json.dumps(check, indent=2))
    with open(run_dir / "claims.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["claim_id", "issue_id", "metric", "value"])
        w.writerows([c["claim_id"], c["issue_id"], c["metric"], c["value"]] for c in out["claims"])
    (run_dir / "recommendation.json").write_text(json.dumps({**out, "check": check}, indent=2, ensure_ascii=False))
    (run_dir / "memo.md").write_text(
        f"# Decision memo: {out['headline']}\n\n"
        f"*Generated by `{llm.MODEL}` (role: memo, prompt `{PROMPT_VERSION}`) from the saved ranking and evidence "
        f"pack only; all claims passed the automated check in `memo_check.json`. Human review: pending.*\n\n"
        f"{out['memo_markdown']}\n\n## Claims\n\n| Claim | Issue | Metric | Value |\n|---|---|---|---|\n"
        + "".join(f"| {c['claim_id']} | {c['issue_id']} | {c['metric']} | {c['value']} |\n" for c in out["claims"]),
        encoding="utf-8")
    return {"status": "passed", "recommended_area": out["recommended_area"], "claims": len(out["claims"]),
            "cached": info.get("cached", False)}
