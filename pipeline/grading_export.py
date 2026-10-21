"""Build the standardized grading/ folder required by GRADING_CONTRACT.md (code only, no model calls).

grading/run.json                 version, input identity, declared scope
grading/ingestion.json           full-file profile from the course helper (already produced by `ingest`)
grading/records.jsonl.gz         exactly one final record per source ID (completed or quarantined)
grading/membership.csv           issue_id,review_id
grading/ranking.csv              rank,issue_id,complaint_count,severity_sum,mean_severity,priority_score
grading/claims.csv               claim_id,issue_id,metric,value (every issue-level number in the memo)
grading/calls.jsonl.gz           every model call of the final run (enrich/verify/group/memo; initial/resume)
grading/checkpoint_before.json   completed_ids before the interruption (saved during the run)
grading/checkpoint_after.json    completed_ids after resuming (saved during the run)
"""
import gzip
import json
import shutil
import sys
from pathlib import Path

from . import db, export

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import check_submission as grader  # noqa: E402

RUN = ROOT / "outputs" / "full_run"
OUT = ROOT / "grading"
SOURCE = ROOT / "data" / "spotify_reviews_18months.csv"


def run():
    OUT.mkdir(exist_ok=True)
    con = db.connect(ROOT / "state" / "pipeline.sqlite")
    counts = dict(con.execute("SELECT status, COUNT(*) FROM records GROUP BY status").fetchall())

    run_json = {"version": grader.VERSION, "analysis_count": sum(counts.values()),
                "analysis_sha256": grader.sha(SOURCE), "classification_input_fields": ["review_text"],
                "allow_multi_issue": False}
    (OUT / "run.json").write_text(json.dumps(run_json, indent=2) + "\n")

    # records: contract fields only (pending never exported as completed; there are none in the final run)
    n = {"completed": 0, "quarantined": 0}
    with gzip.open(OUT / "records.jsonl.gz", "wt", encoding="utf-8", compresslevel=9) as f:
        for rec in export.records(con):
            if rec["status"] == "pending":
                raise SystemExit(f"pending record {rec['review_id']}: the final run is incomplete")
            if rec["status"] == "quarantined":
                rec = {k: rec[k] for k in ("review_id", "source_sha256", "status", "reason")}
            n[rec["status"]] += 1
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    for name in ("membership.csv", "ranking.csv", "claims.csv"):
        shutil.copyfile(RUN / name, OUT / name)

    # calls: every attempt from the final run, in the contract shape (extra fields are allowed)
    seen, calls = set(), 0
    with gzip.open(OUT / "calls.jsonl.gz", "wt", encoding="utf-8", compresslevel=9) as f:
        for line in open(RUN / "calls.jsonl", encoding="utf-8"):
            c = json.loads(line)
            if c["request_id"] in seen:          # local failure IDs are unique per attempt; guard anyway
                c["request_id"] = f"{c['request_id']}-{calls}"
            seen.add(c["request_id"])
            c.setdefault("label_config", c.get("prompt_version"))
            c["input_tokens"] = int(c.get("input_tokens") or 0)
            c["output_tokens"] = int(c.get("output_tokens") or 0)
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
            calls += 1

    # plain copies would be ambiguous next to the .gz versions
    for stale in ("records.jsonl", "calls.jsonl"):
        (OUT / stale).unlink(missing_ok=True)
    return {"run.json": run_json, "records": n, "calls": calls,
            "sizes_mb": {p.name: round(p.stat().st_size / 1e6, 1) for p in sorted(OUT.iterdir())}}
