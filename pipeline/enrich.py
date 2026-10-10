"""Stage 2 — Enrich (role: enrich). Jev labels each canonical review; code validates and saves.

Model judgment: topic, intent, severity, sentiment, and (long reviews only) which sentence is the evidence.
Code owns: batching (<= 50 reviews/request), entities, short-review quotes, validation, retries,
budget checks, saving after every batch, and copying labels to exact-duplicate aliases.

Two request layouts (part of label_config, so results are never mixed):
  batched — up to 50 reviews in one request; definitions sent once in `state`, questions point at each review
  single  — one review per request; definitions sent inside each question's options
"""
import datetime
import json
import random
import re
import time
from pathlib import Path

from . import budget, db, rules

ROOT = Path(__file__).resolve().parent.parent
ENTITIES = json.loads((ROOT / "schema" / "entities.json").read_text())
MODEL = "jev-1.13.0"
PROVIDER = "typesafe"
QUOTE_WHOLE_MAX_CHARS = 200
NEEDS_REVIEW_CONFIDENCE = 0.5      # provisional; tuned on development data, never on the golden set
CHARS_PER_TOKEN_ESTIMATE = 3.0     # conservative (over-estimates tokens) until measured
RESERVE_FACTOR = 1.5               # reserve 1.5x the estimate before each request
API_ATTEMPTS = 3                   # transient API errors: up to 3 attempts with backoff + jitter
FIELDS = ("topic", "intent", "severity", "sentiment")

LABEL_SCHEMA = """
CREATE TABLE IF NOT EXISTS labels (
    review_id       TEXT PRIMARY KEY REFERENCES reviews(review_id),
    topic           TEXT NOT NULL,
    intent          TEXT NOT NULL,
    severity        INTEGER NOT NULL,
    sentiment       REAL NOT NULL,
    entities        TEXT NOT NULL,      -- JSON list
    evidence_quote  TEXT NOT NULL,
    needs_review    INTEGER NOT NULL,
    label_config    TEXT NOT NULL,
    confidences     TEXT,               -- JSON {field: confidence}
    request_id      TEXT,
    cache_source_id TEXT,
    created_at      TEXT NOT NULL
);
"""


def label_config(layout):
    return f"{MODEL}+{rules.PROMPT_VERSION}+{rules.LABELS_VERSION}+{layout}"


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


# ---------- deterministic helpers (code, not model) ----------

def sentences(text):
    """Exact-substring sentence spans; used only for reviews longer than QUOTE_WHOLE_MAX_CHARS."""
    spans = [m.group(0).strip() for m in re.finditer(r"[^.!?\n]+[.!?]*", text)]
    return [s for s in spans if len(s) >= 3 and s in text]


def entities(text):
    found = []
    for name, words in ENTITIES["vocabulary"].items():
        if any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", text, re.I) for w in words):
            found.append(name)
    return found


# ---------- request building ----------

def build_request(batch, layout):
    """batch: list of (review_id, text). Returns (state, questions, keymap, quote_options)."""
    from typesafe_sdk import Choice, Score
    keymap, quote_options, questions = {}, {}, {}
    if layout == "batched":
        reviews = {}
        for i, (rid, text) in enumerate(batch):
            k = f"r{i:02d}"
            keymap[k] = rid
            reviews[k] = text
            ref = f"`reviews.{k}`"
            questions[f"{k}|topic"] = Choice(instructions=f"Primary topic of review {ref}, using `label_rules.topic`.",
                                             criteria={t: None for t in rules.TOPICS})
            questions[f"{k}|intent"] = Choice(instructions=f"Intent of review {ref}, using `label_rules.intent`.",
                                              criteria={t: None for t in rules.INTENTS})
            questions[f"{k}|severity"] = Choice(instructions=f"Severity of review {ref}, using `label_rules.severity`.",
                                                criteria={s: None for s in rules.SEVERITY})
            questions[f"{k}|sentiment"] = Score(instructions=f"Overall sentiment of review {ref}.",
                                                criteria=rules.SENTIMENT_LEVELS)
            add_quote_question(questions, quote_options, k, text, f"For review {ref}: ")
        state = {"label_rules": rules.shared_rules(), "reviews": reviews}
    elif layout == "single":
        (rid, text), = batch
        k = "r00"
        keymap[k] = rid
        questions[f"{k}|topic"] = Choice(instructions={"question": "Primary topic of this app review.",
                                                       "rules": rules.TOPIC_RULES}, criteria=rules.TOPICS)
        questions[f"{k}|intent"] = Choice(instructions={"question": "Intent of this app review.",
                                                        "rules": rules.INTENT_RULES}, criteria=rules.INTENTS)
        questions[f"{k}|severity"] = Choice(instructions={"question": "Severity of the reported impact.",
                                                          "rules": rules.SEVERITY_RULES}, criteria=rules.SEVERITY)
        questions[f"{k}|sentiment"] = Score(instructions="Overall sentiment of this app review.",
                                            criteria=rules.SENTIMENT_LEVELS)
        add_quote_question(questions, quote_options, k, text, "")
        state = text
    else:
        raise ValueError(layout)
    return state, questions, keymap, quote_options


