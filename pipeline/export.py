"""Write one final record per source review_id in the grading-contract format (code only)."""
import json
from pathlib import Path


def records(con):
    """Yields contract records in source order: completed, quarantined, or pending (pending is not exported
    as completed; it is reported separately so it can never be mistaken for a classification)."""
    rows = con.execute("""
        SELECT r.review_id, r.source_sha256, s.status, s.reason, s.attempts,
               l.topic, l.intent, l.sentiment, l.severity, l.entities, l.evidence_quote, l.needs_review,
               l.label_config, l.cache_source_id
        FROM reviews r JOIN records s USING (review_id) LEFT JOIN labels l USING (review_id)
        ORDER BY r.row_index""")
    for (rid, sha, status, reason, attempts, topic, intent, sent, sev, ents, quote, needs, cfg, cache) in rows:
        if status == "completed":
            rec = {"review_id": rid, "source_sha256": sha, "status": "completed", "topic": topic, "intent": intent,
                   "sentiment": sent, "severity": sev, "entities": json.loads(ents), "evidence_quote": quote,
                   "needs_review": bool(needs), "label_config": cfg}
            if cache:
                rec["cache_source_id"] = cache
        elif status == "quarantined":
            rec = {"review_id": rid, "source_sha256": sha, "status": "quarantined", "reason": reason,
                   "attempts": attempts}
        else:
            rec = {"review_id": rid, "source_sha256": sha, "status": "pending"}
        yield rec


def write(con, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    counts = {}
    with open(tmp, "w", encoding="utf-8") as f:
        for rec in records(con):
            counts[rec["status"]] = counts.get(rec["status"], 0) + 1
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    tmp.replace(path)
    return counts
