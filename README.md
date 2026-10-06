# Spotify Review Multi-Agent Pipeline

Turning 660,622 real Spotify reviews into a product-priority recommendation backed by traceable evidence.

---

## 1. Overview

> What we're doing and the answer we found, plus links to the live dashboard and the main files.

**Question.** Imagine advising Spotify at the end of the review window (May 2022 – Nov 2023): where should next quarter's product effort go? The options are access, usability, playback, or billing/support.

**Answer.** TODO: one-sentence recommendation (e.g., "Prioritize ___ : issue `ISS-___` ranks #1 with ___ complaints and mean severity ___ [claim `C-___`].") See the full [decision memo](memo.md).

**What this repo does.** A staged, multi-agent pipeline coordinated by code:

1. **Prepare:** code ingests and profiles every row, removes duplicate texts, and quarantines empty reviews
2. **Classify:** an enricher model labels topic, intent, severity, sentiment, entities and an evidence quote, with at most 50 reviews per request
3. **Verify:** an independent verifier model re-labels a random sample without seeing the first labels
4. **Group:** code (plus a bounded model for naming) assigns reviews to stable issues
5. **Rank:** code computes `priority = complaint_count × mean_severity`
6. **Recommend:** a memo-writer model works only from the saved aggregates and an evidence pack, and code checks every cited ID and number

Results are stored in a database, served by a deployed backend, and shown on a live dashboard.

| | |
|---|---|
| **Live dashboard** | TODO: `https://...` |
| **Access instructions** | TODO: public / test login / other |
| **Backend API** | TODO: `https://...` |
| **Final run ID** | TODO: `run_...` |
| **Grading export** | [`grading/`](grading/) (TODO: release asset link if large files are hosted externally) |
| **Decision memo** | [`memo.md`](memo.md) |

**Scope.** This is historical, self-selected Google Play review data. It contains no revenue, plan tier or confirmed cancellations. Cancellation language is *expressed intent*, not observed churn.

---

## 2. Results Summary

> The key numbers in one table: how many reviews we processed, how accurate the labels were, and what it cost.

| Metric | Value | Source |
|---|---|---|
| Source rows ingested | TODO (expected 660,622) | TODO: `outputs/ingestion_report.json` |
| Nonempty reviews | TODO (expected 660,609) | TODO: `outputs/ingestion_report.json` |
| Completed classifications | TODO | TODO: `grading/records.jsonl` |
| Quarantined: empty text | TODO (expected 13) | TODO: `outputs/quarantine.jsonl` |
| Quarantined: other failures | TODO | TODO: `outputs/quarantine.jsonl` |
| Distinct texts classified (exact-text cache reuse) | TODO (expected 484,189) | TODO: `outputs/run_summary.json` |
| Golden-set topic agreement | TODO % | TODO: `evals/golden/` |
| Golden-set intent agreement | TODO % | TODO: `evals/golden/` |
| Severity exact match / MAE | TODO % / TODO | TODO: `evals/golden/` |
| Verifier disagreement rate | TODO % (n = TODO) | TODO: `evals/verifier/` |
| Full-run API cost | TODO USD (measured) | TODO: `outputs/run_summary.json` |
| Full-run wall-clock time | TODO | TODO: `outputs/run_summary.json` |
| 100-review pilot: cold / warm | TODO USD, TODO s / TODO USD, TODO s | TODO: `cost/report.md` |

*Accounted-for rows (completed + quarantined) are not the same as completed classifications. Every number in this table is measured unless marked otherwise.*

---

## 3. Rubric → Evidence Map

> A checklist for the grader. Each rubric point links to the section or file that proves we did it.