def add_quote_question(questions, quote_options, k, text, prefix):
    from typesafe_sdk import Choice
    if len(text) <= QUOTE_WHOLE_MAX_CHARS:
        return
    sents = sentences(text)
    if len(sents) < 2:
        return
    opts = {f"s{j}": s for j, s in enumerate(sents[:255])}
    quote_options[k] = opts
    questions[f"{k}|quote"] = Choice(instructions=prefix + rules.QUOTE_QUESTION, criteria=opts)


def estimate_tokens(state, questions):
    payload = json.dumps(state, ensure_ascii=False) + json.dumps(
        {k: q.model_dump() if hasattr(q, "model_dump") else vars(q) for k, q in questions.items()},
        ensure_ascii=False, default=str)
    return int(len(payload) / CHARS_PER_TOKEN_ESTIMATE) + 300  # + measured per-request overhead


# ---------- parsing + validation ----------

def parse(answers, keymap, quote_options, texts, layout, request_id):
    """Returns ({review_id: label_row}, {review_id: reason}) — invalid reviews get a reason."""
    good, bad = {}, {}
    for k, rid in keymap.items():
        try:
            a = {f: answers[f"{k}|{f}"] for f in FIELDS}
            topic, intent, sev = a["topic"].choice, a["intent"].choice, a["severity"].choice
            if topic not in rules.TOPICS or intent not in rules.INTENTS or sev not in rules.SEVERITY:
                raise ValueError("label outside allowed set")
            score = float(a["sentiment"].score)
            if not 0 <= score <= 4:
                raise ValueError("sentiment score out of range")
            text = texts[rid]
            conf = {f: round(float(a[f].confidence), 4) for f in FIELDS}
            if k in quote_options:
                qa = answers[f"{k}|quote"]
                quote = quote_options[k][qa.choice]
                conf["quote"] = round(float(qa.confidence), 4)
            else:
                quote = text
            if not quote.strip() or quote not in text:
                raise ValueError("evidence_quote is not an exact substring")
            needs = min(conf.values()) < NEEDS_REVIEW_CONFIDENCE
            good[rid] = {"review_id": rid, "topic": topic, "intent": intent, "severity": int(sev),
                         "sentiment": round(score / 2 - 1, 2), "entities": json.dumps(entities(text)),
                         "evidence_quote": quote, "needs_review": int(needs), "label_config": label_config(layout),
                         "confidences": json.dumps(conf), "request_id": request_id, "cache_source_id": None,
                         "created_at": now()}
        except (KeyError, ValueError, AttributeError, TypeError) as e:
            bad[rid] = f"invalid_model_output: {type(e).__name__}: {e}"
    return good, bad


# ---------- the stage ----------

