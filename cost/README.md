# Cost & runtime calculator

Everything in this folder can be checked **without an API key and without any model call**.

## Offline replay (default, $0)

```bash
python3 cost/calculator.py
```

Recomputes every pilot charge as `billed units × price per unit` from `usage.csv` and `rates.csv`, projects the full
run from `assumptions.json`, and rewrites `report.md` / `report.json`. Standard library only — no installs needed.

Try edits:

```bash
python3 cost/calculator.py --rates my_rates.csv              # e.g. double every price: API totals double, times don't
python3 cost/calculator.py --assumptions my_assumptions.json # e.g. different volume/workers: measured pilot unchanged
python3 cost/calculator.py build-evidence                    # re-extract the evidence files from pilot_run/ ($0)
```

## Paid pilot execution (explicit, separate command)

Only this spends money, and only with `--confirm-spend`. Without it, it prints a price preview and exits.

```bash
rm -rf state/pilot.sqlite* cost/pilot_run          # empty result cache for the cold run
python -m pipeline run --input data/cost_100.csv --db state/pilot.sqlite --run-dir cost/pilot_run \
  --verify-rate 0.2 --verify-min 20 --max-spend 0.02 --label cold --confirm-spend
python -m pipeline run --input data/cost_100.csv --db state/pilot.sqlite --run-dir cost/pilot_run \
  --verify-rate 0.2 --verify-min 20 --max-spend 0.02 --label warm --confirm-spend   # expect 0 new calls
python3 cost/calculator.py build-evidence && python3 cost/calculator.py
```

## Files

| File | What it is |
|---|---|
| `pilot_run/` | Raw outputs of the real pilot: per-stage logs, `calls.jsonl`, labels, issues, ranking, memo |
| `pilot_records.jsonl` | One result per pilot review ID, with the grading-contract row hash and common labels |
| `pilot_calls.jsonl` | Every attempted model call (cold + warm), with run ID, request ID, role, model, settings, usage, timing |
| `usage.csv` | Billing units per call, split into mutually exclusive items (input / cached input / output) |
| `rates.csv` | Editable prices in their billing units, with source links and the date checked |
| `assumptions.json` | Editable projection inputs: volumes, budget, workers, retry/re-send rates, verify rate |
| `report.md` / `report.json` | Measured pilot table + full-run base/conservative/no-reuse projections with budget warnings |

## Pilot settings (measured)

1 worker · empty result cache (cold) · enrichment batch 50 · Jev `jev-1.13.0` (prompt `enrich-v1`, verify `verify-v1`,
declared 20% verify sample, min 20) · OpenAI `gpt-6-luna`, reasoning effort `none`, output capped
(group 60×issues+200, memo 2,500) · no stronger-model fallback (max fallback fraction 0%).

## Accounting rules

- Input, cached input and output are separate billing items; reasoning tokens are already inside OpenAI output
  tokens and are not added again (effort `none` produced 0).
- Only the standard tier actually used is priced; batch-API discounts would belong in a labeled scenario.
- Failed attempts are logged; provider-reported usage was 0 for them. Missing usage would be shown as unknown.
- Local compute (laptop CPU for ingest/dedupe/rank) is **unknown**, reported separately, never counted as $0.
- Summed call durations are not wall-clock time; wall-clock comes from the orchestrator's clock. Multi-worker times
  in projections are **modeled**.
