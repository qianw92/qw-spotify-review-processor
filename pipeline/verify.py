"""Stage 3 — Verify (role: verify). An independent Jev task re-labels a declared random sample.

Independence: the verifier never sees the enricher's answers. It gets only the original text and the
shared label definitions, with its own question wording and reversed option order (prompt verify-v1).
Code then compares the two and writes a disagreement report. The planted-error test reuses saved
verifier predictions against a deliberately corrupted copy of the enricher labels (no model calls).
"""
import csv
import hashlib
import json
import math
import time
from pathlib import Path

from . import budget, calllog, enrich, rules

PROMPT_VERSION = "verify-v1"
SEED = "verify-seed-v1"
FIELDS = ("topic", "intent", "severity")

SCHEMA = """
CREATE TABLE IF NOT EXISTS verifications (
    review_id     TEXT PRIMARY KEY,
    topic         TEXT NOT NULL,
    intent        TEXT NOT NULL,
    severity      INTEGER NOT NULL,
    sentiment     REAL NOT NULL,
    confidences   TEXT,
    verify_config TEXT NOT NULL,
    request_id    TEXT,
    created_at    TEXT NOT NULL
);
"""


def verify_config():
    return f"{enrich.MODEL}+{PROMPT_VERSION}+{rules.LABELS_VERSION}"


def sample(con, rate, minimum):
    """Declared deterministic sample: canonical completed reviews with the lowest sha256(seed:id)."""
    ids = [r[0] for r in con.execute(
        "SELECT review_id FROM labels WHERE cache_source_id IS NULL ORDER BY review_id")]
    n = min(len(ids), max(minimum, math.ceil(rate * len(ids))))
    ids.sort(key=lambda rid: hashlib.sha256(f"{SEED}:{rid}".encode()).hexdigest())
    return ids[:n]


def build_request(batch):
    from typesafe_sdk import Choice, Score
    reviews, questions, keymap = {}, {}, {}
    rev = lambda d: dict(reversed(list(d.items())))  # different option order than the enricher
    for i, (rid, text) in enumerate(batch):
        k = f"v{i:02d}"
        keymap[k] = rid
        reviews[k] = text
        ref = f"`texts.{k}`"
        questions[f"{k}|topic"] = Choice(instructions=f"Audit {ref}: which category in `taxonomy.topic` does it "
                                                      f"mainly concern? Apply the taxonomy's rules.",
                                         criteria={t: None for t in rev(rules.TOPICS)})
        questions[f"{k}|intent"] = Choice(instructions=f"Audit {ref}: what is the writer doing, per "
                                                       f"`taxonomy.intent` and its precedence?",
                                          criteria={t: None for t in rev(rules.INTENTS)})
        questions[f"{k}|severity"] = Choice(instructions=f"Audit {ref}: how serious is the reported impact, "
                                                         f"per `taxonomy.severity`?",
                                            criteria={s: None for s in rev(rules.SEVERITY)})
        questions[f"{k}|sentiment"] = Score(instructions=f"Audit {ref}: overall tone.",
                                            criteria=rules.SENTIMENT_LEVELS)
    return {"taxonomy": rules.shared_rules(), "texts": reviews}, questions, keymap


def run(con, run_dir, guard, rate=0.01, minimum=20, batch_size=50, phase="initial"):
    from typesafe_sdk import RetryPolicy, TypeSafeClient, TypeSafeError
    con.executescript(SCHEMA)
    cfg = verify_config()
    ids = sample(con, rate, minimum)
    done = {r[0] for r in con.execute("SELECT review_id FROM verifications WHERE verify_config=?", (cfg,))}
    todo = [i for i in ids if i not in done]
    texts = dict(con.execute(f"SELECT review_id, review_text FROM reviews WHERE review_id IN "
                             f"({','.join('?' * len(todo))})", todo).fetchall()) if todo else {}
    stats = {"declared_rate": rate, "declared_minimum": minimum, "seed": SEED, "sample_size": len(ids),
             "already_verified": len(ids) - len(todo), "requests": 0, "invalid": 0}
    for start in range(0, len(todo), batch_size):
        batch = [(rid, texts[rid]) for rid in todo[start:start + batch_size]]
        state, questions, keymap = build_request(batch)
        est = enrich.estimate_tokens(state, questions)
        guard.check(budget.cost(enrich.PROVIDER, est, 0) * enrich.RESERVE_FACTOR)
        ids_sent = [rid for rid, _ in batch]
        for attempt in range(1, enrich.API_ATTEMPTS + 1):
            t0 = time.time()
            try:
                with TypeSafeClient(model=enrich.MODEL, retry=RetryPolicy(max_retries=0), timeout=60) as c:
                    resp = c.system_one(state=state, questions=questions)
                break
            except TypeSafeError as e:
                calllog.log_call(run_dir, role="verify", model=enrich.MODEL, phase=phase, outcome="failed",
                                 request_id=f"local-verify-{time.time_ns()}", review_ids=ids_sent, input_tokens=0,
                                 output_tokens=0, attempt=attempt, error=f"{type(e).__name__}: {str(e)[:200]}")
                if attempt == enrich.API_ATTEMPTS:
                    raise
                time.sleep(0.5 * 2 ** attempt)
        u = resp.usage
        usd = budget.record(enrich.PROVIDER, resp.model, "verify", resp.request_id, u.input_tokens or 0,
                            u.output_tokens or 0)
        guard.add(usd)
        calllog.log_call(run_dir, role="verify", model=resp.model, phase=phase, outcome="succeeded",
                         request_id=resp.request_id, review_ids=ids_sent, input_tokens=u.input_tokens or 0,
                         output_tokens=u.output_tokens or 0, prompt_version=PROMPT_VERSION, attempt=attempt,
                         cost_usd=round(usd, 8), seconds=round(time.time() - t0, 3))
        stats["requests"] += 1
        with con:
            for k, rid in keymap.items():
                try:
                    a = {f: resp.answers[f"{k}|{f}"] for f in (*FIELDS, "sentiment")}
                    row = (rid, a["topic"].choice, a["intent"].choice, int(a["severity"].choice),
                           round(float(a["sentiment"].score) / 2 - 1, 2),
                           json.dumps({f: round(float(a[f].confidence), 4) for f in FIELDS}), cfg,
                           resp.request_id, calllog.now())
                    if row[1] not in rules.TOPICS or row[2] not in rules.INTENTS:
                        raise ValueError("label outside allowed set")
                    con.execute("INSERT OR REPLACE INTO verifications VALUES (?,?,?,?,?,?,?,?,?)", row)
                except (KeyError, ValueError, AttributeError) as e:
                    stats["invalid"] += 1  # verifier gaps are reported, never filled in
    stats.update(compare(con, ids, Path(run_dir) / "verify"))
    return stats


