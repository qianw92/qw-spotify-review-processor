"""Stage 1 — Prepare. Read every source row with code (no model calls), profile it,
quarantine empty texts, and queue everything else as pending.

Outputs:
  outputs/data_manifest.json    identity of the input file and this run
  outputs/ingestion_report.json full-file profile + checks against the course manifest
  outputs/quarantine.jsonl      rows set aside, with reasons
  grading/ingestion.json        profile produced by the course-provided helper
  state/pipeline.sqlite         every row + status (pending / quarantined)
"""
import datetime
import hashlib
import json
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import check_submission as grader  # noqa: E402  (course helper: row_sha, csv_rows, profile)

from . import db  # noqa: E402

COURSE_MANIFEST = ROOT / "data" / "manifest.json"
EXPECTED_FULL = {"records": 660622, "nonempty": 660609, "empty_review_text": 13,
                 "missing_app_version": 159701, "duplicate_review_ids": 0, "distinct_nonempty_texts": 484189}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return None


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)  # atomic


def run(input_csv, db_path=db.DEFAULT_DB, out_dir=ROOT / "outputs", grading_dir=ROOT / "grading"):
    input_csv = Path(input_csv)
    started = time.time()
    run_id = "ingest-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    file_sha = grader.sha(input_csv)

    con = db.connect(db_path)
    con.execute("DELETE FROM records"); con.execute("DELETE FROM reviews")  # ingest is a full, deterministic rebuild

    counts = Counter()
    seen_ids, text_counts = set(), Counter()
    ratings, months, ts_issues = Counter(), Counter(), Counter()
    text_lengths = []
    quarantine = []
    first = last = None
    batch_reviews, batch_records = [], []
    stamp = now()

    for i, row in enumerate(grader.csv_rows(input_csv)):
        rid = row["review_id"]
        text = row["review_text"]
        empty = not text.strip()
        counts["records"] += 1
        if rid in seen_ids:
            counts["duplicate_review_ids"] += 1
            quarantine.append({"review_id": rid, "row_index": i, "reason": "duplicate_review_id"})
            continue  # keep the first occurrence; later duplicates are reported, not loaded
        seen_ids.add(rid)
        counts["empty_review_text"] += empty
        counts["missing_app_version"] += not row["app_version"].strip()
        counts["multiline_text"] += ("\n" in text)
        ratings[row["review_rating"]] += 1
        ts = row["review_timestamp"]
        months[ts[:7]] += 1
        if len(ts) != 19:
            ts_issues["unexpected_timestamp_format"] += 1
        first = min(first, ts) if first else ts
        last = max(last, ts) if last else ts
        text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if not empty:
            text_counts[text_sha] += 1
            text_lengths.append(len(text))
        source_sha = grader.row_sha(row)
        batch_reviews.append((rid, i, text, row["review_rating"], row["review_likes"], row["app_version"],
                              ts, source_sha, text_sha, int(empty)))
        if empty:
            batch_records.append((rid, "quarantined", "empty_review_text", 0, stamp))
            quarantine.append({"review_id": rid, "source_sha256": source_sha, "row_index": i,
                               "status": "quarantined", "reason": "empty_review_text", "attempts": 0})
        else:
            batch_records.append((rid, "pending", None, 0, stamp))
        if len(batch_reviews) >= 20000:
            con.executemany("INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?,?,?)", batch_reviews)
            con.executemany("INSERT INTO records VALUES (?,?,?,?,?)", batch_records)
            con.commit(); batch_reviews.clear(); batch_records.clear()
    con.executemany("INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?,?,?)", batch_reviews)
    con.executemany("INSERT INTO records VALUES (?,?,?,?,?)", batch_records)
    con.commit()

    nonempty = counts["records"] - counts["duplicate_review_ids"] - counts["empty_review_text"]
    distinct = len(text_counts)
    dup_groups = sum(1 for c in text_counts.values() if c > 1)
    status_counts = dict(con.execute("SELECT status, COUNT(*) FROM records GROUP BY status").fetchall())

    # Grader's own profile (required file grading/ingestion.json), produced by the provided helper.
    official = grader.profile(input_csv)
    grader.write_json(Path(grading_dir) / "ingestion.json", official)

    observed = {"records": counts["records"], "nonempty": nonempty, "empty_review_text": counts["empty_review_text"],
                "missing_app_version": counts["missing_app_version"], "duplicate_review_ids": counts["duplicate_review_ids"],
                "distinct_nonempty_texts": distinct}
    is_full_file = file_sha == json.loads(COURSE_MANIFEST.read_text())["files"]["spotify_reviews_18months.csv"]["sha256"] \
        if COURSE_MANIFEST.exists() else False
    checks = {k: {"expected": EXPECTED_FULL[k], "observed": observed[k], "ok": observed[k] == EXPECTED_FULL[k]}
              for k in EXPECTED_FULL} if is_full_file else "skipped: input is not the full course file"
    agrees_with_grader = (official["counts"]["records"] == counts["records"]
                          and official["counts"]["empty_review_text"] == counts["empty_review_text"]
                          and official["counts"]["missing_app_version"] == counts["missing_app_version"]
                          and official["counts"]["duplicate_review_ids"] == counts["duplicate_review_ids"])

    report = {
        "run_id": run_id, "created_at": now(), "stage": "prepare", "model_calls": 0,
        "input": {"path": str(input_csv), "bytes": input_csv.stat().st_size, "sha256": file_sha,
                  "is_course_full_file": is_full_file},
        "counts": {**observed, "multiline_text": counts["multiline_text"]},
        "exact_duplicate_texts": {"distinct_nonempty_texts": distinct,
                                  "texts_appearing_more_than_once": dup_groups,
                                  "rows_reusable_from_cache": nonempty - distinct},
        "text_length_chars": {"min": min(text_lengths), "median": statistics.median(text_lengths),
                              "mean": round(statistics.fmean(text_lengths), 1),
                              "p95": sorted(text_lengths)[int(len(text_lengths) * 0.95)],
                              "max": max(text_lengths)} if text_lengths else None,
        "reviews_by_rating": dict(sorted(ratings.items())),
        "reviews_by_month": dict(sorted(months.items())),
        "first_review": first, "last_review": last, "timestamp_issues": dict(ts_issues),
        "record_status": status_counts,
        "quarantine": {"count": len(quarantine), "by_reason": dict(Counter(q["reason"] for q in quarantine))},
        "checks_vs_course_manifest": checks,
        "agrees_with_course_profile_helper": agrees_with_grader,
        "seconds": round(time.time() - started, 1),
    }
    manifest = {"run_id": run_id, "created_at": report["created_at"], "code_commit": git_commit(),
                "input": report["input"], "row_hash": "check_submission.row_sha (SHA-256 of canonical JSON of 6 source fields)",
                "outputs": {"ingestion_report": "outputs/ingestion_report.json", "quarantine": "outputs/quarantine.jsonl",
                            "grading_ingestion": "grading/ingestion.json", "state_db": str(db_path)}}

    out_dir = Path(out_dir)
    write_json(out_dir / "ingestion_report.json", report)
    write_json(out_dir / "data_manifest.json", manifest)
    tmp = out_dir / "quarantine.jsonl.tmp"
    tmp.write_text("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in quarantine), encoding="utf-8")
    tmp.replace(out_dir / "quarantine.jsonl")
    con.close()
    return report
