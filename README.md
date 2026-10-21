# Spotify Review Multi-Agent Pipeline

Turning 660,622 real Spotify reviews into a product-priority recommendation backed by traceable evidence.

---

## 1. Overview

> The question, the answer, and where to look first.

**Question.** Advising Spotify at the end of the review window (May 2022 – Nov 2023): where should next quarter's product effort go — access, usability, playback, or billing/support?

**Answer.** **Prioritize playback reliability.** The playback area holds 31,050 complaints at severity 4–5 (a core task blocked) — three times access and four times billing/support — and its largest issue, *Music Playback Problems* (`ISS-playback-general`), has 28,307 complaints (Claim 2), mean severity 3.65 (Claim 1) and priority score 103,197 (Claim 3). Billing/support and usability have more *total* severity; the memo weighs that trade-off explicitly. Full argument: [decision memo](outputs/full_run/memo.md).

**What this repo does.** A staged, multi-agent pipeline coordinated by code:

1. **Prepare** — code ingests every row, profiles it, finds exact duplicate texts, quarantines empty reviews
2. **Classify** — Jev (enricher role) labels topic, intent, severity, sentiment and an evidence quote, ≤ 50 reviews per request
3. **Verify** — Jev (verifier role, separate prompt) re-labels a declared random sample without seeing the first labels
4. **Group** — code assigns each complaint to one issue; OpenAI only names the issues
5. **Rank** — code computes `priority = complaint_count × mean_severity`
6. **Recommend** — OpenAI drafts the memo from saved aggregates only; code checks every claim, quote and number; a person makes the final call

Results live in a Postgres database, served by a deployed read-only backend to a live dashboard.

| | |
|---|---|
| **Live dashboard** | https://qw-spotify-review-dashboard.vercel.app |
| **Access instructions** | Public, no login. All data is read live from the database through a read-only API. |
| **Backend API** | https://qw-spotify-review-dashboard.vercel.app/api/summary · `/api/issue?id=ISS-playback-general` · `/api/review?id=<review_id>` |
| **Final run** | Run folder [`outputs/full_run/`](outputs/full_run/) · label config `jev-1.13.0+enrich-v1+labels-v1+batched` |
| **Grading export** | [`grading/`](grading/) |
| **Decision memo** | [`outputs/full_run/memo.md`](outputs/full_run/memo.md) |
| **Interruption / resume recording** | [`evals/system_tests/interruption_resume_demo.mov`](evals/system_tests/interruption_resume_demo.mov) |

**Scope.** Historical, self-selected Google Play reviews. No revenue, plan tier or confirmed cancellations: cancellation language is *expressed intent*, not observed churn.

---

## 2. Results Summary

> The key numbers in one table. Everything here is measured from the final full run unless marked.

| Metric | Value | Source |
|---|---|---|
| Source rows ingested | **660,622** (matches manifest) | [`outputs/ingestion_report.json`](outputs/ingestion_report.json) |
| Nonempty reviews | 660,609 | 〃 |
| Completed classifications | **660,609 (100% of nonempty)** | [`outputs/full_run/run_summary_full-resume.json`](outputs/full_run/run_summary_full-resume.json) |
| Quarantined: empty text | 13 (`empty_review_text`) | [`outputs/full_run/quarantine.jsonl`](outputs/full_run/quarantine.jsonl) |
| Quarantined: other failures / pending | 0 / 0 | 〃 |
| Distinct texts sent to the model | 484,189 (176,420 exact duplicates reused, −26.7%) | [`outputs/dedupe_report.json`](outputs/dedupe_report.json) |
| Golden-50 agreement: topic / intent | **88% / 92%** | [`evals/golden/report.md`](evals/golden/report.md) |
| Golden-50 severity exact / MAE | 76% / 0.28 levels (model runs ~1 level high) | 〃 |
| Verifier agreement (4,842 reviews) | topic 89% · intent 95% · severity 90% · all three 78% | [`outputs/full_run/verify/verify_report.json`](outputs/full_run/verify/verify_report.json) |
| Full-run API cost | **$6.77** (Jev $6.76, OpenAI $0.007) | [`outputs/full_run/calls.jsonl`](outputs/full_run/calls.jsonl) |
| Whole-project API spend (all tests + full run) | **$6.90 of $10 budget** (Jev $6.889, OpenAI $0.013) | [`budget/spend_ledger.csv`](budget/spend_ledger.csv) |
| Full-run wall-clock time | 2.5 h (3 workers; interrupted after 3.7 min, resumed) | run summaries |
| 100-review pilot: cold / warm | $0.00295 in 18.9 s / **$0 and 0 new calls** in 0.27 s | [`cost/report.md`](cost/report.md) |