def compare(con, ids, out_dir, enricher_override=None, tag=""):
    """Code compares enricher vs verifier on the sample. enricher_override lets the planted-error test
    substitute a corrupted copy of enricher labels without touching the database."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    q = f"""SELECT l.review_id, r.review_text, l.topic, l.intent, l.severity, l.sentiment, l.confidences,
                   v.topic, v.intent, v.severity, v.sentiment
            FROM labels l JOIN verifications v USING (review_id) JOIN reviews r USING (review_id)
            WHERE l.review_id IN ({','.join('?' * len(ids))})"""
    rows = con.execute(q, ids).fetchall() if ids else []
    agree = {f: 0 for f in FIELDS}
    sev_err = sent_err = 0.0
    disagreements = []
    for rid, text, et, ei, es, esent, econf, vt, vi, vs, vsent in rows:
        e = {"topic": et, "intent": ei, "severity": es}
        if enricher_override and rid in enricher_override:
            e.update(enricher_override[rid])
        v = {"topic": vt, "intent": vi, "severity": vs}
        diff = [f for f in FIELDS if e[f] != v[f]]
        for f in FIELDS:
            agree[f] += f not in diff
        sev_err += abs(e["severity"] - vs)
        sent_err += abs(esent - vsent)
        if diff:
            disagreements.append({"review_id": rid, "fields": "|".join(diff), "review_text": text[:300],
                                  **{f"enricher_{f}": e[f] for f in FIELDS}, **{f"verifier_{f}": v[f] for f in FIELDS},
                                  "enricher_confidences": econf})
    n = len(rows)
    report = {"compared": n, "agreement": {f: round(agree[f] / n, 4) if n else None for f in FIELDS},
              "all_three_agree": round((n - len(disagreements)) / n, 4) if n else None,
              "severity_mae": round(sev_err / n, 4) if n else None,
              "sentiment_mae": round(sent_err / n, 4) if n else None, "disagreements": len(disagreements)}
    with open(out_dir / f"disagreements{tag}.csv", "w", newline="", encoding="utf-8") as f:
        cols = ["review_id", "fields", "review_text", *[f"enricher_{x}" for x in FIELDS],
                *[f"verifier_{x}" for x in FIELDS], "enricher_confidences"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(disagreements)
    (out_dir / f"verify_report{tag}.json").write_text(json.dumps(report, indent=2))
    return report


def planted_error_test(con, run_dir, n=10):
    """Synthetic: flip the topic on n verified records (in memory only) and check the comparison flags them."""
    cfg = verify_config()
    rows = con.execute("""SELECT l.review_id, l.topic FROM labels l JOIN verifications v USING (review_id)
                          WHERE v.verify_config=? AND l.topic = v.topic ORDER BY l.review_id LIMIT ?""",
                       (cfg, n)).fetchall()
    topics = list(rules.TOPICS)
    override = {rid: {"topic": topics[(topics.index(t) + 1) % len(topics)]} for rid, t in rows}
    ids = [r[0] for r in con.execute("SELECT review_id FROM verifications WHERE verify_config=?", (cfg,))]
    report = compare(con, ids, Path(run_dir) / "verify", enricher_override=override, tag="_planted_TEST")
    flagged = sum(1 for row in csv.DictReader(open(Path(run_dir) / "verify" / "disagreements_planted_TEST.csv"))
                  if row["review_id"] in override and "topic" in row["fields"])
    result = {"synthetic_test": True, "planted_wrong_topics": len(override), "flagged_by_comparison": flagged,
              "caught_all": flagged == len(override), "model_calls": 0, "comparison": report}
    (Path(run_dir) / "verify" / "planted_error_test.json").write_text(json.dumps(result, indent=2))
    return result
