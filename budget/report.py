"""Print spend so far, separately for each provider, against the $10 project cap. No API calls."""
import csv, json, pathlib
here = pathlib.Path(__file__).parent
cap = json.loads((here / "budget.json").read_text())["project_cap_usd"]
totals = {}
for r in csv.DictReader(open(here / "spend_ledger.csv")):
    t = totals.setdefault(r["provider"], {"calls": 0, "in": 0, "out": 0, "usd": 0.0})
    t["calls"] += 1; t["in"] += int(r["input_tokens"]); t["out"] += int(r["output_tokens"]); t["usd"] += float(r["cost_usd"])
print(f"{'provider':<10}{'calls':>7}{'input tok':>12}{'output tok':>12}{'spent USD':>14}")
for p, t in sorted(totals.items()):
    print(f"{p:<10}{t['calls']:>7}{t['in']:>12}{t['out']:>12}{t['usd']:>14.6f}")
spent = sum(t["usd"] for t in totals.values())
print(f"{'TOTAL':<10}{'':>31}{spent:>14.6f}")
print(f"Cap ${cap:.2f} | left ${cap - spent:.6f}")