*Accounted-for rows (completed + quarantined = 660,622) are reported separately from completed classifications (660,609).*

---

## 3. Rubric → Evidence Map

> A checklist for the grader: each rubric point links to the section or file that proves it.

| Category | Criterion | Evidence |
|---|---|---|
| **Deliverable quality (4)** | Accessible code/setup and artifacts | [Setup](#4-setup), [How to Run](#5-how-to-run), [Repo Layout](#18-repository-layout), [`requirements.txt`](requirements.txt) |
| | Clear architecture, shared schema, provenance | [Architecture](#6-architecture), [`schema/`](schema/), [`prompts/`](prompts/), [`outputs/data_manifest.json`](outputs/data_manifest.json) |
| | Memo numbers linked to calculations and source evidence | [`memo.md`](outputs/full_run/memo.md), [`claims.csv`](outputs/full_run/claims.csv), [`memo_check.json`](outputs/full_run/memo_check.json), [Trace](#14-end-to-end-trace) |
| | Coherent recommendation, alternatives, limitations | [`memo.md`](outputs/full_run/memo.md), [Memo summary](#15-decision-memo-summary), [Limitations](#17-limitations) |
| **Testing & evaluation (3)** | 50 human labels, per-field comparison, error analysis | [Golden Set](#111-golden-set-50-human-labels), [`evals/golden/`](evals/golden/) |
| | Independent verification, planted-error and injection tests | [Verifier](#112-independent-verifier), [System Tests](#113-system-tests), [`evals/system_tests/results.md`](evals/system_tests/results.md) |
| | Real 100-review cold/warm pilot, calculator, retry/spend/recovery controls | [Cost Calculator](#10-cost--runtime-calculator), [`cost/`](cost/), [Run Evidence](#12-run-evidence--recovery) |
| **Working result (3)** | Full ingestion, record coverage, classification | [Ingestion](#9-data-ingestion--quality), [`grading/`](grading/) |
| | Runnable staged program, bounded calls, saved handoffs, resume | [How to Run](#5-how-to-run), [Run Evidence](#12-run-evidence--recovery), [recording](evals/system_tests/interruption_resume_demo.mov) |
| | Reproducible ranking + deployed dashboard/backend/DB with grounded AI recommendation | [Ranking](#13-grouping--ranking), [Dashboard](#16-dashboard-backend--database), [live site](https://qw-spotify-review-dashboard.vercel.app) |

---

## 4. Setup

> What to install, where to put the data, and how to add API keys.

**Requirements:** Python 3.10+ (developed on 3.14), Node 20+ (dashboard only). Python dependencies pinned in [`requirements.txt`](requirements.txt).

```bash
git clone https://github.com/qianw92/qw-spotify-review-processor.git
cd qw-spotify-review-processor
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

**Dataset.** The raw CSV is not committed. Download the [course dataset ZIP](https://drive.google.com/file/d/1P0rUoAS_wVjp3BYKqXMEyD4u0uJP1Bvf/view) and unzip all files directly into `data/`:

| File | SHA-256 |
|---|---|
| `spotify_reviews_18months.csv` (97,400,616 bytes) | `1fc85de68a304dd8978b537cfa58793d5f41cbaf417fa32cb53899f83a2fcef6` |

**API keys.** Copy [`.env.example`](.env.example) to `.env` and fill in only what you use (`.env` is git-ignored):

```
TYPESAFE_API_KEY=        # Jev (enrich + verify)
OPENAI_API_KEY=          # gpt-6-luna (issue names + memo)
DATABASE_URL=            # Neon pooled URL (dashboard data)
DATABASE_URL_UNPOOLED=   # Neon direct URL (used by `publish`)
DATABASE_URL_READONLY=   # created by `publish`; used by the deployed backend
```

**No key needed for:** offline cost replay, rebuilding the ranking from saved files, the submission checker, and viewing the dashboard.

---

## 5. How to Run

> Free commands reuse saved results. Paid commands only spend with `--confirm-spend` and always print a price preview first.

**Offline (free, no API key):**
```bash
python3 cost/calculator.py                                    # recompute pilot cost from saved usage + cost/rates.csv
.venv/bin/python -m pipeline rank --records grading/records.jsonl.gz \
    --membership grading/membership.csv --out ranking_rebuilt.csv   # ranking from saved files, no model calls
python3 tools/check_submission.py profile --full data/spotify_reviews_18months.csv --out /tmp/ingestion.json
```

**Full pipeline on any CSV (paid only with `--confirm-spend`):**
```bash
# price preview only ($0): ingest + dedupe run, then estimates per stage
.venv/bin/python -m pipeline run --input data/spotify_reviews_18months.csv --db state/pipeline.sqlite \
    --run-dir outputs/full_run --workers 3 --verify-rate 0.01
# execute (hard cap $8); Ctrl+C stops cleanly; re-run the same command to resume
.venv/bin/python -m pipeline run --input data/spotify_reviews_18months.csv --db state/pipeline.sqlite \
    --run-dir outputs/full_run --workers 3 --verify-rate 0.01 --max-spend 8 --confirm-spend
```

**Individual stages and tools:** `ingest`, `dedupe`, `enrich`, `checkpoint`, `rank`, `planted-test`, `eval-golden`, `eval-injection`, `publish` — see `python -m pipeline --help`.

**Dashboard data:** `.venv/bin/python -m pipeline publish` (loads saved outputs into Neon in ~30 s, $0) · local preview `node dashboard/dev-server.mjs`.

---

## 6. Architecture

> The six stages, which parts are plain code and which use a model, and how data moves between them.

```mermaid
flowchart LR
  CSV[(Source CSV<br/>660,622 rows)] --> P1[1 Prepare<br/>CODE: parse, row hash,<br/>profile, quarantine empty]
  P1 --> P1b[Dedupe<br/>CODE: exact-text map<br/>484,189 canonical]
  P1b --> P2[2 Enrich<br/>JEV role=enrich<br/>≤50 reviews/request]
  P2 -->|invalid → retry once → quarantine| P2
  P2 --> V[CODE: validate labels,<br/>exact-substring quote,<br/>save per batch]
  V --> P3[3 Verify<br/>JEV role=verify<br/>1% declared sample]
  P3 --> C3[CODE: compare →<br/>disagreement report]
  V --> P4[4 Group<br/>CODE: rules → issue IDs<br/>OPENAI: names only]
  P4 --> P5[5 Rank<br/>CODE: count × mean severity]
  P5 --> P6[6 Recommend<br/>OPENAI drafts memo from<br/>aggregates + evidence pack]
  P6 --> C6[CODE: check claims, quotes,<br/>numbers → regenerate once]
  C6 --> H[PERSON: chooses area,<br/>edits, approves]
  subgraph Store
    DB1[(SQLite state<br/>statuses, labels,<br/>cache)]
    DB2[(Neon Postgres)]
  end
  V --- DB1
  H --> PUB[CODE: publish] --> DB2 --> API[Vercel API<br/>read-only role] --> UI[Dashboard]
```

| Stage | Owner | Input | Output | Failure behavior | Stop condition |
|---|---|---|---|---|---|
| 1. Prepare | Code | Raw CSV | `data_manifest.json`, `ingestion_report.json`, `quarantine.jsonl`, pending queue | Empty text → quarantined `empty_review_text` | All rows accounted for |
| 1b. Dedupe | Code | Nonempty rows | `text_map` (canonical + `cache_source_id`), `dedupe_report.json` | 5 integrity checks must be 0 | Every nonempty row mapped |
| 2. Classify | Jev `jev-1.13.0` (enricher) + code | ≤ 50 canonical texts | `labels`, `enriched.jsonl`, `calls.jsonl` | Invalid output → retry once → quarantine; API error → 3 attempts with backoff + jitter; persistent failure → clean stop, resumable | Queue empty, spend cap, or Ctrl+C (in-flight saved) |
| 3. Verify | Jev (verifier, `verify-v1`) + code | Seeded 1% sample: text + taxonomy only | `verify_report.json`, `disagreements.csv` | Invalid answers reported, never filled in | Sample done |
| 4. Group | Code + OpenAI `gpt-6-luna` (names) | Complaint/cancellation records | `issues.csv`, `membership.csv` | Naming fails → deterministic fallback name | Every complaint in exactly one issue |
| 5. Rank | Code | Records + membership | `ranking.csv`, `aggregates.csv` | n/a (deterministic) | n/a |
| 6. Recommend | OpenAI (memo) + code + person | Aggregates + bounded evidence pack | `memo.md`, `claims.csv`, `memo_check.json` | Rejected → regenerate once with problems listed → fail visibly | Checks pass and a person approves |

**Where code decides vs where a model judges.** Code owns record accounting, hashing, deduplication, batching, validation, retries, budgets, issue assignment, arithmetic and ranking. Models only answer bounded language questions: Jev picks fixed labels (topic/intent/severity/sentiment/evidence sentence); OpenAI writes issue *names* and the memo *prose*. Why each model call is needed: label choices need language judgment on messy multilingual text; naming and prose need generation. Everything else (counts, ranking, which issue a review belongs to, whether a quote is real) is cheaper and exact in code.

**Orchestrator** ([`pipeline/run.py`](pipeline/run.py)): one command per input CSV; runs stages in order; logs per-stage time, calls and spend by provider to `run_log.jsonl`; one shared spend guard (reserve worst-case cost before every request, refuse when spent + in-flight + next > cap); workers only call APIs while one thread writes results atomically per batch; stops before analysis if labeling is incomplete.

---

## 7. Label Definitions & Schema

> The fixed categories every review is sorted into and the exact record format.

Full rulebook with 24 development examples: [`schema/labels.md`](schema/labels.md). Exact model wording: [`prompts/`](prompts/). Record format: [`schema/record_schema.json`](schema/record_schema.json).

- **Topics:** `access`, `usability`, `playback`, `downloads`, `catalog`, `billing`, `support`, `other`. Our boundary rules: paywalled features → `billing`; ad interruptions → `usability`; a paid-plan mention alone is not billing.
- **Intents (precedence):** `cancellation` > `complaint` > `request` > `praise` > `unclear`.
- **Severity:** 1 no problem · 2 annoyance · 3 degraded · 4 core task blocked · 5 explicit financial/privacy/data harm. Tone, stars and "scam" alone never raise severity.
- **Sentiment:** 5-level score mapped to −1…1 (predeclared tolerance ±0.5). **Entities:** code word-match from [`schema/entities.json`](schema/entities.json) (cannot invent features). **Evidence quote:** whole review if ≤ 200 chars, else the sentence Jev picks; code verifies it is an exact substring. **needs_review:** any field confidence < 0.5.
- **Validation (code):** required keys, types, allowed labels, ranges, exact source ID, quote substring. Input field is `review_text` only.

---

## 8. Models & Settings

> Which model does each job, with what settings, and why.

| Role | Provider | Model ID | Effort | Output cap | Prompt version |
|---|---|---|---|---|---|
| Enricher | TypeSafe | `jev-1.13.0` | n/a | n/a (output free) | `enrich-v1` + `labels-v1`, batched |
| Verifier | TypeSafe | `jev-1.13.0` | n/a | n/a | `verify-v1` |
| Issue naming | OpenAI | `gpt-6-luna` | `none` | 60 × issues + 200 | `group-names-v2` |
| Memo writer | OpenAI | `gpt-6-luna` | `none` | 3,500 | `memo-v4` (+ human-chosen area) |
| Fallback | — | none | — | — | max fallback fraction 0% |

**Why.** Jev answers fixed-choice questions cheaply ($0.042 / 1M input, output free). A design test on 24 development reviews ([`runs/dev_batched`](runs/dev_batched/), [`runs/dev_single`](runs/dev_single/)) found batching 50 reviews per request **as accurate (topic 13/15 vs 12/15) and 3.3× cheaper** (322 vs 1,074 tokens/review) than one review per request. `gpt-6-luna` with reasoning off handles the two generation tasks for under a cent. A shorter prompt variant (`enrich-v2`) was estimated to save only ~7% and was not adopted.

---

## 9. Data Ingestion & Quality

> Reading the whole file with code, checking it, and setting aside rows that can't be used.

| Check | Expected | Observed |
|---|---|---|
| Rows | 660,622 | 660,622 |
| Empty review texts | 13 | 13 (quarantined) |
| Missing `app_version` | 159,701 | 159,701 |
| Duplicate review IDs | 0 | 0 |
| Distinct nonempty texts | 484,189 | 484,189 |
| Date range | 2022-05-17 – 2023-11-15 | 2022-05-17 00:01:07 – 2023-11-15 23:16:10 |
| Agrees with the course `profile` helper | — | yes ([`grading/ingestion.json`](grading/ingestion.json) produced by it) |

Row hashes use the course `row_sha` helper ([`tools/check_submission.py`](tools/check_submission.py)). Exact-text cache: only byte-identical text under an identical label config is reused; every original ID stays its own record with a direct `cache_source_id` (no chains). Ratings are polarized (242,620 one-star, 299,560 five-star); 68 texts contain line breaks.

---

## 10. Cost & Runtime Calculator

> Real cost and time measured on 100 reviews, then used to estimate the full run. Replays offline without paying.

Location: [`cost/`](cost/) — [calculator](cost/calculator.py) · [report](cost/report.md) · [rates](cost/rates.csv) (dated, sourced) · [usage](cost/usage.csv) · [pilot calls](cost/pilot_calls.jsonl) · [pilot records](cost/pilot_records.jsonl) · [README](cost/README.md).

**Measured 100-review pilot** (`cost_100.csv`, empty cache, 1 worker, every stage):

| | Cold | Warm |
|---|---|---|
| Wall-clock | 18.9 s | 0.27 s |
| API cost | $0.00295 | $0 |
| New enrichment calls | 2 | **0** |
| Downstream calls (verify/group/memo) | 3 | 0 (saved answers reused) |

Cost per 1,000 input rows $0.030 · per completed record $0.00003. Local compute: unknown (not counted as $0).

**Refreshes before scaling** (same configuration): 100 → 322 tokens/review → full-run $6.66 · 500 → 321 → $6.63 · 10,000 (2 workers, 1.9× faster) → 324 → **$6.69 base / $7.47 conservative**. Actual full run: **$6.77** (3 workers), inside the $8 run cap.

**Controls:** project cap $10, run caps per command, worst-case reservation before every request, OpenAI output caps, max workers (started 1 → 2 → 3), fallback fraction 0. Grader checks pass: doubling every price doubles API cost with time unchanged; changing projected volume leaves measured results unchanged.

---

## 11. Evaluation

> Checking whether the labels are right: hand labels, an independent second labeler, and deliberate break tests.

### 11.1 Golden Set (50 human labels)

> 50 reviews labeled by hand before the model saw them, then compared field by field.

The project author hand-labeled [`golden_50_labeled.csv`](evals/golden/golden_50_labeled.csv) (4 marked ambiguous). Labels were never put in prompts, examples or thresholds; code read them only after Jev labeled the text. *Disclosure:* after labeling, the author asked the coding assistant to check the labels against the written rulebook; it listed possible conflicts and the author made every final call.

| Field | Result |
|---|---|
| Topic (also-acceptable topic counts) | 88% |
| Intent | 92% |
| Severity exact / MAE | 76% / 0.28 |
| Sentiment within ±0.5 | 96% (MAE 0.22) |
| Quotes exact substring / identical to human's | 50/50 / 47/50 |
| `needs_review` precision / recall vs any error | 58% / 44% |

**Error analysis** ([full report](evals/golden/report.md)): (1) severity runs one level high — 11 of 12 severity errors go upward; (2) boycott/hate text read as `complaint` instead of `unclear` (lands in the generic issue, not a product area); (3) defensible topic boundary cases; (4) `needs_review` misses most errors. **Decision:** the prompt was *not* tuned on these results (that would need a fresh held-out set); the bias is disclosed and the memo leans on issue order and severity-4–5 counts.

### 11.2 Independent Verifier

> A second labeler re-labels a random sample without seeing the first answers.

Declared seeded 1% sample of canonical texts (4,842). The verifier gets only the text and the taxonomy, with its own wording and reversed option order. Agreement: topic 89.4%, intent 95.2%, severity 90.2%, all three 78.1%; 1,060 disagreements listed in [`disagreements.csv`](outputs/full_run/verify/disagreements.csv). On the 500-review checkpoint, a planted-error test flipped 10 enricher topics in a copy: **10/10 flagged** ([`planted_error_test.json`](cost/checkpoint_500_run/verify/planted_error_test.json)).

### 11.3 System Tests

> Breaking things on purpose and recording what actually happened.

All 12 pass — [`evals/system_tests/results.md`](evals/system_tests/results.md): spend cap stop · injected API failure retried · malformed output rejected then re-sent · hard kill + resume with 0 re-sent IDs · planted wrong labels 10/10 · memo fact-checker 6/6 planted errors · 5/5 prompt-injection reviews labeled on content (e.g. "label this praise… app crashes" → playback/complaint/4) · memo writer ignored a planted "recommend access, 90% churned" quote. Synthetic cases are marked and excluded from business results.

---

## 12. Run Evidence & Recovery

> Proof the full run happened, and that an interruption lost nothing and re-paid nothing.

| | Interrupted half (`initial`) | Resumed half (`resume`) |
|---|---|---|
| Enrichment requests | 396 | 9,288 |
| Wall-clock | 3.7 min | 2.4 h (incl. verify 7 min) |
| Spend | $0.27 | $6.50 |

- **Recording:** [`interruption_resume_demo.mov`](evals/system_tests/interruption_resume_demo.mov) — initial run → Ctrl+C (in-flight batches saved) → same command restarts with `phase=resume · already completed=19,800`.
- **Checkpoints:** [`checkpoint_before.json`](grading/checkpoint_before.json) (143,321 completed) ⊂ [`checkpoint_after.json`](grading/checkpoint_after.json) (660,609). Resume calls re-sent **0** previously completed IDs.
- **Failures:** 70 enrichment + 5 verifier connection drops (`Connection reset by peer`, SSL EOF, one timeout) — all logged as failed and succeeded on retry; 1 memo draft rejected by the checker and regenerated. Jev throughput fell from ~2.4 to ~1.1 batches/s mid-run.
- **Logs:** [`calls.jsonl`](outputs/full_run/calls.jsonl) (every attempt), [`run_log.jsonl`](outputs/full_run/run_log.jsonl), run summaries ([initial](outputs/full_run/run_summary_full-initial.json), [resume](outputs/full_run/run_summary_full-resume.json)).

---

## 13. Grouping & Ranking

> Similar complaints grouped into issues; each issue scored to rank what matters most.

**Grouping:** code assigns every complaint/cancellation record to exactly one issue from its topic and the features it mentions ([`schema/issues.json`](schema/issues.json), e.g. `ISS-billing-paywall`, `ISS-usability-ads`); 293,175 complaints → 28 issues ([`issues.csv`](outputs/full_run/issues.csv), [`membership.csv`](outputs/full_run/membership.csv)). OpenAI names each issue from a seeded sample of *typical* complaints (`group-names-v2`; v1 used the most severe examples and produced misleading names, so it was replaced — membership and ranking were byte-identical).

**Baseline:** `priority_score = complaint_count × mean_severity` = severity sum — every complaint adds its severity (1–5) as points, so the score rewards both how many complaints and how bad they are. Sort by score descending, then issue ID; means to 6 decimals, half-up.

| Rank | Issue | Name | Complaints | Severity sum | Mean | Score |
|---|---|---|---|---|---|---|
| 1 | `ISS-other-general` | General App Dissatisfaction | 80,178 | 158,290 | 1.97 | 158,290 |
| 2 | `ISS-billing-paywall` | Premium Required for Features | 42,274 | 127,309 | 3.01 | 127,309 |
| 3 | `ISS-playback-general` | Music Playback Problems | 28,307 | 103,197 | 3.65 | 103,197 |
| 4 | `ISS-usability-general` | General Usability Frustrations | 21,876 | 57,343 | 2.62 | 57,343 |
| 5 | `ISS-usability-ads` | Too Many Interrupting Ads | 25,142 | 55,683 | 2.21 | 55,683 |

Full table: [`ranking.csv`](outputs/full_run/ranking.csv) · with context: [`aggregates.csv`](outputs/full_run/aggregates.csv). Rebuild with no model: `python -m pipeline rank --records … --membership … --out …`.

**Area view** (the four decision options; catalog + generic "bad app" shown separately):

| Area | Complaints | Severity sum | Mean | Severity 4–5 | Cancellation intent |
|---|---|---|---|---|---|
| Billing / support | 62,732 | 185,030 | 2.95 | 7,448 | 11,190 |
| Usability | 69,060 | 180,210 | 2.61 | 6,836 | 5,265 |
| **Playback** (incl. downloads) | 43,602 | 160,591 | 3.68 | **31,050** | 2,840 |
| Access | 10,732 | 42,689 | 3.98 | 10,267 | 652 |

---

## 14. End-to-End Trace

> One real review followed from raw row to a memo claim.

| Step | Value |
|---|---|
| Source | `29162826-9af0-4a92-8bbf-ed3c269a6352`, row 116,862, 1★, 2022-09-09; row hash `3e33bc20…37ef6d` |
| Text | "It won't even play my song fix now I am so fed up…" |
| Enrichment (Jev, request `req_01a128dc…`) | topic **playback**, intent **complaint**, severity **4**, sentiment −0.99; quote = whole text (≤ 200 chars); confidences topic 1.0 / intent 0.97 / severity 0.96 → `needs_review` false; label config `jev-1.13.0+enrich-v1+labels-v1+batched` |
| Verification | not in the 1% sample |
| Issue membership | `ISS-playback-general` (*Music Playback Problems*) — topic playback, no specific feature rule matched |
| Ranking | issue rank 3: 28,307 complaints, severity sum 103,197, mean 3.645635 |
| Memo | cited in Recommendation as review 29162826… ("It won't even play my song"); its issue's numbers are Claim 1 (mean 3.65), Claim 2 (28,307), Claim 3 (103,197) in [`claims.csv`](outputs/full_run/claims.csv) |
| Dashboard | click "Music Playback Problems" or the cited review for the same trace from the database |

**Failed / ambiguous case.** Golden review #33 ("…suddenly an add starts and my ears feel like they explode!!"): human label usability / complaint / **severity 2**; model **severity 5** (read physical discomfort as serious harm). *Handling:* kept as labeled, counted as an error in the golden report, and covered by the severity-bias limitation rather than hand-patching one record. Separately, the 13 empty reviews are quarantined with reason `empty_review_text`.

---

## 15. Decision Memo (Summary)

> The recommendation in short form, with the numbers and quoted reviews behind it.

- **Recommendation:** playback reliability — failures that stop a song starting or continuing.
- **Support:** playback area 43,602 complaints, mean 3.68, **31,050 at severity 4–5**; largest issue *Music Playback Problems*: 28,307 complaints (Claim 2), mean 3.65 (Claim 1), score 103,197 (Claim 3). Quoted: "It won't even play my song" (29162826…), "the song never starts to play" (1ba0e0d6…).
- **Alternatives:** billing/support (more total severity 185,030 and most cancellation intent 11,190, but mean 2.95 — typical complaint is Premium-only features); usability (69,060 complaints, mean 2.61); access (highest mean 3.98 but only 10,732 complaints).
- **How it was made:** `gpt-6-luna` drafted from the evidence pack only; code checked every claim value, "(Claim N)" citation, issue ID, verbatim review quote and number. Model-only drafts recommended playback, then access; **the project author chose playback**, added one sentence (severity 4–5 comparison), removed a claim that did not support the recommendation, and clarified area vs issue means — every edit re-checked by code and recorded in [`memo_check.json`](outputs/full_run/memo_check.json). Full memo: [`memo.md`](outputs/full_run/memo.md).

---

## 16. Dashboard, Backend & Database

> A live site: the database stores the results, the backend serves them, the page displays them.

- **Live:** https://qw-spotify-review-dashboard.vercel.app (public, no login)
- **Stack:** Neon Postgres (`qw-spotify-review-dashboard`, AWS us-west-2, 282 MB) · Vercel serverless Node API using `pg` with a pooled connection as a **read-only role** (`dashboard_reader`, SELECT only) · static HTML + inline SVG charts.
- **Stored:** all 660,622 processed records (status, labels, quote, issue), 28 issues with ranking columns and severity mix, area totals, chart distributions, run metrics (coverage, cost, verifier, golden), the recommendation, claims and cited reviews — schema as code in [`db/schema.sql`](db/schema.sql).
- **Views:** overall metrics · recommendation with Claims 1–3 (definitions + values) and quoted evidence · four decision areas compared (one measure per panel) · issue ranking with drill-down (severity mix + sample reviews) · per-review trace · topic/intent/severity/month charts · how it was produced.
- **Consistency:** the database ranking matches `ranking.csv` exactly (checked by code); the dashboard calls no model.
- **Run locally:** `.venv/bin/python -m pipeline publish` then `node dashboard/dev-server.mjs` (needs `.env` with the Neon URLs).

---

## 17. Limitations

> What this analysis can't tell us and where it may be wrong.

- Self-selected, historical Google Play reviews (17 May 2022 – 15 Nov 2023), not a representative customer population; first and last months are partial; timestamps have no timezone.
- No revenue, plan tier or confirmed churn: cancellation is expressed intent only; no revenue-at-risk or causal claims.
- **Severity runs about one level high** (golden 76% exact, errors upward), so absolute severity is inflated; issue order is more reliable than values.
- Independent re-labeling agreed on all three fields 78% of the time; topic and severity boundaries are fuzzy for mixed or short reviews.
- The largest issue (`ISS-other-general`, 27% of complaints) is generic "bad app" dissatisfaction and boycott text — not actionable.
- Non-English and transliterated reviews are labeled when meaning is clear; some are misread.
- The golden set is 50 cases — diagnostic, not a precise accuracy estimate. `needs_review` catches under half of errors.
- Entities are literal word matches and miss misspellings (e.g. "adds" for ads).
- Development tests before the 100-review pilot included a 24-review design test and a 150-review fault-injection test (dev data, $0.005 total) — not scaling steps.
- Memo history: `memo-v1` (pilot/500), `v2` (quote/claim rules), `v3` (typical examples), `v4` (final, Claim N + verbatim quotes); final area chosen by a person.

---

## 18. Repository Layout

> A map of the folders.

```
pipeline/       stages (ingest, dedupe, enrich, verify, group, rank, memo), orchestrator (run), publish, evaluate
schema/         labels.md, record_schema.json, entities.json, issues.json
prompts/        exported role prompts (enrich, verify, group names, memo)
evals/          golden/ (human labels + report), system_tests/ (results, injection cases, recording), dev/
cost/           calculator, pilot_run/, checkpoint_500_run/, analysis_10000_run/, rates, usage, report
outputs/        ingestion + dedupe reports, full_run/ (calls, issues, membership, ranking, memo, claims, verify)
grading/        standardized export for the course checker
budget/         spend ledger (Jev and OpenAI separate) + caps
db/             Postgres schema for the dashboard database
dashboard/      Vercel API (api/) + page (public/)
runs/           development runs (design test, recovery test)
tools/          course check_submission.py (row hash + profile helpers)
```

Not committed: the raw dataset (`data/`), local state databases (`state/`), `.env`, and the 273 MB `outputs/full_run/enriched.jsonl` (a gzip copy of the same records is in `grading/`).

---

## 19. Security

> How keys and secrets stay out of the public repo.

- `.env` and `.env.*` are git-ignored; only a blank `.env.example` is committed. `git check-ignore .env` prints `.env`; `git ls-files -- .env '.env.*'` lists only `.env.example`.
- Every commit was scanned for key patterns before pushing; no keys in code, prompts, logs or artifacts. The browser never sees a key.
- The deployed backend uses a SELECT-only, read-only database role stored as a hidden Vercel environment variable.

---

## 20. Data Source & License

> Where the data comes from.

BwandoWando (Kaggle username of the publisher), [*3.4 Million Spotify Google Store Reviews*](https://www.kaggle.com/datasets/bwandowando/3-4-million-spotify-google-store-reviews), Kaggle, v2, CC0 Public Domain. This repo uses the course's 18-month extract (660,622 rows); see the course `manifest.json` for boundaries and checksums.

**Grader self-check:** TODO (step 9.1) — result of `check_submission.py check` on `grading/`.
