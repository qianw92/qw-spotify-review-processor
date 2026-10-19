-- Dashboard database (Neon Postgres). Rebuilt from saved pipeline outputs by `python -m pipeline publish`.
-- Every value comes from the full run; nothing here is computed by a model at query time.

DROP TABLE IF EXISTS reviews_processed, issues, areas, distributions, metrics, recommendation, claims CASCADE;

-- One row per source review (660,622): its final status and validated labels.
CREATE TABLE reviews_processed (
    review_id        TEXT PRIMARY KEY,
    row_index        INTEGER NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('completed', 'quarantined')),
    reason           TEXT,
    review_text      TEXT NOT NULL,
    review_rating    SMALLINT,
    review_timestamp TIMESTAMP,
    app_version      TEXT,
    topic            TEXT,
    intent           TEXT,
    severity         SMALLINT,
    sentiment        REAL,
    needs_review     BOOLEAN,
    evidence_quote   TEXT,
    issue_id         TEXT,           -- set for complaint/cancellation records (baseline membership)
    cache_source_id  TEXT,           -- exact-duplicate copy of this canonical review's label
    label_config     TEXT
);

-- 28 issues with the required baseline ranking columns plus names and context.
CREATE TABLE issues (
    issue_id          TEXT PRIMARY KEY,
    rank              INTEGER NOT NULL,
    topic             TEXT NOT NULL,
    area              TEXT NOT NULL,
    name              TEXT NOT NULL,
    description       TEXT,
    complaint_count   INTEGER NOT NULL,
    severity_sum      INTEGER NOT NULL,
    mean_severity     NUMERIC(9, 6) NOT NULL,
    priority_score    INTEGER NOT NULL,
    cancellation_count INTEGER NOT NULL,
    share_of_complaints_pct NUMERIC(5, 1) NOT NULL,
    severity_mix      JSONB NOT NULL,
    example_review_ids TEXT[] NOT NULL
);

-- The four decision areas (plus catalog/other as "outside_options").
CREATE TABLE areas (
    area                    TEXT PRIMARY KEY,
    topics                  TEXT[] NOT NULL,
    complaint_count         INTEGER NOT NULL,
    severity_sum            INTEGER NOT NULL,
    mean_severity           NUMERIC(4, 2) NOT NULL,
    share_of_complaints_pct NUMERIC(5, 1) NOT NULL,
    severity_4_or_5_count   INTEGER NOT NULL,
    cancellation_intent_count INTEGER NOT NULL
);

-- Pre-aggregated counts for charts (dimension = topic | intent | severity | month).
CREATE TABLE distributions (
    dimension TEXT NOT NULL,
    bucket    TEXT NOT NULL,
    records   INTEGER NOT NULL,
    complaints INTEGER NOT NULL,
    PRIMARY KEY (dimension, bucket)
);

-- Run-level metrics: coverage, cost, timing, evaluation results (one JSON document per key).
CREATE TABLE metrics (
    key   TEXT PRIMARY KEY,
    value JSONB NOT NULL
);

-- The AI-generated, human-reviewed recommendation (memo) and its checks.
CREATE TABLE recommendation (
    id               INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    recommended_area TEXT NOT NULL,
    headline         TEXT NOT NULL,
    memo_markdown    TEXT NOT NULL,
    cited_reviews    JSONB NOT NULL,
    check_result     JSONB NOT NULL,
    model            TEXT NOT NULL,
    prompt_version   TEXT NOT NULL
);

CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL REFERENCES issues (issue_id),
    metric   TEXT NOT NULL,
    value    TEXT NOT NULL
);
