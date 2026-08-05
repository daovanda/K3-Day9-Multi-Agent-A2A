from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.config import OUTPUT_DIR, ROOT_DIR
from src.validation import validate_output_set, validate_submission_zip


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate all lab deliverables.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--zip", dest="zip_path", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = validate_output_set(args.output_dir)
    if args.zip_path is not None:
        validate_submission_zip(args.zip_path)
        result["zip"] = str(args.zip_path.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))

