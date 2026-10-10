"""Command-line entry point: python -m pipeline <stage> ..."""
import argparse
import json
from pathlib import Path


def main():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # API keys stay in .env, never in code
    parser = argparse.ArgumentParser(prog="python -m pipeline")
    stages = parser.add_subparsers(dest="stage", required=True)
    p = stages.add_parser("ingest", help="Stage 1: read, profile and queue every row (no model calls, $0)")
    p.add_argument("--input", required=True, help="path to any review CSV with the six source columns")
    p.add_argument("--db", default="state/pipeline.sqlite")
    p.add_argument("--out-dir", default="outputs", help="reports folder (use a run folder for sample files)")
    p = stages.add_parser("dedupe", help="Stage 1b: map exact-duplicate texts to one canonical review (no model calls, $0)")
    p.add_argument("--db", default="state/pipeline.sqlite")
    p.add_argument("--out-dir", default="outputs")
    p = stages.add_parser("enrich", help="Stage 2: label pending reviews with Jev. Shows a price preview; "
                                         "only spends money with --confirm-spend")
    p.add_argument("--db", default="state/pipeline.sqlite")
    p.add_argument("--run-dir", required=True, help="where calls.jsonl for this run is written")
    p.add_argument("--layout", choices=["batched", "single"], default="batched")
    p.add_argument("--batch-size", type=int, default=50)
    p.add_argument("--limit", type=int, help="only the first N pending canonical reviews")
    p.add_argument("--max-spend", type=float, default=0.0, help="hard USD cap for this run")
    p.add_argument("--confirm-spend", action="store_true", help="actually call the paid API")
    args = parser.parse_args()

    if args.stage == "enrich":
        from . import enrich
        e = enrich.Enricher(args.db, args.run_dir, layout=args.layout, batch_size=args.batch_size,
                            max_spend=args.max_spend, limit=args.limit)
        preview = e.preview()
        print("PRICE PREVIEW\n" + json.dumps(preview, indent=2))
        if not args.confirm_spend:
            print("\nNo API calls made. Re-run with --confirm-spend (and --max-spend) to execute.")
            return
        if preview["reserved_with_safety_margin_usd"] > args.max_spend:
            print(f"\nNote: estimate exceeds --max-spend ${args.max_spend}; the run will stop when the cap is reached.")
        print("\nRESULT\n" + json.dumps(e.run(), indent=2))
        return

    if args.stage == "ingest":
        from . import ingest
        out = Path(args.out_dir)
        report = ingest.run(args.input, db_path=args.db, out_dir=out,
                            grading_dir=Path('grading') if out == Path('outputs') else out / 'grading')
        print(json.dumps({k: report[k] for k in ("run_id", "counts", "exact_duplicate_texts", "record_status",
                                                 "quarantine", "agrees_with_course_profile_helper", "seconds")}, indent=2))
    elif args.stage == "dedupe":
        from . import dedupe
        report = dedupe.run(db_path=args.db, out_dir=Path(args.out_dir))
        print(json.dumps({k: report[k] for k in ("counts", "integrity_checks_all_zero", "integrity_checks",
                                                 "group_size_distribution", "seconds")}, indent=2))


if __name__ == "__main__":
    main()
