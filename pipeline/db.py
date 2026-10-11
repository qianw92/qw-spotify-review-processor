"""Local SQLite state store: one row per source review plus its pipeline status."""
import sqlite3
from pathlib import Path

DEFAULT_DB = Path("state/pipeline.sqlite")

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    review_id        TEXT PRIMARY KEY,
    row_index        INTEGER NOT NULL,      -- 0-based position in the source CSV
    review_text      TEXT NOT NULL,         -- exact source string, never trimmed
    review_rating    TEXT NOT NULL,
    review_likes     TEXT NOT NULL,
    app_version      TEXT NOT NULL,
    review_timestamp TEXT NOT NULL,
    source_sha256    TEXT NOT NULL,         -- grader's row_sha() of the six original fields
    text_sha256      TEXT NOT NULL,         -- SHA-256 of review_text alone, for exact-duplicate lookup
    is_empty         INTEGER NOT NULL       -- 1 when review_text.strip() == ''
);
CREATE TABLE IF NOT EXISTS records (
    review_id  TEXT PRIMARY KEY REFERENCES reviews(review_id),
    status     TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'quarantined')),
    reason     TEXT,
    attempts   INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS llm_cache (
    cache_key  TEXT PRIMARY KEY,      -- sha256 of model + prompt version + exact request payload
    role       TEXT NOT NULL,
    response   TEXT NOT NULL,         -- validated JSON returned by the model
    request_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reviews_text ON reviews(text_sha256);
CREATE INDEX IF NOT EXISTS idx_records_status ON records(status);
"""


def connect(path=DEFAULT_DB):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


DERIVED_TABLES = ("labels", "verifications", "membership", "issues", "llm_cache", "text_map")


def reset_for_new_input(con):
    """A different input file invalidates every saved result in this database."""
    for t in DERIVED_TABLES:
        con.execute(f"DROP TABLE IF EXISTS {t}")
    con.execute("DELETE FROM records")
    con.execute("DELETE FROM reviews")
    con.executescript(SCHEMA)
