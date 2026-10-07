"""Stage 1b — Exact-text deduplication (no model calls).

For every distinct nonempty review_text, the earliest source row becomes the
"canonical" review: it is the only one sent to the model. Every other row with
byte-identical text records cache_source_id = that canonical review_id, so it can
reuse the canonical's validated label later. Every original ID stays its own row.

Grading contract rules this follows:
  - only exact text matches (SHA-256 of the unmodified string), never "similar" text
  - cache_source_id points directly at the original, never at another alias (no chains)
  - classification uses review_text only, so identical text => identical valid input

Outputs:
  state/pipeline.sqlite  table text_map(review_id, text_sha256, canonical_review_id, is_canonical)
  outputs/dedupe_report.json
"""
import datetime
import json
import time
from pathlib import Path

from . import db

ROOT = Path(__file__).resolve().parent.parent

SCHEMA = """
DROP TABLE IF EXISTS text_map;
CREATE TABLE text_map (
    review_id           TEXT PRIMARY KEY REFERENCES reviews(review_id),
    text_sha256         TEXT NOT NULL,
    canonical_review_id TEXT NOT NULL REFERENCES reviews(review_id),
    is_canonical        INTEGER NOT NULL
);
CREATE INDEX idx_text_map_canonical ON text_map(canonical_review_id);
"""


def run(db_path=db.DEFAULT_DB, out_dir=ROOT / "outputs"):
    started = time.time()
    con = db.connect(db_path)
    con.executescript(SCHEMA)
    # Canonical = lowest row_index among nonempty rows sharing the exact same text hash.
    con.execute("""
        INSERT INTO text_map (review_id, text_sha256, canonical_review_id, is_canonical)
        SELECT r.review_id, r.text_sha256, c.review_id, r.review_id = c.review_id
        FROM reviews r
        JOIN (SELECT text_sha256, MIN(row_index) AS first_row FROM reviews WHERE is_empty = 0 GROUP BY text_sha256) f
          ON f.text_sha256 = r.text_sha256
        JOIN reviews c ON c.row_index = f.first_row
        WHERE r.is_empty = 0
    """)
    con.commit()

    q = lambda sql: con.execute(sql).fetchone()[0]
    nonempty = q("SELECT COUNT(*) FROM reviews WHERE is_empty = 0")
    mapped = q("SELECT COUNT(*) FROM text_map")
    canonical = q("SELECT COUNT(*) FROM text_map WHERE is_canonical = 1")
    aliases = q("SELECT COUNT(*) FROM text_map WHERE is_canonical = 0")

    # Integrity checks — each must be 0.
    checks = {
        "nonempty_rows_not_mapped": nonempty - mapped,
        "alias_text_differs_from_canonical": q("""
            SELECT COUNT(*) FROM text_map m JOIN reviews a ON a.review_id = m.review_id
            JOIN reviews c ON c.review_id = m.canonical_review_id WHERE a.review_text != c.review_text"""),
        "alias_points_to_non_canonical (chain)": q("""
            SELECT COUNT(*) FROM text_map m JOIN text_map t ON t.review_id = m.canonical_review_id
            WHERE t.is_canonical = 0"""),
        "canonical_not_pointing_to_itself": q(
            "SELECT COUNT(*) FROM text_map WHERE is_canonical = 1 AND canonical_review_id != review_id"),
        "empty_text_rows_mapped": q(
            "SELECT COUNT(*) FROM text_map m JOIN reviews r USING (review_id) WHERE r.is_empty = 1"),
    }

    top = con.execute("""
        SELECT c.review_text, COUNT(*) AS n FROM text_map m JOIN reviews c ON c.review_id = m.canonical_review_id
        GROUP BY m.canonical_review_id ORDER BY n DESC, c.row_index LIMIT 15""").fetchall()
    size_buckets = dict(con.execute("""
        SELECT CASE WHEN n = 1 THEN '1 (unique)' WHEN n <= 5 THEN '2-5' WHEN n <= 50 THEN '6-50'
                    WHEN n <= 500 THEN '51-500' ELSE '501+' END AS bucket, COUNT(*)
        FROM (SELECT COUNT(*) AS n FROM text_map GROUP BY canonical_review_id) GROUP BY bucket""").fetchall())

    report = {
        "stage": "dedupe", "model_calls": 0,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "rule": "exact byte-identical review_text (SHA-256); canonical = earliest source row; aliases reuse its label via cache_source_id",
        "counts": {"nonempty_rows": nonempty, "canonical_texts_to_classify": canonical,
                   "alias_rows_reusing_a_label": aliases,
                   "work_reduction_pct": round(100 * aliases / nonempty, 2) if nonempty else 0},
        "integrity_checks_all_zero": all(v == 0 for v in checks.values()),
        "integrity_checks": checks,
        "group_size_distribution": size_buckets,
        "most_repeated_texts": [{"text": t, "rows": n} for t, n in top],
        "seconds": round(time.time() - started, 1),
    }
    out = Path(out_dir) / "dedupe_report.json"
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out)
    con.close()
    return report
