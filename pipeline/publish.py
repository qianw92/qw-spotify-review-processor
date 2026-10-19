"""Publish saved full-run outputs to the dashboard database (Neon Postgres). Code only, no model calls.

Reads the local pipeline database (state/pipeline.sqlite) and saved run files, then rebuilds every table in
db/schema.sql over a DIRECT connection (DATABASE_URL_UNPOOLED). Also (re)creates a read-only role for the
deployed backend, so the website can never modify the data.
"""
import csv
import json
import os
import secrets
import sqlite3
from collections import defaultdict
from pathlib import Path

import psycopg
import psycopg.sql

from . import memo

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "outputs" / "full_run"
ISSUES_CFG = json.loads((ROOT / "schema" / "issues.json").read_text())
AREA_OF = {t: a for a, ts in ISSUES_CFG["areas"].items() if a != "description" for t in ts}
READER_ROLE = "dashboard_reader"


def metrics_documents(lite):
    status = dict(lite.execute("SELECT status, COUNT(*) FROM records GROUP BY status").fetchall())
    ing = json.loads((RUN / "ingestion_report.json").read_text())
    ded = json.loads((RUN / "dedupe_report.json").read_text())
    ver = json.loads((RUN / "verify" / "verify_report.json").read_text())
    gold = json.loads((ROOT / "evals" / "golden" / "summary.json").read_text())["summary"]
    s_init = json.loads((RUN / "run_summary_full-initial.json").read_text())
    s_res = json.loads((RUN / "run_summary_full-resume.json").read_text())
    ledger = defaultdict(float)
    for r in csv.DictReader(open(ROOT / "budget" / "spend_ledger.csv", encoding="utf-8")):
        ledger[r["provider"]] += float(r["cost_usd"])
    calls = [json.loads(l) for l in open(RUN / "calls.jsonl", encoding="utf-8")]
    run_cost = defaultdict(float)
    for c in calls:
        run_cost["typesafe" if c["role"] in ("enrich", "verify") else "openai"] += c.get("cost_usd", 0) or 0
    return {
        "coverage": {"source_rows": sum(status.values()), "completed": status.get("completed", 0),
                     "quarantined": status.get("quarantined", 0), "pending": status.get("pending", 0),
                     "nonempty": ing["counts"]["nonempty"], "empty_text_quarantined": ing["counts"]["empty_review_text"],
                     "distinct_texts_sent_to_model": ded["counts"]["canonical_texts_to_classify"],
                     "exact_duplicate_reuses": ded["counts"]["alias_rows_reusing_a_label"]},
        "run": {"jev_model": "jev-1.13.0", "openai_model": "gpt-6-luna", "label_config": s_res["config"]["enrich"],
                "workers": s_res["config"]["workers"], "batch_size": 50,
                "wall_clock_hours": round((s_init["wall_clock_seconds"] + s_res["wall_clock_seconds"]) / 3600, 2),
                "model_calls": len(calls), "failed_attempts_retried": sum(c["outcome"] == "failed" for c in calls),
                "interrupted_and_resumed": True},
        "cost_usd": {"full_run_jev": round(run_cost["typesafe"], 4), "full_run_openai": round(run_cost["openai"], 4),
                     "project_total_jev": round(ledger["typesafe"], 4), "project_total_openai": round(ledger["openai"], 4),
                     "project_total": round(sum(ledger.values()), 4), "budget": 10.0},
        "verifier": {"sample": ver["compared"], "topic": ver["agreement"]["topic"], "intent": ver["agreement"]["intent"],
                     "severity": ver["agreement"]["severity"], "all_three": ver["all_three_agree"]},
        "golden": {"cases": gold["cases"], "topic": gold["topic_agreement"], "intent": gold["intent_agreement"],
                   "severity_exact": gold["severity_exact"], "severity_mae": gold["severity_mae"],
                   "note": "model severity tends to run one level high"},
    }


def run():
    url = os.environ["DATABASE_URL_UNPOOLED"]
    lite = sqlite3.connect(ROOT / "state" / "pipeline.sqlite")
    with psycopg.connect(url, autocommit=False) as pg:
        pg.execute((ROOT / "db" / "schema.sql").read_text())

        # 1) every source review with its final status and labels
        q = lite.execute("""
            SELECT r.review_id, r.row_index, s.status, s.reason, r.review_text, r.review_rating, r.review_timestamp,
                   NULLIF(r.app_version, ''), l.topic, l.intent, l.severity, l.sentiment, l.needs_review,
                   l.evidence_quote, m.issue_id, l.cache_source_id, l.label_config
            FROM reviews r JOIN records s USING (review_id) LEFT JOIN labels l USING (review_id)
            LEFT JOIN membership m USING (review_id) ORDER BY r.row_index""")
        n = 0
        with pg.cursor() as cur, cur.copy("COPY reviews_processed FROM STDIN") as cp:
            for row in q:
                row = list(row)
                row[5] = int(row[5]) if row[5] not in (None, "") else None
                row[6] = row[6] or None
                row[12] = None if row[12] is None else bool(row[12])
                cp.write_row(row)
                n += 1
        # 2) issues + ranking
        ranking = {r["issue_id"]: r for r in csv.DictReader(open(RUN / "aggregates.csv", encoding="utf-8"))}
        meta = {r[0]: r[1:] for r in lite.execute("SELECT issue_id, topic, name, description FROM issues")}
        examples = {r["issue_id"]: r["example_review_ids"].split() for r in csv.DictReader(open(RUN / "issues.csv"))}
        mix = defaultdict(dict)
        for iid, sev, cnt in lite.execute("""SELECT m.issue_id, l.severity, COUNT(*) FROM membership m
                                             JOIN labels l USING (review_id) GROUP BY 1, 2"""):
            mix[iid][str(sev)] = cnt
        with pg.cursor() as cur:
            for iid, r in ranking.items():
                topic, name, desc = meta[iid]
                cur.execute("INSERT INTO issues VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (iid, int(r["rank"]), topic, AREA_OF[topic], name, desc, int(r["complaint_count"]),
                             int(r["severity_sum"]), r["mean_severity"], int(r["priority_score"]),
                             int(r["cancellation_count"]), r["share_of_complaints_pct"], json.dumps(mix[iid]),
                             examples.get(iid, [])))
            # 3) areas (same numbers the memo's evidence pack used)
            pack = json.loads((RUN / "memo_evidence_pack.json").read_text())
            for a, x in pack["areas"].items():
                cur.execute("INSERT INTO areas VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                            (a, x["topics"], x["complaint_count"], x["severity_sum"], x["mean_severity"],
                             x["share_of_complaints_pct"], x["severity_4_or_5_count"], x["cancellation_intent_count"]))
            # 4) chart distributions
            for dim, expr in (("topic", "l.topic"), ("intent", "l.intent"), ("severity", "CAST(l.severity AS TEXT)"),
                              ("month", "substr(r.review_timestamp, 1, 7)")):
                for bucket, recs, comp in lite.execute(f"""
                        SELECT {expr}, COUNT(*), SUM(l.intent IN ('complaint','cancellation'))
                        FROM labels l JOIN reviews r USING (review_id) GROUP BY 1"""):
                    cur.execute("INSERT INTO distributions VALUES (%s,%s,%s,%s)", (dim, bucket, recs, comp))
            # 5) run metrics
            for k, v in metrics_documents(lite).items():
                cur.execute("INSERT INTO metrics VALUES (%s,%s)", (k, json.dumps(v)))
            # 6) recommendation + claims
            rec = json.loads((RUN / "recommendation.json").read_text())
            cur.execute("INSERT INTO recommendation VALUES (1,%s,%s,%s,%s,%s,%s,%s)",
                        (rec["recommended_area"], rec["headline"], rec["memo_markdown"], json.dumps(rec["cited_reviews"]),
                         json.dumps(rec["check"]), "gpt-6-luna", memo.PROMPT_VERSION))
            for c in csv.DictReader(open(RUN / "claims.csv", encoding="utf-8")):
                cur.execute("INSERT INTO claims VALUES (%s,%s,%s,%s)", (c["claim_id"], c["issue_id"], c["metric"], c["value"]))
            # indexes after bulk load
            cur.execute("CREATE INDEX ON reviews_processed (issue_id, severity DESC)")
            cur.execute("CREATE INDEX ON reviews_processed (topic)")
            # 7) read-only role for the deployed backend
            password = secrets.token_urlsafe(24)
            cur.execute(f"""DO $$ BEGIN
                              IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{READER_ROLE}') THEN
                                CREATE ROLE {READER_ROLE} LOGIN;
                              END IF; END $$""")
            cur.execute(psycopg.sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                psycopg.sql.Identifier(READER_ROLE), psycopg.sql.Literal(password)))
            cur.execute(f"GRANT USAGE ON SCHEMA public TO {READER_ROLE}")
            cur.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {READER_ROLE}")
            cur.execute(f"ALTER ROLE {READER_ROLE} SET default_transaction_read_only = on")
        pg.commit()
    reader_url = os.environ["DATABASE_URL"].replace("neondb_owner:", f"{READER_ROLE}:", 1)
    reader_url = reader_url.split("@", 1)
    reader_url = reader_url[0].rsplit(":", 1)[0] + ":" + password + "@" + reader_url[1]
    env = ROOT / ".env"
    lines = [l for l in env.read_text().splitlines() if not l.startswith("DATABASE_URL_READONLY=")]
    env.write_text("\n".join(lines + [f"DATABASE_URL_READONLY={reader_url}"]) + "\n")
    return {"reviews_processed": n, "issues": len(ranking), "areas": len(pack["areas"]),
            "readonly_role": READER_ROLE, "readonly_url_saved_to": ".env (DATABASE_URL_READONLY)"}
