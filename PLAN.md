# Project Plan

**Due:** Tue Oct 20, 2026, 11:59 pm PT (bCourses; the assignment doc said Oct 13) · **Budget:** $10 total (Jev + OpenAI, tracked separately in `budget/spend_ledger.csv`)

## 📍 Where we are

| | |
|---|---|
| **Current step** | **9.1 — grading export + checker** |
| **Open decision** | none |
| **Then** | Review memo (playback recommended vs billing/support highest severity sum) → 8.x database/backend/dashboard → 9.x grading export, README, submit |
| **Progress** | 26 of 29 steps done |
| **Spent so far** | Jev $6.889 · OpenAI $0.013 · **Total $6.902 of $10** ($3.10 left) |
| **Last updated** | Oct 19 |

**Status key:** ✅ done · 🔨 code built, still needs its full-data run · ⏳ to do

### Remaining schedule

| Day | Steps |
|---|---|
| **Oct 10–11** | ✅ 4.2–6.2 done (calculator, 500, golden eval, system tests, 10k, full run) |
| **Oct 12** | Fix issue names/memo examples → review memo → 8.x database, backend, dashboard |
| **Oct 13** | 9.x grading export (gzip records), checker, README, submit by 11:59 pm PT |

Rules for every step: explain outputs in plain words · price preview + approval before any paid run · commit after each step.

---

## Phase 0: Set up the project ✅

### ✅ Step 0.1: Create the repo and protect secrets
**What you're doing:** Make a public GitHub repo set up so API keys can never be uploaded.
**Outputs:** `.gitignore` (blocks `.env`, `data/`, `state/`) · `.env.example` (blank key names) · `.env` (your keys, local only)

### ✅ Step 0.2: Download the dataset
**What you're doing:** Download the course ZIP into `data/` and verify every file's fingerprint against `manifest.json`.
**Outputs:** `data/` (not committed) · checksum in README Setup

### ✅ Step 0.3: Choose tools
**What you're doing:** Pick the tools and test both API keys with one tiny call each.
**Outputs:** Python 3.14 · Jev `jev-1.13.0` (labeling) · OpenAI `gpt-6-luna` (naming + memo) · `outputs/smoke/` (test-call records) · `budget/` (spend tracker)

---

## Phase 1: Understand the data ✅

