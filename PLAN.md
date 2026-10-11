# Project Plan

**Due:** Oct 13, 2026, 11:59 pm PT · **Budget:** $10 total (Jev + OpenAI, tracked separately in `budget/spend_ledger.csv`)

## 📍 Where we are

| | |
|---|---|
| **Current step** | **5.1 + 5.3 — golden-50 evaluation and system tests** (awaiting price approval) |
| **Next paid step** | 5.1 + 5.3 (~$0.002) |
| **Progress** | 15 of 27 steps done |
| **Spent so far** | Jev $0.0122 · OpenAI $0.0028 · **Total $0.0150 of $10** |
| **Last updated** | Oct 10 |

**Status key:** ✅ done · 🔨 code built, still needs its full-data run · ⏳ to do

### Remaining schedule

| Day | Steps |
|---|---|
| **Oct 10–11** | 4.2 calculator → 4.3 500 reviews → 5.1 golden-50 evaluation → 5.3 system tests |
| **Oct 11–12** | 6.1 10,000 reviews → 6.2 full run + interruption recording → 7.x group/rank/memo on full data |
| **Oct 12–13** | 8.x database, backend, dashboard → 9.x grading export, checker, README, submit |

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

### ⏳ Step 5.1: Compare AI labels with the golden 50 (paid, <$0.01) ← **current**
**What you're doing:** Run Jev on the golden 50 and compare with your labels, field by field.
**Outputs:** `evals/golden/results.csv` · `evals/golden/report.md` (agreement, confusion table, error analysis)

### 🔨 Step 5.2: Build the verifier (Stage 3)
**What you're doing:** A second, independent Jev task re-labels a declared random sample; code compares.
**Outputs:** `pipeline/verify.py` (built, ran in pilot: 18/20 agree) · full-run report comes in 6.2

### ⏳ Step 5.3: Run system tests ($0–0.01)
**What you're doing:** Planted wrong labels, a hidden instruction in a fake review, malformed output, API failure — record actual outcomes.
**Outputs:** `evals/system_tests/results.md` (reuses the recovery test from 3.2/3.3)

---

## Phase 6: Scale up and do the full run

### ⏳ Step 6.1: Run 10,000 reviews (paid, ~$0.15)
**What you're doing:** Run `analysis_10000.csv`, refresh the estimate, confirm the full run fits the budget.
**Outputs:** `cost/analysis_10000_run/` · updated `cost/report.md`

### ⏳ Step 6.2: Full run + interruption demo (paid, ~$6–7)
**What you're doing:** Label all 484,189 unique texts. Stop it partway on purpose (screen recording), then resume.
**Outputs:** full run folder · `grading/checkpoint_before.json`, `checkpoint_after.json` · screen recording

---

## Phase 7: Group, rank and write the memo (full data)

### 🔨 Step 7.1: Group complaints into issues (Stage 4)
**Outputs:** `pipeline/group.py` (built, ran in pilot) · full-data `issues.csv`, `grading/membership.csv`

### 🔨 Step 7.2: Rank issues (Stage 5)
**Outputs:** `pipeline/rank.py` (built; rebuild-from-saved-files verified) · full-data `aggregates.csv`, `grading/ranking.csv`

### 🔨 Step 7.3: Write the memo (Stage 6)
**What you're doing:** OpenAI writes from the ranking + evidence pack only; code fact-checks; **you read and approve it**.
**Outputs:** `pipeline/memo.py` (built, passed checks in pilot) · full-data `memo.md`, `grading/claims.csv`

---

## Phase 8: Database, backend and dashboard

### ⏳ Step 8.1: Load the results into a database
**Outputs:** hosted Postgres (Neon) tables + load script

### ⏳ Step 8.2: Deploy the backend
**Outputs:** live API URL that reads from the database

### ⏳ Step 8.3: Deploy the dashboard
**Outputs:** live dashboard URL (metrics, issue ranking, AI recommendation with evidence links)

---

## Phase 9: Package and submit

### ⏳ Step 9.1: Build the grading export and run the checker
**Outputs:** `grading/` (run.json, ingestion.json, records.jsonl, membership.csv, ranking.csv, claims.csv, calls.jsonl, checkpoints) · self-check report

### ⏳ Step 9.2: Finish the README
**Outputs:** completed `README.md` (no TODOs; disclose the 150-review recovery test and AI-assisted golden-label consistency review)

### ⏳ Step 9.3: Final checks and submit
**Outputs:** public repo verified signed-out · no keys in history · repo URL submitted on the course portal
