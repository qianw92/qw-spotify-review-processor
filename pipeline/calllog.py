"""Append-only model-call log (grading contract format) shared by every role."""
import datetime
import json
from pathlib import Path


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def log_call(run_dir, **event):
    """role in {enrich, verify, group, memo}; outcome in {succeeded, failed}; review_ids = IDs actually sent."""
    path = Path(run_dir) / "calls.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now(), **event}, ensure_ascii=False) + "\n")


def count_calls(run_dir):
    path = Path(run_dir) / "calls.jsonl"
    return sum(1 for _ in open(path, encoding="utf-8")) if path.exists() else 0
