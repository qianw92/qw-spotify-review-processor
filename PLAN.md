# Project Plan

**Due:** Oct 13, 2026, 11:59 pm PT (7 days from Oct 6)
**Checkpoint (Class 7):** bring the golden 50, a finished 500-review run, evaluation results, and the cost calculator.

Each step lists **what you're doing** and **what it produces**. Each output says in plain words what it is.
Mark a step `[x]` when it's done.

---

## Phase 0: Set up the project (Day 1)

### [ ] Step 0.1: Create the repo and protect secrets
**What you're doing:** Make a GitHub repo and set it up so API keys can never be uploaded by accident.
**Outputs:**
- `.gitignore`: tells Git to never upload the `.env` file that holds real keys
- `.env.example`: a blank template listing which keys are needed, with no real values
- `.env` (local only, never committed): your real keys

### [ ] Step 0.2: Download the dataset
**What you're doing:** Download the course ZIP, unzip it into `data/`, and read `GRADING_CONTRACT.md` and `COST_CALCULATOR.md`. These two files contain the exact rules the grader checks.
**Outputs:**
- `data/` folder (not committed): the review CSV plus sample files like `cost_100.csv` and `golden_50_to_label.csv`

### [ ] Step 0.3: Choose tools
**What you're doing:** Pick a programming language, an AI model for labeling (a cheap, small one), a database, and a hosting service for the dashboard.
**Outputs:**
- Notes in README section 8 explaining the choices

---

## Phase 1: Understand the data (Day 1)

### [ ] Step 1.1: Ingest and profile all 660,622 reviews
**What you're doing:** Use code (no AI) to read every row, count everything, and check for problems: empty reviews, missing versions, duplicate IDs, and duplicate texts.
**Outputs:**
- `outputs/data_manifest.json`: an "ID card" for the input file (its fingerprint/checksum, size and row count) so we can prove which data we used
- `outputs/ingestion_report.json`: a health check of the data (how many rows, how many are empty or missing values, the date range)
- `outputs/quarantine.jsonl`: the 13 empty reviews, set aside with a reason
- Pending queue: the list of review IDs still waiting to be labeled

### [ ] Step 1.2: Find duplicate texts
**What you're doing:** Group identical review texts so the AI labels each unique text only once. This cuts the work from 660,609 reviews to 484,189 unique texts.
**Outputs:**
- A mapping from each review ID to its unique text, so every original ID is still tracked

---

## Phase 2: Define labels and hand-label (Day 1–2)

### [ ] Step 2.1: Write the label rules
**What you're doing:** Write down the 8 topics, 5 intents and 5 severity levels, with examples, following `GRADING_CONTRACT.md` exactly.
**Outputs:**
- `schema/labels.md`: the rulebook for how to label a review
- `schema/record_schema.json`: the exact format every labeled review must follow

### [ ] Step 2.2: Hand-label the golden 50
**What you're doing:** You read 50 reviews and label them yourself, without AI help. These are the "answer key" for testing the AI. Never show them to the AI as examples.
**Outputs:**
- `evals/golden/golden_50_labeled.csv`: your 50 human labels

---

## Phase 3: Build the labeling pipeline (Day 2–3)

### [ ] Step 3.1: Build the enricher (Stage 2: Classify)
**What you're doing:** Write code that sends batches of up to 50 reviews to the AI and gets back labels. Code then checks each answer: correct format, allowed values, and a quote that really appears in the review. Bad answers are retried once, then quarantined.
**Outputs:**
- `prompts/enricher_v1.md`: the instructions given to the AI
- `outputs/enriched.jsonl`: one labeled record per review

### [ ] Step 3.2: Add saving, caching and resume
**What you're doing:** Save results after every batch, so a crash loses nothing and a restart skips finished work. Reuse labels for duplicate texts.
**Outputs:**
- A status for every review (pending, completed or quarantined)
- `outputs/run_log.jsonl`: a diary of every AI call (time, tokens, cost, success or failure)

### [ ] Step 3.3: Add safety limits
**What you're doing:** Add a spending cap, a max number of workers, a token cap and retry limits. The pipeline stops cleanly when it hits a limit.
**Outputs:**
- Settings in a config file, documented in README section 10

---

## Phase 4: Cost calculator and pilots (Day 3)

### [ ] Step 4.1: Run the 100-review pilot (cold, then warm)
**What you're doing:** Run the whole pipeline on `cost_100.csv` with an empty cache and 1 worker, and measure real cost and time. Then run it again: it should make 0 new labeling calls because everything is already saved.
**Outputs:**
- `cost/pilot_records.jsonl`: the result for each of the 100 reviews
- `cost/pilot_calls.jsonl`: every AI call made, including failures
- `cost/usage.csv`: tokens used per call

