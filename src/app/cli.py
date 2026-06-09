from __future__ import annotations

import argparse

from app.graph import ShoppingAssistant


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Student scaffold CLI.")
    parser.add_argument("--question", help="Run one question through the graph.")
    parser.add_argument("--test-file", default="data/test.json")
    parser.add_argument("--trace-file", default=None)
    parser.add_argument("--batch", action="store_true")
    return parser


import sys
from pathlib import Path


def main() -> None:
    args = build_parser().parse_args()
    assistant = ShoppingAssistant()

    if args.batch:
        test_file = Path(args.test_file)
        output_dir = Path("src/artifacts")
        print(f"Running batch test using file: {test_file}...")
        summary = assistant.run_batch(test_file, output_dir)
        print("\n=== BATCH RUN COMPLETED ===")
        print(f"Total test cases run: {summary['total_cases']}")
        print(f"Summary file written to: {output_dir / 'summary.json'}")
        
        ok_count = sum(1 for r in summary["results"] if r["status"] == "ok")
        clar_count = sum(1 for r in summary["results"] if r["status"] == "clarification_needed")
        nf_count = sum(1 for r in summary["results"] if r["status"] == "not_found")
        print(f"Status results: ok={ok_count}, clarification_needed={clar_count}, not_found={nf_count}")
    elif args.question:
        question = args.question
        print(f"Asking: '{question}'...\n")
        trace_file = Path(args.trace_file) if args.trace_file else None
        res = assistant.ask(question, trace_file=trace_file)
        print("=== FINAL ANSWER ===")
        print(res["final_answer"])
        if trace_file:
            print(f"\nTrace saved to: {trace_file}")
    else:
        print("Please provide --question or --batch argument. Use --help for usage details.")
        sys.exit(1)



if __name__ == "__main__":
    main()