class Enricher:
    def __init__(self, db_path, run_dir, layout="batched", batch_size=50, max_spend=0.0, limit=None):
        assert 1 <= batch_size <= 50, "enrichment requests must contain at most 50 reviews"
        if layout == "single":
            batch_size = 1
        self.con = db.connect(db_path)
        self.con.executescript(LABEL_SCHEMA)
        self.layout, self.batch_size, self.limit = layout, batch_size, limit
        self.config = label_config(layout)
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.calls_path = self.run_dir / "calls.jsonl"
        self.guard = budget.Guard(max_spend)
        done = self.con.execute("SELECT COUNT(*) FROM labels WHERE label_config = ?", (self.config,)).fetchone()[0]
        self.phase = "resume" if done else "initial"

    def pending(self):
        """Canonical, nonempty reviews still pending — the only texts sent to the model."""
        sql = """SELECT r.review_id, r.review_text FROM reviews r
                 JOIN text_map m ON m.review_id = r.review_id AND m.is_canonical = 1
                 JOIN records s ON s.review_id = r.review_id AND s.status = 'pending'
                 ORDER BY r.row_index"""
        rows = self.con.execute(sql).fetchall()
        return rows[: self.limit] if self.limit else rows

    def batches(self, rows):
        for i in range(0, len(rows), self.batch_size):
            yield rows[i:i + self.batch_size]

    def preview(self):
        rows = self.pending()
        tokens = requests = 0
        for b in self.batches(rows):
            state, qs, _, _ = build_request(b, self.layout)
            tokens += estimate_tokens(state, qs)
            requests += 1
        usd = budget.cost(PROVIDER, tokens, 0)
        return {"layout": self.layout, "label_config": self.config, "phase": self.phase, "reviews_to_send": len(rows),
                "requests": requests, "estimated_input_tokens": tokens, "estimated_cost_usd": round(usd, 6),
                "reserved_with_safety_margin_usd": round(usd * RESERVE_FACTOR, 6),
                "price": f"${budget.price(PROVIDER)[0]}/1M input tokens, output free",
                "jev_spent_so_far_usd": round(budget.spent(PROVIDER), 6),
                "openai_spent_so_far_usd": round(budget.spent("openai"), 6),
                "project_total_spent_usd": round(budget.spent(), 6),
                "run_cap_usd": self.guard.run_cap}

    def log_call(self, **event):
        event = {"ts": now(), "role": "enrich", "model": MODEL, "phase": self.phase,
                 "label_config": self.config, **event}
        with open(self.calls_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def call(self, batch):
        """One logical request with bounded retries on transient API errors. Each attempt is logged."""
        from typesafe_sdk import RetryPolicy, TypeSafeClient, TypeSafeError
        state, questions, keymap, quote_options = build_request(batch, self.layout)
        est = estimate_tokens(state, questions)
        self.guard.check(budget.cost(PROVIDER, est, 0) * RESERVE_FACTOR)   # raises BudgetExceeded
        ids = [rid for rid, _ in batch]
        for attempt in range(1, API_ATTEMPTS + 1):
            started = time.time()
            try:
                with TypeSafeClient(model=MODEL, retry=RetryPolicy(max_retries=0), timeout=60) as client:
                    resp = client.system_one(state=state, questions=questions)
                u = resp.usage
                tin, tout = u.input_tokens or 0, u.output_tokens or 0
                usd = budget.record(PROVIDER, resp.model, "enrich", resp.request_id, tin, tout)
                self.guard.add(usd)
                self.log_call(request_id=resp.request_id, review_ids=ids, outcome="succeeded", attempt=attempt,
                              input_tokens=tin, output_tokens=tout, estimated_input_tokens=est,
                              cost_usd=round(usd, 8), seconds=round(time.time() - started, 3), model=resp.model)
                return resp, keymap, quote_options
            except TypeSafeError as e:
                local_id = f"local-{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
                self.log_call(request_id=local_id, review_ids=ids, outcome="failed", attempt=attempt,
                              input_tokens=0, output_tokens=0, usage_note="no usage reported for failed call",
                              error=f"{type(e).__name__}: {str(e)[:200]}", seconds=round(time.time() - started, 3))
                if attempt == API_ATTEMPTS:
                    raise
                time.sleep(min(8, 0.5 * 2 ** attempt) + random.uniform(0, 0.5))

    def save(self, good, bad, final):
        """Atomic per batch: labels + statuses commit together or not at all."""
        with self.con:
            for row in good.values():
                self.con.execute("INSERT OR REPLACE INTO labels VALUES (:review_id,:topic,:intent,:severity,:sentiment,"
                                 ":entities,:evidence_quote,:needs_review,:label_config,:confidences,:request_id,"
                                 ":cache_source_id,:created_at)", row)
                self.con.execute("UPDATE records SET status='completed', reason=NULL, attempts=attempts+1, "
                                 "updated_at=? WHERE review_id=?", (now(), row["review_id"]))
            for rid, reason in bad.items():
                if final:
                    self.con.execute("UPDATE records SET status='quarantined', reason=?, attempts=attempts+1, "
                                     "updated_at=? WHERE review_id=?", (reason + " (after 1 retry)", now(), rid))
                else:
                    self.con.execute("UPDATE records SET attempts=attempts+1, updated_at=? WHERE review_id=?",
                                     (now(), rid))

    def run(self):
        rows = self.pending()
        texts = dict(rows)
        stats = {"requests": 0, "completed": 0, "quarantined": 0, "stopped_reason": None}
        started = time.time()
        try:
            for b in self.batches(rows):
                resp, keymap, qopts = self.call(b)
                stats["requests"] += 1
                good, bad = parse(resp.answers, keymap, qopts, texts, self.layout, resp.request_id)
                self.save(good, bad, final=False)
                stats["completed"] += len(good)
                if bad:  # retry invalid output once, then quarantine
                    retry = [(rid, texts[rid]) for rid in bad]
                    resp2, keymap2, qopts2 = self.call(retry)
                    stats["requests"] += 1
                    good2, bad2 = parse(resp2.answers, keymap2, qopts2, texts, self.layout, resp2.request_id)
                    self.save(good2, bad2, final=True)
                    stats["completed"] += len(good2)
                    stats["quarantined"] += len(bad2)
        except budget.BudgetExceeded as e:
            stats["stopped_reason"] = f"budget: {e}"
        stats["aliases_completed_from_cache"] = self.propagate()
        stats["run_spent_usd"] = round(self.guard.run_spent, 6)
        stats["seconds"] = round(time.time() - started, 2)
        return stats

    def propagate(self):
        """Copy a completed canonical's label to its exact-duplicate aliases (cache_source_id = canonical)."""
        with self.con:
            cur = self.con.execute("""
                INSERT INTO labels
                SELECT m.review_id, l.topic, l.intent, l.severity, l.sentiment, l.entities, l.evidence_quote,
                       l.needs_review, l.label_config, l.confidences, NULL, l.review_id, ?
                FROM text_map m
                JOIN labels l ON l.review_id = m.canonical_review_id AND l.label_config = ?
                JOIN records s ON s.review_id = m.review_id AND s.status = 'pending'
                WHERE m.is_canonical = 0""", (now(), self.config))
            n = cur.rowcount
            self.con.execute("""UPDATE records SET status='completed', updated_at=?
                                WHERE status='pending' AND review_id IN (SELECT review_id FROM labels)""", (now(),))
        return n