### ✅ Step 1.1: Ingest and profile all 660,622 reviews
**What you're doing:** Read every row with code (no AI), count everything, set aside empty reviews.
**Outputs:** `pipeline/ingest.py` · `outputs/ingestion_report.json` (all counts match the assignment) · `outputs/data_manifest.json` · `outputs/quarantine.jsonl` (13 empty) · `grading/ingestion.json` (made with the grader's helper)

### ✅ Step 1.2: Find duplicate texts
**What you're doing:** Map identical texts so each is labeled once; copies reuse the label.
**Outputs:** `pipeline/dedupe.py` · `outputs/dedupe_report.json` (484,189 unique texts; 176,420 copies; all safety checks 0)

---

## Phase 2: Define labels and hand-label ✅

### ✅ Step 2.1: Write the label rules
**What you're doing:** Write the rulebook (8 topics, 5 intents, 5 severity levels) with real examples.
**Outputs:** `schema/labels.md` · `schema/record_schema.json` · `schema/entities.json`

### ✅ Step 2.2: Hand-label the golden 50
**What you're doing:** You labeled 50 reviews by hand as the answer key (never shown to the AI).
**Outputs:** `evals/golden/golden_50_labeling.xlsx` · `evals/golden/golden_50_labeled.csv` (4 marked ambiguous)

---

## Phase 3: Build the labeling pipeline ✅

### ✅ Step 3.1: Build the enricher (Stage 2: Classify)
**What you're doing:** Code sends ≤50 reviews per Jev request, validates every answer, saves after each batch. A design test picked "batched" (as accurate, 3× cheaper).
**Outputs:** `pipeline/enrich.py` · `pipeline/rules.py` (prompt `enrich-v1`) · `pipeline/budget.py` · `evals/dev/dev_rulebook_24.csv` · `runs/dev_batched/`, `runs/dev_single/` (design test)

### ✅ Step 3.2: Add saving, caching and resume
### ✅ Step 3.3: Add safety limits
**What you're doing:** Prove a crash loses nothing, resume never re-pays, retries are bounded, and the spend cap stops the run.
**Outputs:** `runs/dev_resume/` (calls log, 3 checkpoints, `recovery_test_report.json`: 0 re-sent IDs) · `checkpoint` command

---

## Phase 4: Pilot and cost calculator

> **Order fix (Oct 10):** the official pilot must include every stage, so verify/group/rank/memo code was built first (step 4.0).
> Scaling order unchanged: 100 → 500 → 10,000 → full run.

### ✅ Step 4.0: Build verify, group, rank, memo + orchestrator ($0)
**What you're doing:** Build the remaining four stages and one `run` command that executes all of them on any CSV.
**Outputs:** `pipeline/verify.py`, `group.py`, `rank.py`, `memo.py`, `llm.py`, `export.py`, `run.py` · `schema/issues.json` · offline tests passed ($0)

### ✅ Step 4.1: Run the 100-review pilot (cold, then warm)
**What you're doing:** Run every stage on `cost_100.csv`: cold (nothing saved) then warm (should reuse everything).
**Outputs:** `cost/pilot_run/` — cold $0.00295 in 18.9 s; warm $0 in 0.27 s with **0 new calls**; memo passed all checks; verifier agreed 18/20

### ✅ Step 4.2: Build the calculator ($0)
**What you're doing:** A tool that recomputes cost from saved usage and editable prices (no API key), and projects the full run with budget warnings.
**Outputs:** `cost/rates.csv` · `cost/usage.csv` · `cost/pilot_records.jsonl` · `cost/pilot_calls.jsonl` · `cost/report.md` · offline replay command

### ✅ Step 4.3: Run 500 reviews (paid, $0.0086)
**What you're doing:** Run `checkpoint_500.csv`, refresh the estimate; test shorter question wording to cut full-run cost.
**Outputs:** `cost/checkpoint_500_run/` (500/500 completed, 321 tokens/review, verifier 43/48 all-agree, planted-error test caught 10/10) · `cost/report.md` refreshed: full run base $6.63 / conservative $7.40 · run cap raised to $8

---

## Phase 5: Evaluate quality

### ✅ Step 5.1: Compare AI labels with the golden 50 (paid, $0.00065)
**What you're doing:** Run Jev on the golden 50 and compare with your labels, field by field.
**Outputs:** `evals/golden/results.csv` · `evals/golden/summary.json` · `evals/golden/report.md` — topic 88%, intent 92%, severity exact 76% (MAE 0.28; model runs ~1 level high), sentiment within ±0.5: 96%

### ✅ Step 5.2: Build the verifier (Stage 3)
**What you're doing:** A second, independent Jev task re-labels a declared random sample; code compares.
**Outputs:** `pipeline/verify.py` · pilot 18/20 and 500-run 43/48 all-three agree · full-run report comes in 6.2

### ✅ Step 5.3: Run system tests ($0.0009)
**What you're doing:** Planted wrong labels, a hidden instruction in a fake review, malformed output, API failure — record actual outcomes.
**Outputs:** `evals/system_tests/results.md` — 12/12 pass (spend cap, API failure, malformed output, crash/resume, planted errors 10/10, memo checker 6/6, injection 6/6) · memo prompt → `memo-v2`

---

## Phase 6: Scale up and do the full run

### ✅ Step 6.1: Run 10,000 reviews (paid, $0.118)
**What you're doing:** Run `analysis_10000.csv`, refresh the estimate, confirm the full run fits the budget.
**Outputs:** `cost/analysis_10000_run/` — 10,000/10,000 completed, 0 quarantined, 2 workers (1.9× faster than 1), 1 real connection error retried OK, verifier 74% all-three agree · `cost/report.md`: full run base $6.69 / conservative $7.47

### ✅ Step 6.2: Full run + interruption demo (paid, $6.50)
**What you're doing:** Label all 484,189 unique texts. Stop it partway on purpose (screen recording), then resume.
**Outputs:** `outputs/full_run/` — 660,609 completed + 13 quarantined, 0 pending; 71 connection drops all retried · `grading/checkpoint_before.json` (143,321) → `checkpoint_after.json` (660,609), 0 re-sent · screen recording `evals/system_tests/interruption_resume_demo.mov` (4m56s) · verifier 4,842 reviews, 78% all-three agree

---

## Phase 7: Group, rank and write the memo (full data)

### ✅ Step 7.1: Group complaints into issues (Stage 4)
**Outputs:** `outputs/full_run/issues.csv`, `membership.csv` — 293,175 complaints → 28 issues · names re-generated with typical examples (`group-names-v2`, $0.0015); v1 names came from extreme examples and were misleading

### ✅ Step 7.2: Rank issues (Stage 5)
**Outputs:** `outputs/full_run/ranking.csv`, `aggregates.csv` (unchanged by the renaming)

### ✅ Step 7.3: Write the memo (Stage 6)
**What you're doing:** OpenAI writes from the ranking + evidence pack only; code fact-checks; **you read and approve it**.
**Outputs:** `outputs/full_run/memo.md` (`memo-v4`: Claim N citations, verbatim review quotes, 2-dp means) · `claims.csv` · `memo_check.json` — **human decision: playback** (author chose it over access/billing-support after reviewing drafts; model-only drafts said playback, then access)

---

## Phase 8: Database, backend and dashboard

### ✅ Step 8.1: Load the results into a database
**Outputs:** Neon project `qw-spotify-review-dashboard` (282 MB) · `db/schema.sql` · `python -m pipeline publish` (loads 660,622 rows in ~30 s) · read-only role `dashboard_reader` for the website

### ✅ Step 8.2: Deploy the backend
**Outputs:** https://qw-spotify-review-dashboard.vercel.app/api/summary (+ `/api/issue`, `/api/review`) — Vercel serverless, read-only role, secret stored as Vercel env

### ✅ Step 8.3: Deploy the dashboard
**Outputs:** **https://qw-spotify-review-dashboard.vercel.app** — public, tested logged-out; metrics, areas, ranking drill-down, review trace, memo with Claims 1–3 + definitions

---

## Phase 9: Package and submit

### ⏳ Step 9.1: Build the grading export and run the checker
**Outputs:** `grading/` (run.json, ingestion.json, records.jsonl, membership.csv, ranking.csv, claims.csv, calls.jsonl, checkpoints) · self-check report

### ⏳ Step 9.2: Finish the README
**Outputs:** completed `README.md` (no TODOs; disclose the 150-review recovery test and AI-assisted golden-label consistency review)

### ⏳ Step 9.3: Final checks and submit
**Outputs:** public repo verified signed-out · no keys in history · repo URL submitted on the course portal
