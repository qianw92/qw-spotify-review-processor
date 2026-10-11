"""100-review cost and runtime calculator. Standard library only; makes NO API calls and needs NO keys.

Default (offline replay):
    python cost/calculator.py
        Recomputes every pilot charge as billed_units x price_per_unit from cost/usage.csv and cost/rates.csv,
        projects the full run from cost/assumptions.json, and writes cost/report.md + cost/report.json.

    python cost/calculator.py --rates my_rates.csv --assumptions my_assumptions.json
        Same, with edited prices or projection assumptions. Measured pilot results never use the assumptions.

    python cost/calculator.py build-evidence
        Re-extracts pilot_records.jsonl, pilot_calls.jsonl and usage.csv from cost/pilot_run/ (still $0).

Paid pilot execution is a separate, explicit command (see cost/README.md); nothing here can start it.
"""
import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PILOT = HERE / "pilot_run"
ROLES = ["enrich", "verify", "group", "memo"]
STAGE_PROVIDER = {"enrich": "typesafe", "verify": "typesafe", "group": "openai", "memo": "openai"}


# ---------------------------------------------------------------- evidence extraction ($0)

def build_evidence():
    cold = json.loads((PILOT / "run_summary_cold.json").read_text())
    warm = json.loads((PILOT / "run_summary_warm.json").read_text())
    calls = [json.loads(l) for l in open(PILOT / "calls.jsonl", encoding="utf-8")]
    out_calls, usage = [], []
    for c in calls:
        label = "cold" if cold["started_at"] <= c["ts"] <= cold["finished_at"] else \
                "warm" if warm["started_at"] <= c["ts"] <= warm["finished_at"] else "other"
        c = {"run_id": f"pilot-{label}", "run_label": label, **c}
        out_calls.append(c)
        prov = STAGE_PROVIDER[c["role"]]
        if c["outcome"] == "succeeded" or c["input_tokens"] or c["output_tokens"]:
            if prov == "typesafe":
                items = [("input_tokens", c["input_tokens"]), ("output_tokens", c["output_tokens"])]
            else:
                cached = c.get("cached_input_tokens") or 0
                items = [("input_tokens_uncached", c["input_tokens"] - cached), ("cached_input_tokens", cached),
                         ("output_tokens", c["output_tokens"])]
            for item, units in items:
                usage.append({"request_id": c["request_id"], "run_label": label, "role": c["role"], "provider": prov,
                              "model": c["model"], "outcome": c["outcome"], "billing_item": item, "units": units})
    with open(HERE / "pilot_calls.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in out_calls)
    with open(HERE / "usage.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(usage[0]))
        w.writeheader()
        w.writerows(usage)
    (HERE / "pilot_records.jsonl").write_text((PILOT / "enriched.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    print(f"pilot_calls.jsonl: {len(out_calls)} calls · usage.csv: {len(usage)} billing rows · pilot_records.jsonl copied")


# ---------------------------------------------------------------- pricing (pure arithmetic)

def load_rates(path):
    rates = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        price = None if r["price_usd"].strip().lower() == "unknown" else float(r["price_usd"]) / float(r["per_units"])
        rates[(r["provider"], r["billing_item"])] = {**r, "unit_price": price}
    return rates


def item_cost(rates, provider, item, units):
    """billed_units x price_per_unit. Unknown prices return None (never silently 0)."""
    p = rates[(provider, item)]["unit_price"]
    return None if p is None else units * p


def bill(rates, provider, tokens):
    """tokens: {billing_item: units}. Mutually exclusive items, so the sum is the charge."""
    return sum(item_cost(rates, provider, item, units) for item, units in tokens.items())


# ---------------------------------------------------------------- measured pilot

def measured(rates):
    usage = list(csv.DictReader(open(HERE / "usage.csv", encoding="utf-8")))
    calls = [json.loads(l) for l in open(HERE / "pilot_calls.jsonl", encoding="utf-8")]
    records = [json.loads(l) for l in open(HERE / "pilot_records.jsonl", encoding="utf-8")]
    cold = json.loads((PILOT / "run_summary_cold.json").read_text())
    warm = json.loads((PILOT / "run_summary_warm.json").read_text())
    manifest = json.loads((PILOT / "data_manifest.json").read_text())
    dedupe = json.loads((PILOT / "dedupe_report.json").read_text())

    stages = {}
    for role in ROLES:
        rc = [c for c in calls if c["role"] == role and c["run_label"] == "cold"]
        ru = [u for u in usage if u["role"] == role and u["run_label"] == "cold"]
        tokens = defaultdict(int)
        for u in ru:
            tokens[u["billing_item"]] += int(u["units"])
        cost = sum(item_cost(rates, u["provider"], u["billing_item"], int(u["units"])) for u in ru)
        stage_secs = next(s["seconds"] for s in cold["stages"] if s["stage"] == role)
        call_secs = [c.get("seconds", 0) for c in rc if c["outcome"] == "succeeded"]
        reviews_sent = sum(len(c["review_ids"]) for c in rc if c["outcome"] == "succeeded")
        first = rc[0] if rc else {}
        stages[role] = {
            "provider": STAGE_PROVIDER[role], "model": first.get("model"),
            "effort": first.get("reasoning_effort", "n/a (Jev has no effort setting)"),
            "prompt_version": first.get("label_config") or first.get("prompt_version"),
            "batch_size": 50 if role in ("enrich", "verify") else "1 request (bounded pack)", "workers": 1,
            "requests": len({c["request_id"] for c in rc}), "attempts": len(rc),
            "failed_attempts": sum(c["outcome"] == "failed" for c in rc), "reviews_sent": reviews_sent,
            "tokens": dict(tokens), "cost_usd": cost, "stage_seconds": stage_secs,
            "call_seconds": call_secs, "seconds_per_request_mean": sum(call_secs) / len(call_secs) if call_secs else 0,
            "seconds_per_request_max": max(call_secs) if call_secs else 0}
    warm_calls = [c for c in calls if c["run_label"] == "warm"]
    total_cold = sum(s["cost_usd"] for s in stages.values())
    n = len(records)
    completed = sum(r["status"] == "completed" for r in records)
    return {
        "input": {"file": "cost_100.csv", "sha256": manifest["input"]["sha256"], "rows": n},
        "records": {"completed": completed, "failed_or_quarantined": n - completed,
                    "unique_texts": dedupe["counts"]["canonical_texts_to_classify"],
                    "result_cache_hits_cold": dedupe["counts"]["alias_rows_reusing_a_label"]},
        "stages": stages,
        "cold": {"api_cost_usd": total_cold,
                 "wall_clock_seconds": cold["wall_clock_seconds"],
                 "stage_seconds": {s["stage"]: s["seconds"] for s in cold["stages"]}},
        "warm": {"api_calls": len(warm_calls),
                 "enrich_calls": sum(c["role"] == "enrich" for c in warm_calls),
                 "api_cost_usd": sum(item_cost(rates, u["provider"], u["billing_item"], int(u["units"]))
                                     for u in usage if u["run_label"] == "warm"),
                 "wall_clock_seconds": warm["wall_clock_seconds"],
                 "stage_calls": {s["stage"]: s["calls_logged"] for s in warm["stages"]}},
        "unit": {"cost_per_1000_input_rows_usd": total_cold / n * 1000,
                 "cost_per_completed_record_usd": total_cold / completed if completed else None,
                 "throughput_rows_per_second_cold": n / cold["wall_clock_seconds"]},
        "local_compute": {"cost": "unknown", "note": "laptop CPU only; electricity/hardware not measured, not counted as $0"},
    }


# ---------------------------------------------------------------- projection

def project(m, rates, a, distinct_override=None):
    full = a["full_run"]
    texts = distinct_override or full["distinct_nonempty_texts"]
    out = {}
    for name, sc in a["scenarios"].items():
        st = {}
        for role in ("enrich", "verify"):
            s = m["stages"][role]
            per_review = {k: v / s["reviews_sent"] for k, v in s["tokens"].items()}
            n = texts if role == "enrich" else math.ceil(a["verify_rate"] * texts)
            # Failed API attempts bill no tokens (observed), so only invalid-output re-sends add tokens.
            factor = (1 + sc["token_variance"]) * (1 + sc["invalid_output_resend_rate"])
            tokens = {k: v * n * factor for k, v in per_review.items()}
            requests = math.ceil(n / a["batch_size"]) * (1 + sc["api_retry_rate"] + sc["invalid_output_resend_rate"])
            secs = requests * s["seconds_per_request_" + sc["seconds_per_request"]]
            wall = secs / (a["controls"]["max_workers"] * sc["parallel_efficiency"])
            st[role] = {"reviews": n, "requests": math.ceil(requests), "tokens": {k: round(v) for k, v in tokens.items()},
                        "cost_usd": bill(rates, s["provider"], tokens), "sequential_seconds": secs,
                        "modeled_wall_seconds": wall}
        issue_scale = a["expected_full_run_issues"] / max(1, len(open(PILOT / "ranking.csv").readlines()) - 1)
        for role, scale_key in (("group", "group_attempts"), ("memo", "memo_attempts")):
            s = m["stages"][role]
            scale = (issue_scale if role == "group" else 1) * sc[scale_key]
            tokens = {k: v * scale for k, v in s["tokens"].items()}
            st[role] = {"reviews": "fixed overhead (once)", "requests": sc[scale_key],
                        "tokens": {k: round(v) for k, v in tokens.items()},
                        "cost_usd": bill(rates, s["provider"], tokens),
                        "sequential_seconds": s["stage_seconds"] * sc[scale_key],
                        "modeled_wall_seconds": s["stage_seconds"] * sc[scale_key]}
        api = sum(x["cost_usd"] for x in st.values())
        wall = sum(x["modeled_wall_seconds"] for x in st.values())
        remaining = a["budget_usd"] - a["already_spent_usd"]
        out[name] = {"texts_classified": texts, "stages": st, "api_cost_usd": api,
                     "by_provider": {p: sum(x["cost_usd"] for r, x in st.items() if STAGE_PROVIDER[r] == p)
                                     for p in ("typesafe", "openai")},
                     "modeled_wall_hours": wall / 3600, "budget_remaining_usd": remaining,
                     "within_budget": api <= remaining, "within_run_cap": api <= a["controls"]["run_cap_usd"]}
    return out


# ---------------------------------------------------------------- report

def money(x, d=4):
    return "unknown" if x is None else f"${x:,.{d}f}"


def report(m, proj, noreuse, rates, a):
    L = []
    w = L.append
    w("# Cost & runtime report — 100-review pilot\n")
    w("*Generated by `python cost/calculator.py` (offline: no API key, no model calls). "
      "Charges = billed units × price per unit from `rates.csv`; usage from `usage.csv`.*\n")
    w("## Measured: real pilot on `cost_100.csv`\n")
    w(f"- Input: `{m['input']['file']}` sha256 `{m['input']['sha256'][:16]}…`, {m['input']['rows']} IDs")
    w(f"- Records: **{m['records']['completed']} completed**, {m['records']['failed_or_quarantined']} failed/quarantined; "
      f"{m['records']['unique_texts']} unique texts; result-cache hits (cold): {m['records']['result_cache_hits_cold']}")
    w("- Settings: 1 worker, empty result cache for the cold run, enrichment batch size 50\n")
    w("| Stage | Provider | Model | Effort | Prompt/schema | Requests | Attempts | Failed | Reviews sent | Tokens (billing items) | Cost | Stage time |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for role, s in m["stages"].items():
        toks = ", ".join(f"{k} {v:,}" for k, v in s["tokens"].items())
        w(f"| {role} | {s['provider']} | {s['model']} | {s['effort']} | {s['prompt_version']} | {s['requests']} | "
          f"{s['attempts']} | {s['failed_attempts']} | {s['reviews_sent']} | {toks} | {money(s['cost_usd'], 6)} | {s['stage_seconds']:.2f}s |")
    w("")
    w("| | Cold run | Warm run |\n|---|---|---|")
    w(f"| API cost | **{money(m['cold']['api_cost_usd'], 6)}** | **{money(m['warm']['api_cost_usd'], 6)}** |")
    w(f"| Wall-clock (end to end) | {m['cold']['wall_clock_seconds']:.2f}s | {m['warm']['wall_clock_seconds']:.2f}s |")
    w(f"| New enrichment calls | {m['stages']['enrich']['requests']} | **{m['warm']['enrich_calls']}** |")
    w(f"| Downstream calls (verify/group/memo) | 3 | {m['warm']['api_calls'] - m['warm']['enrich_calls']} (saved answers reused) |")
    w(f"| Local compute | unknown (not measured) | unknown (not measured) |\n")
    u = m["unit"]
    w(f"Cost per 1,000 input rows: **{money(u['cost_per_1000_input_rows_usd'])}** · per completed record: "
      f"{money(u['cost_per_completed_record_usd'], 7)} · cold throughput: {u['throughput_rows_per_second_cold']:.1f} rows/s. "
      "Summed call durations are not wall-clock time; wall-clock comes from the orchestrator's clock.\n")
    w("## Rates used (editable `rates.csv`)\n")
    w("| Provider | Model | Billing item | Price | Per | Source | Checked |\n|---|---|---|---|---|---|---|")
    for (p, item), r in rates.items():
        w(f"| {p} | {r['model']} | {item} | {r['price_usd']} | {r['per_units']} {r['unit']}s | {r['source_url'] or '—'} | {r['checked_date']} |")
    w("")
    full = a["full_run"]
    w("## Estimated: full run (projection, not a measurement)\n")
    w(f"- {full['source_rows']:,} rows accounted for: {full['nonempty_to_classify']:,} nonempty classified, "
      f"{full['empty_text_quarantines']} empty-text quarantines")
    w(f"- With exact-text reuse: **{full['distinct_nonempty_texts']:,}** distinct texts sent to the model "
      f"(no-reuse comparison: {full['nonempty_to_classify']:,})")
    w(f"- Verification: {a['verify_rate']:.0%} declared sample · fallback model: {a['controls']['fallback_model']} "
      f"(max fallback fraction {a['controls']['max_fallback_fraction']:.0%}) · group + memo counted once as fixed overhead")
    w(f"- Controls: budget ${a['budget_usd']:.2f} (already spent ${a['already_spent_usd']:.4f}) · run cap "
      f"${a['controls']['run_cap_usd']:.2f} · max workers {a['controls']['max_workers']} · OpenAI output caps "
      f"{a['controls']['openai_max_output_tokens']}\n")
    w("| Scenario | Texts | Enrich | Verify | Group | Memo | **API total** | Jev | OpenAI | Modeled wall time | Budget check |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for label, pr in [*((k, v) for k, v in proj.items()), *((f"{k} (no reuse)", v) for k, v in noreuse.items())]:
        st = pr["stages"]
        flag = "✅ within budget" if pr["within_budget"] else "⚠️ **EXCEEDS BUDGET**"
        if pr["within_budget"] and not pr["within_run_cap"]:
            flag = "⚠️ exceeds run cap"
        w(f"| {label} | {pr['texts_classified']:,} | {money(st['enrich']['cost_usd'], 2)} | {money(st['verify']['cost_usd'], 3)} | "
          f"{money(st['group']['cost_usd'], 4)} | {money(st['memo']['cost_usd'], 4)} | **{money(pr['api_cost_usd'], 2)}** | "
          f"{money(pr['by_provider']['typesafe'], 2)} | {money(pr['by_provider']['openai'], 4)} | "
          f"{pr['modeled_wall_hours']:.1f} h | {flag} |")
    w("")
    w("Assumptions (`assumptions.json`): base = measured tokens/review, 1% API retries, 0.5% invalid-output re-sends, "
      "mean request time, 90% parallel efficiency; conservative = +10% tokens, 5% retries, 2% re-sends, slowest observed "
      "request, 60% efficiency, memo and group each regenerated once. Failed API attempts are logged but bill no tokens. "
      "Wall time with >1 worker is **modeled**, not measured. Local compute cost is unknown and excluded from API totals. "
      "The first 100 reviews are an initial estimate; it is refreshed at 500 and 10,000 reviews before the full run.")
    (HERE / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="replay", choices=["replay", "build-evidence"])
    ap.add_argument("--rates", default=str(HERE / "rates.csv"))
    ap.add_argument("--assumptions", default=str(HERE / "assumptions.json"))
    args = ap.parse_args()
    if args.command == "build-evidence":
        build_evidence()
        return
    rates = load_rates(args.rates)
    a = json.loads(Path(args.assumptions).read_text())
    m = measured(rates)
    proj = project(m, rates, a)
    noreuse = project(m, rates, a, distinct_override=a["full_run"]["nonempty_to_classify"])
    report(m, proj, noreuse, rates, a)
    (HERE / "report.json").write_text(json.dumps({"measured": m, "projection": proj, "projection_no_reuse": noreuse},
                                                 indent=2, default=str))
    print(f"Measured cold pilot: {money(m['cold']['api_cost_usd'], 6)} in {m['cold']['wall_clock_seconds']:.1f}s · "
          f"warm: {money(m['warm']['api_cost_usd'], 6)}, {m['warm']['enrich_calls']} enrichment calls")
    for k, v in proj.items():
        print(f"Full run {k}: {money(v['api_cost_usd'], 2)} (Jev {money(v['by_provider']['typesafe'], 2)}, OpenAI "
              f"{money(v['by_provider']['openai'], 4)}), ~{v['modeled_wall_hours']:.1f} h modeled, "
              f"{'within' if v['within_budget'] else 'EXCEEDS'} remaining budget ${v['budget_remaining_usd']:.2f}")
    print("Wrote cost/report.md and cost/report.json (no API calls made)")


if __name__ == "__main__":
    main()