| Category | Criterion | Evidence |
|---|---|---|
| **Deliverable quality (4)** | Accessible code/setup and artifacts | [Setup](#4-setup), [How to Run](#5-how-to-run), [Repo Layout](#18-repository-layout) |
| | Clear architecture, shared schema, provenance | [Architecture](#6-architecture), [`schema/`](schema/), [`data_manifest.json`](outputs/data_manifest.json) |
| | Memo numbers linked to calculations and source evidence | [`memo.md`](memo.md), [`grading/claims.csv`](grading/claims.csv), [Trace](#14-end-to-end-trace) |
| | Coherent recommendation, alternatives, limitations | [`memo.md`](memo.md), [Limitations](#17-limitations) |
| **Testing & evaluation (3)** | 50 human labels, per-field comparison, error analysis | [Golden Set](#111-golden-set-50-human-labels), [`evals/golden/`](evals/golden/) |
| | Independent verification, planted-error and injection tests | [Verifier](#112-independent-verifier), [System Tests](#113-system-tests) |
| | Real 100-review cold/warm pilot, calculator, retry/spend/recovery controls | [Cost Calculator](#10-cost--runtime-calculator), [`cost/`](cost/) |
| **Working result (3)** | Full ingestion, record coverage, classification | [Ingestion](#9-data-ingestion--quality), [`grading/records.jsonl`](grading/) |
| | Runnable staged program, bounded calls, saved handoffs, resume | [How to Run](#5-how-to-run), [Run Evidence](#12-run-evidence--recovery) |
| | Reproducible ranking plus deployed dashboard/backend/DB with grounded AI recommendations | [Ranking](#13-grouping--ranking), [Dashboard](#16-dashboard-backend--database) |

---

## 4. Setup

> What to install, where to put the data, and how to add API keys so the project runs on your machine.

**Requirements:** TODO: language/runtime version. Dependencies are pinned in TODO: `requirements.txt` / `package.json` / lockfile.

```bash
TODO: clone + install commands
```

**Dataset.** The raw CSV is not committed. Download the [course dataset ZIP](https://drive.google.com/file/d/1P0rUoAS_wVjp3BYKqXMEyD4u0uJP1Bvf/view) and unzip it into `data/`:

| File | SHA-256 |
|---|---|
| `spotify_reviews_18months.csv` (97,400,616 bytes) | TODO |

**API keys.** Copy `.env.example` to `.env` and fill in only the keys you use. `.env` is git-ignored.

```
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
TYPESAFE_API_KEY=
TODO: any other provider variables
DATABASE_URL=
```

**No key needed for:** offline cost replay, rebuilding the ranking from saved outputs, the submission checker, and viewing the dashboard.

---

## 5. How to Run

> The commands that run the project. Free commands use saved results. Paid commands call AI models and are kept separate.

**Offline (free, no API key):**
```bash
TODO: <cmd> cost replay                  # recompute pilot cost from saved usage + cost/rates.csv
TODO: <cmd> rank --from-saved            # regenerate ranking.csv from saved records + membership, no model calls
python check_submission.py grading/      # zero-API grading self-check
```

**Paid (explicit commands only):**
```bash
TODO: <cmd> pilot --input data/cost_100.csv --workers 1 --fresh-cache   # cold run
TODO: <cmd> pilot --input data/cost_100.csv --workers 1                 # warm run, 0 new enrichment calls
TODO: <cmd> run --input <any.csv> --run-id <id> --max-spend <usd> --workers <n>
TODO: <cmd> run --run-id <id> --resume                                   # continue after interruption
```

The pipeline takes **any input CSV path** and runs all stages without manual copy-pasting. Importing or opening the calculator never makes a paid call.

---

## 6. Architecture

> How the pipeline is built: the 6 steps, which parts are plain code, which use AI, and how data moves between them.

TODO: architecture diagram (image or Mermaid) showing the 6 stages, the split between code and model work, each role's input and output, stored artifacts, stop/retry paths, and the DB → backend → dashboard path.

| Stage | Owner | Input | Output | Failure behavior | Stop condition |
|---|---|---|---|---|---|
| 1. Prepare | Code | Raw CSV | `data_manifest.json`, `ingestion_report.json`, pending IDs | Quarantine unreadable/empty rows with a reason | All rows accounted for |
| 2. Classify | Enricher model (TODO) + code validation | Batches of ≤50 pending distinct texts | `enriched.jsonl`, `quarantine.jsonl` | Retry invalid output once, then quarantine. Bounded backoff on API errors. | Queue empty, or spend/time cap reached |
| 3. Verify | Verifier model (TODO) + code comparison | Random sample of TODO records (text + rubric only) | Verifier predictions, disagreement report | TODO | Sample complete |
| 4. Group | Code + naming model (TODO) | Complaint/cancellation records | `issues.csv`, `membership.csv` | TODO | All eligible records mapped |
| 5. Rank | Code | Records + membership | `aggregates.csv`, `ranking.csv` | n/a (deterministic) | n/a |
| 6. Recommend | Memo model (TODO) + code claim checker | Aggregates + bounded evidence pack | `memo.md`, `claims.csv` | Reject unsupported IDs/numbers and regenerate (max TODO) | Claims pass the check |

**Code vs. model.** Code owns record accounting, deduplication, validation, budgets, arithmetic and ranking. Models handle only bounded language judgments. TODO: explain why each model call is needed and what code does instead.

**Orchestrator.** TODO: how dispatch, state, atomic saves after each batch, the shared spend ledger and rate limits, and logging work.

---

## 7. Label Definitions & Schema

> The fixed categories every review gets sorted into (topic, intent, severity) and the exact format each labeled record must follow.

Full definitions: TODO: [`schema/labels.md`](schema/labels.md). Prompts: [`prompts/`](prompts/) (version TODO).

**Topics:** `access`, `usability`, `playback`, `downloads`, `catalog`, `billing`, `support`, `other`. TODO: optional subtopics.

**Intents (in precedence order):** `cancellation` > `complaint` > `request` > `praise` > `unclear`

**Severity:**

| Level | Meaning | Example |
|---|---|---|
| 1 | No problem, praise, unclear, or pure feature request | TODO |
| 2 | Annoyance or generic criticism | TODO |
| 3 | Degraded or restricted function, some use remaining | TODO |
| 4 | Core task clearly blocked | TODO |
| 5 | Explicit serious financial, privacy or data harm | TODO |

Stars, angry language or cancellation intent alone do not set severity. When a review mentions several problems, choose the highest-severity specific one, then the first mentioned. A paid-plan mention alone is not `billing`.

**Record schema:** `review_id, source_sha256, status, topic, intent, sentiment (−1..1), severity (1–5), entities, evidence_quote, needs_review, label_config`

**Validation (code):** required keys, types, allowed labels, numeric ranges, exact source ID match, and `evidence_quote` must be an exact substring of the source text.

---

## 8. Models & Settings

> Which AI model does each job, what settings it uses, and why we chose it.

| Role | Provider | Model ID | Effort | Max output tokens | Prompt version |
|---|---|---|---|---|---|
| Enricher | TODO | TODO | TODO | TODO | TODO |
| Verifier | TODO | TODO | TODO | TODO | TODO |
| Grouper (naming) | TODO | TODO | TODO | TODO | TODO |
| Memo writer | TODO | TODO | TODO | TODO | TODO |
| Fallback | TODO | TODO | TODO | TODO | cap: TODO % of records |

**Why these models:** TODO: measured quality, cost and runtime comparison on development data.

---

## 9. Data Ingestion & Quality

> Reading the full review file, checking it for problems (empty, missing or duplicate data), and setting aside rows we can't use.

| Check | Expected | Observed |
|---|---|---|
| Rows | 660,622 | TODO |
| Empty review texts | 13 | TODO |
| Missing `app_version` | 159,701 | TODO |
| Duplicate review IDs | 0 | TODO |
| Distinct nonempty texts | 484,189 | TODO |
| Date range | May 2022 – Nov 2023 | TODO |
| Rating distribution | n/a | TODO |

**Quarantine rules:** TODO. **Exact-text cache:** a saved result is reused only when the model, effort, prompt and schema are unchanged. Every original ID is kept, with `cache_source_id` recording where the result came from. Details: [`ingestion_report.json`](outputs/ingestion_report.json).

---

## 10. Cost & Runtime Calculator

> We ran the pipeline on 100 reviews to measure real cost and time, then used those numbers to estimate the full run. The calculator can redo the math without paying for new AI calls.

Location: [`cost/`](cost/). Spec: `COST_CALCULATOR.md`. Report: [`cost/report.md`](cost/report.md).

**Measured 100-review pilot** (`cost_100.csv`, empty cache, 1 worker):

| | Cold | Warm |
|---|---|---|
| Wall-clock time | TODO | TODO |
| API cost | TODO | TODO |
| New enrichment calls | TODO | 0 |
| Downstream calls | TODO | TODO |

TODO: per-stage table with provider, model/effort, prompt version, batch size, workers, completed/failed, unique texts, cache hits, attempts, usage, price units and dated price links.

**Unit metrics:** cost per 1,000 inputs TODO · cost per completed record TODO · throughput TODO records/min.

**Estimate refreshes:** 500 reviews: TODO · 10,000 reviews: TODO

**Full-run projection:**

| Scenario | Cost | Time | Over budget? |
|---|---|---|---|
| Base (with reuse) | TODO | TODO | TODO |
| Conservative | TODO | TODO | TODO |
| No-reuse comparison | TODO | TODO | TODO |

**Controls:** spend limit TODO · output-token cap TODO · max workers TODO · fallback fraction TODO. API spend is reported separately from local compute costs and unknown costs.

**Evidence files:** `pilot_records.jsonl`, `pilot_calls.jsonl`, `rates.csv`, `usage.csv`, `report.md`, and replay instructions.

---

## 11. Evaluation

> Checking whether the AI labels are correct: we compare them to our own hand labels, have a second AI double-check them, and test tricky situations on purpose.

### 11.1 Golden Set (50 human labels)

> We labeled 50 reviews by hand and compared the AI's answers to ours, field by field.

TODO: labeling procedure. Golden labels never appear in prompts, examples, thresholds or grouping inputs. TODO: disclose whether golden-set results influenced any revisions, and if so, describe the fresh held-out check.

| Field | Result |
|---|---|
| Topic agreement | TODO |
| Intent agreement | TODO |
| Severity exact / MAE | TODO / TODO |
| Sentiment MAE (or tolerance ±TODO) | TODO |
| Evidence quote: exact substring / supports label | TODO / TODO |
| Unsupported entities | TODO |
| `needs_review` precision / recall | TODO |
| Ambiguous cases | TODO |

TODO: confusion table, per-topic counts, and concrete disagreements with error analysis. Files: [`evals/golden/`](evals/golden/).

### 11.2 Independent Verifier

> A second AI labels a random sample from scratch without seeing the first AI's answers. Code then compares the two to find disagreements.

TODO: sample size and how it was drawn. The verifier sees only the original text and rubric, never the enricher's answer, and code compares the two. Disagreement rate: TODO. Findings: TODO. Files: [`evals/verifier/`](evals/verifier/).

### 11.3 System Tests

> We break things on purpose (bad output, a fake instruction hidden in a review, an API error) to show the pipeline handles them safely.

| Test | Expected | Actual outcome |
|---|---|---|
| Planted wrong label (separate test copy) | Flagged by verifier | TODO |
| Injected instruction in a synthetic review | Ignored; label unaffected | TODO |
| Malformed model output | Retry once, then quarantine | TODO |
| Missing text | Quarantined with reason | TODO |
| Temporary API failure | Bounded backoff, then success or quarantine | TODO |
| Spend cap reached | Stops admitting work, saves progress | TODO |

Synthetic cases are marked and excluded from business aggregates. Files: [`evals/system_tests/`](evals/system_tests/).

---

## 12. Run Evidence & Recovery

> Proof that the full run actually happened, and that if it stops partway it picks up where it left off without paying again for finished work.

**Full run** (`TODO run_id`): stage timings, statuses, attempts, retries, failures, usage and cost are in [`run_log.jsonl`](outputs/run_log.jsonl) and [`run_summary.json`](outputs/run_summary.json).

**Interruption / resume demo:** TODO: link to the recording.

| | Before interruption | After resume |
|---|---|---|
| Completed | TODO | TODO |
| Pending | TODO | TODO |
| Quarantined | TODO | TODO |
| Paid relabels of completed IDs | n/a | 0 |

Checkpoints: [`grading/checkpoint_before.json`](grading/checkpoint_before.json), [`grading/checkpoint_after.json`](grading/checkpoint_after.json).

---

## 13. Grouping & Ranking

> Similar complaints are grouped into issues, and each issue is scored by number of complaints × average severity to rank what matters most.

**Grouping:** TODO: method. Issue IDs stay stable across reruns, and the accepted mapping is saved in [`issues.csv`](outputs/issues.csv) and [`grading/membership.csv`](grading/membership.csv).

**Baseline ranking:** `priority(issue) = complaint_count × mean_severity` (= severity_sum). It includes complaint and cancellation records, counts each review once per issue, and sorts by score descending, then issue ID ascending. Means are rounded half-up to 6 decimals.

| Rank | Issue ID | Name | Topic | Count | Mean severity | Score |
|---|---|---|---|---|---|---|
| 1 | TODO | TODO | TODO | TODO | TODO | TODO |
| 2 | TODO | TODO | TODO | TODO | TODO | TODO |
| 3 | TODO | TODO | TODO | TODO | TODO | TODO |

Full table: [`grading/ranking.csv`](grading/ranking.csv). Rebuild it with no model calls: `TODO: <cmd> rank --from-saved`.

TODO (optional): alternative business ranking, and complaint-share trends by comparable period with denominators. The first and last months are partial.

---

## 14. End-to-End Trace

> Following one real review through every step, from raw text to a claim in the memo, so a grader can see the chain of evidence.

**One real review:**

| Step | Value |
|---|---|
| Source | `review_id` TODO, row hash TODO |
| Enrichment | topic TODO, intent TODO, severity TODO, quote "TODO" |
| Verification | TODO (agree / disagree / not sampled) |
| Issue membership | `ISS-TODO` |
| Ranking | Rank TODO, score TODO |
| Memo claim | Claim `C-TODO` |

**One failed or ambiguous case:** `review_id` TODO. What happened: TODO. Handling decision: TODO.

---

## 15. Decision Memo (Summary)

> Our recommendation to Spotify in short form, with the numbers and example reviews that support it.

- **Recommendation:** TODO
- **Support:** TODO: counts, severity, score [claims `C-TODO`]
- **Alternatives considered:** TODO
- **Representative reviews:** TODO: IDs
- **Unresolved classifications disclosed:** TODO

Every material number in the memo maps to a row in [`grading/claims.csv`](grading/claims.csv), and code checks cited IDs and numbers against saved calculations. Full memo: [`memo.md`](memo.md).

---

## 16. Dashboard, Backend & Database

> A live website showing the results. Data lives in a database, a backend serves it, and the dashboard displays it.

- **Live dashboard:** TODO: URL (also listed in the [Overview](#1-overview))
- **Access:** TODO
- **Stack:** Database TODO · Backend TODO · Frontend TODO · Hosting TODO
- **Stored in the database:** processed review records, aggregates, ranking, issue membership, and AI-generated recommendations
- **Dashboard views:** overall metrics, issue rankings, and AI recommendations, each with supporting numbers and links to issue and review evidence
- **Consistency check:** TODO: how dashboard numbers were verified against saved calculations

**Load data and run locally:**
```bash
TODO: db load command
TODO: backend start command
TODO: frontend start command
```

---

## 17. Limitations

> What this analysis can't tell us and where it might be wrong.

- Reviews are self-selected and historical (May 2022 – Nov 2023, Google Play only). They are not a representative customer population.
- There is no revenue, plan tier or confirmed churn data. Cancellation is expressed intent only, so no revenue-at-risk or causal retention claims are made.
- Unresolved or quarantined records: TODO count and impact.
- The 50-review golden set is a small diagnostic sample, not a precise accuracy estimate.
- `app_version` is missing for 159,701 rows. Timestamps have no specified timezone. The first and last months are partial.
- TODO: model error patterns found during evaluation.
- TODO: any other known issues.

---

## 18. Repository Layout

> A map of the project folders and what's in each one.

```
src/            pipeline stages + orchestrator
prompts/        versioned role prompts
schema/         label definitions + output schema
evals/          golden/, verifier/, system_tests/
cost/           calculator, pilot records/calls, rates, usage, report
outputs/        manifest, ingestion report, enriched, quarantine, issues, aggregates, run logs
grading/        run.json, ingestion.json, records.jsonl, membership.csv, ranking.csv,
                claims.csv, calls.jsonl, checkpoint_before.json, checkpoint_after.json
backend/        API serving data from the database
dashboard/      frontend
memo.md
.env.example
.gitignore
```

TODO: list any large outputs hosted as release assets, with links.

---

## 19. Security

> How we keep API keys and other secrets out of the public repo.

- `.env` and `.env.*` are git-ignored, and only a blank `.env.example` is committed.
- No keys appear in code, prompts, logs, screenshots or artifacts. The frontend never handles keys.
- TODO: confirm that `git check-ignore .env` and `git ls-files -- .env '.env.*'` were run and the history was checked for secrets.

---

## 20. Data Source & License

> Where the review data comes from and the terms for using it.

BwandoWando, [*3.4 Million Spotify Google Store Reviews*](https://www.kaggle.com/datasets/bwandowando/3-4-million-spotify-google-store-reviews), Kaggle, v2, CC0 Public Domain. This repo uses the course's 18-month extract (660,622 rows). See `manifest.json` for exact boundaries and checksums.
