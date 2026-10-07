"""Command-line entry point: python -m pipeline <stage> ..."""
import argparse
import json


def main():
    parser = argparse.ArgumentParser(prog="python -m pipeline")
    stages = parser.add_subparsers(dest="stage", required=True)
    p = stages.add_parser("ingest", help="Stage 1: read, profile and queue every row (no model calls, $0)")
    p.add_argument("--input", required=True, help="path to any review CSV with the six source columns")
    p.add_argument("--db", default="state/pipeline.sqlite")
    p = stages.add_parser("dedupe", help="Stage 1b: map exact-duplicate texts to one canonical review (no model calls, $0)")
    p.add_argument("--db", default="state/pipeline.sqlite")
    args = parser.parse_args()

    if args.stage == "ingest":
        from . import ingest
        report = ingest.run(args.input, db_path=args.db)
        print(json.dumps({k: report[k] for k in ("run_id", "counts", "exact_duplicate_texts", "record_status",
                                                 "quarantine", "agrees_with_course_profile_helper", "seconds")}, indent=2))
    elif args.stage == "dedupe":
        from . import dedupe
        report = dedupe.run(db_path=args.db)
        print(json.dumps({k: report[k] for k in ("counts", "integrity_checks_all_zero", "integrity_checks",
                                                 "group_size_distribution", "seconds")}, indent=2))


if __name__ == "__main__":
    main()
