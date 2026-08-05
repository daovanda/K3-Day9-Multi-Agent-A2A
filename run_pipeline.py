from __future__ import annotations

import argparse
import json

from src.pipeline import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the 50-case multi-agent dispute resolution pipeline."
    )
    parser.add_argument(
        "--llm-mode",
        choices=("off", "policy", "all"),
        default="all",
        help="off=deterministic test, policy=one API audit/case, all=four API audits/case",
    )
    parser.add_argument("--limit", type=int, default=None, help="Process the first N cases")
    parser.add_argument(
        "--zip",
        action="store_true",
        help="Create submission.zip after a complete 50-case run",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of cases processed concurrently (1-8)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    result = run_pipeline(
        llm_mode=arguments.llm_mode,
        limit=arguments.limit,
        create_zip=arguments.zip,
        workers=arguments.workers,
    )
    print(json.dumps(dict(sorted(result.items())), indent=2))