### [ ] Step 4.2: Build the calculator
**What you're doing:** Write a tool that recalculates cost from saved usage and editable prices without calling the AI. It also projects full-run cost and time and warns if the projection goes over budget.
**Outputs:**
- `cost/rates.csv`: model prices, with the date and source link for each
- `cost/report.md`: measured results plus full-run estimates (base, conservative, and no-reuse)
- A replay command anyone can run for free

### [ ] Step 4.3: Run 500 reviews (Class 7 checkpoint)
**What you're doing:** Run `checkpoint_500.csv` and update the cost estimate.
**Outputs:**
- Updated `cost/report.md` with the 500-review numbers

---

## Phase 5: Evaluate quality (Day 3–4)

### [ ] Step 5.1: Compare AI labels with the golden 50
**What you're doing:** Run the AI on the golden 50 and use code to compare its answers with yours, field by field. Study where it got things wrong.
**Outputs:**
- `evals/golden/results.csv`: a side-by-side comparison of your labels and the AI's labels
- `evals/golden/report.md`: agreement scores, a confusion table, and an explanation of the mistakes

### [ ] Step 5.2: Build the verifier (Stage 3)
**What you're doing:** A second AI labels a random sample without seeing the first AI's answers. Code compares the two, and you look into the disagreements.
**Outputs:**
- `prompts/verifier_v1.md`: the verifier's instructions
- `evals/verifier/disagreements.csv`: cases where the two AIs disagreed, with notes

### [ ] Step 5.3: Run system tests
**What you're doing:** Break things on purpose: plant a wrong label, hide an instruction in a fake review, send malformed output, and simulate an API error. Record what actually happened.
**Outputs:**
- `evals/system_tests/results.md`: each test with its expected and actual result

---

## Phase 6: Scale up and do the full run (Day 4–5)

### [ ] Step 6.1: Run 10,000 reviews
**What you're doing:** Run `analysis_10000.csv`, refresh the cost estimate, and confirm the full run fits the budget.
**Outputs:**
- Updated `cost/report.md`

### [ ] Step 6.2: Full run plus an interruption demo
**What you're doing:** Run all 660,622 reviews. Partway through, stop it on purpose (record your screen), then resume, to show it continues without paying again for finished reviews.
**Outputs:**
- `outputs/enriched.jsonl`: labels for every review
- `outputs/run_summary.json`: totals for counts, cost, time and failures
- `grading/checkpoint_before.json` / `grading/checkpoint_after.json`: snapshots taken before and after the interruption
- A screen recording of the interruption and resume

---

## Phase 7: Group, rank and write the memo (Day 5)

### [ ] Step 7.1: Group complaints into issues (Stage 4)
**What you're doing:** Code groups complaint and cancellation reviews into issues. The AI may suggest names for the issues. The mapping is saved so ranking never needs the AI again.
**Outputs:**
- `outputs/issues.csv`: the list of issues, each with a stable ID
- `grading/membership.csv`: which reviews belong to which issue

### [ ] Step 7.2: Rank issues (Stage 5)
**What you're doing:** Code scores each issue as count × average severity and sorts from highest to lowest.
**Outputs:**
- `outputs/aggregates.csv`: counts and averages per issue
- `grading/ranking.csv`: the final ranked list

### [ ] Step 7.3: Write the memo (Stage 6)
**What you're doing:** The AI writes a recommendation using only the ranking and a small set of example reviews. Code checks that every number and ID it cites is real. You then read it and edit it.
**Outputs:**
- `memo.md`: the recommendation to Spotify
- `grading/claims.csv`: every number in the memo, linked to where it came from

---

## Phase 8: Database, backend and dashboard (Day 6)

### [ ] Step 8.1: Load the results into a database
**What you're doing:** Put the labeled reviews, rankings and recommendations into a hosted database.
**Outputs:**
- Database tables, plus a load script

### [ ] Step 8.2: Deploy the backend
**What you're doing:** Build a small server that reads from the database and sends the data to the dashboard.
**Outputs:**
- A live backend URL

### [ ] Step 8.3: Deploy the dashboard
**What you're doing:** Build a website showing overall metrics, issue rankings, and AI recommendations with links to supporting reviews.
**Outputs:**
- A live dashboard URL

---

## Phase 9: Package and submit (Day 7)

### [ ] Step 9.1: Build the grading export and run the checker
**What you're doing:** Put the required files in `grading/` in the exact format the grader expects, then run `check_submission.py` to self-check.
**Outputs:**
- `grading/`: `run.json`, `ingestion.json`, `records.jsonl`, `membership.csv`, `ranking.csv`, `claims.csv`, `calls.jsonl`, checkpoints

### [ ] Step 9.2: Finish the README
**What you're doing:** Replace every `TODO` with real numbers and links. Fill in the end-to-end trace and the architecture diagram.
**Outputs:**
- A completed `README.md`

### [ ] Step 9.3: Final checks and submit
**What you're doing:** Open the repo while logged out to confirm everything is public, check that no keys were committed, test the dashboard, and submit the repo URL on the course portal.
**Outputs:**
- The submitted GitHub URL
