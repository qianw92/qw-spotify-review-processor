"""Orchestrator: runs every stage on one input CSV, in order, under one spend cap.

Code decides the next step; models only answer bounded questions inside enrich/verify (Jev) and
group/memo (OpenAI). Each stage's handoff is saved to the run folder, so any stage can be inspected
or rerun. A warm rerun of the same input reuses saved results: 0 new enrichment calls.
"""
import datetime
import json
import math
import time
from pathlib import Path

from . import budget, calllog, db, dedupe, enrich, export, group, ingest, llm, memo, rank, verify


def spend_by_provider():
    return {"typesafe": budget.spent("typesafe"), "openai": budget.spent("openai")}


def preview(input_csv, db_path, run_dir, verify_rate, verify_min):
    """Estimate every stage before spending. Runs ingest + dedupe ($0) so pending work is known."""
    ingest.run(input_csv, db_path=db_path, out_dir=Path(run_dir), grading_dir=Path(run_dir) / "grading")
    dedupe.run(db_path=db_path, out_dir=Path(run_dir))
    e = enrich.Enricher(db_path, run_dir).preview()
    con = db.connect(db_path)
    canon = con.execute("SELECT COUNT(*) FROM text_map WHERE is_canonical=1").fetchone()[0]
    per_review = e["estimated_input_tokens"] / max(1, e["reviews_to_send"]) if e["reviews_to_send"] else 330
    n_verify = min(canon, max(verify_min, math.ceil(verify_rate * canon)))
    v_tokens = int(n_verify * per_review)
    g_in, g_out = 6000, 3000        # bounded: <= ~40 issues x 4 examples, capped output
    m_in, m_out = 8000, 2500        # bounded evidence pack, capped output
    rows = [
        ("enrich (Jev)", "typesafe", e["estimated_input_tokens"], 0, e["requests"]),
        (f"verify sample of {n_verify} (Jev)", "typesafe", v_tokens, 0, math.ceil(n_verify / 50)),
        ("group naming (OpenAI)", "openai", g_in, g_out, 1),
        ("memo (OpenAI)", "openai", m_in, m_out, 1),
    ]
    out = []
    for name, prov, tin, tout, req in rows:
        pin, pout = budget.price(prov)
        out.append({"stage": name, "provider": prov, "requests": req, "est_input_tokens": tin,
                    "est_output_tokens_max": tout, "price": f"${pin}/1M in, ${pout}/1M out",
                    "est_cost_usd": round(budget.cost(prov, tin, tout), 6)})
    return {"stages": out, "total_est_usd": round(sum(r["est_cost_usd"] for r in out), 6),
            "reviews_to_enrich": e["reviews_to_send"], "phase": e["phase"],
            "spent_so_far": {k: round(v, 6) for k, v in spend_by_provider().items()}}


def run(input_csv, db_path, run_dir, max_spend, verify_rate=0.01, verify_min=20, run_label="run",
        allow_partial=False):
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    guard = budget.Guard(max_spend)
    log_path = run_dir / "run_log.jsonl"
    summary = {"run_label": run_label, "input": str(input_csv), "db": str(db_path),
               "started_at": calllog.now(), "max_spend_usd": max_spend,
               "config": {"enrich": enrich.label_config("batched"), "verify": verify.verify_config(),
                          "group_prompt": group.PROMPT_VERSION, "memo_prompt": memo.PROMPT_VERSION,
                          "openai_model": llm.MODEL, "openai_reasoning_effort": llm.REASONING_EFFORT,
                          "jev_model": enrich.MODEL, "batch_size": 50, "workers": 1,
                          "verify_rate": verify_rate, "verify_min": verify_min, "verify_seed": verify.SEED},
               "stages": []}
    t_run = time.time()
    state = {}

    def stage(name, fn):
        calls0, spend0, t0 = calllog.count_calls(run_dir), spend_by_provider(), time.time()
        status, result = "ok", None
        try:
            result = fn()
        except budget.BudgetExceeded as e:
            status, result = "stopped_budget", str(e)
        except Exception as e:  # recorded, then re-raised after the log is written
            status, result = "error", f"{type(e).__name__}: {e}"
        spend1 = spend_by_provider()
        entry = {"stage": name, "status": status, "seconds": round(time.time() - t0, 3),
                 "calls_logged": calllog.count_calls(run_dir) - calls0,
                 "spend_usd": {k: round(spend1[k] - spend0[k], 8) for k in spend1}, "result": result}
        summary["stages"].append(entry)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": calllog.now(), "run_label": run_label, **entry}, default=str) + "\n")
        print(f"[{run_label}] {name}: {status} in {entry['seconds']}s, calls={entry['calls_logged']}", flush=True)
        if status == "error":
            raise RuntimeError(result)
        return status, result

    stage("ingest", lambda: {k: v for k, v in ingest.run(input_csv, db_path=db_path, out_dir=run_dir,
                                                           grading_dir=run_dir / "grading").items()
                             if k in ("counts", "record_status", "reused_saved_state_for_same_input")})
    stage("dedupe", lambda: dedupe.run(db_path=db_path, out_dir=run_dir)["counts"])
    enricher = enrich.Enricher(db_path, run_dir, guard=guard)
    status, res = stage("enrich", enricher.run)
    con = db.connect(db_path)
    counts = dict(con.execute("SELECT status, COUNT(*) FROM records GROUP BY status").fetchall())
    stage("export_records", lambda: export.write(con, run_dir / "enriched.jsonl"))
    incomplete = counts.get("pending", 0) > 0 or status != "ok" or (res or {}).get("stopped_reason")
    if incomplete and not allow_partial:
        summary["stopped"] = f"enrichment incomplete: {counts}; downstream stages not run (use --allow-partial)"
    else:
        phase = enricher.phase
        stage("verify", lambda: verify.run(con, run_dir, guard, rate=verify_rate, minimum=verify_min, phase=phase))
        stage("group", lambda: group.run(con, run_dir, guard))
        status_r, rank_res = stage("rank", lambda: rank.from_db(con, run_dir))
        rows = rank.compute(con.execute("SELECT issue_id, review_id FROM membership").fetchall(),
                            dict(con.execute("SELECT review_id, severity FROM labels")))
        coverage = {"source_rows": sum(counts.values()), "completed": counts.get("completed", 0),
                    "quarantined": counts.get("quarantined", 0), "pending": counts.get("pending", 0)}
        stage("memo", lambda: memo.run(con, run_dir, guard, rows, coverage))
    summary["record_status"] = counts
    summary["wall_clock_seconds"] = round(time.time() - t_run, 3)
    summary["run_spent_usd"] = round(guard.run_spent, 8)
    summary["finished_at"] = calllog.now()
    (run_dir / f"run_summary_{run_label}.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary
