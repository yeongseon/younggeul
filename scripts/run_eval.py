#!/usr/bin/env python3
"""Eval runner — executes evaluation tests and emits artifacts.

Usage:
    python scripts/run_eval.py [--output-dir eval_results]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from subprocess import run


def main() -> int:
    parser = argparse.ArgumentParser(description="Run evaluation tests")
    parser.add_argument("--output-dir", default="eval_results", help="Directory for artifacts")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    junit_path = output_dir / "eval_junit.xml"
    json_path = output_dir / "eval_summary.json"

    result = run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            "eval",
            f"--junitxml={junit_path}",
            "-v",
            "--tb=short",
        ],
        capture_output=True,
        text=True,
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "exit_code": result.returncode,
        "status": "passed" if result.returncode == 0 else "failed",
        "junit_xml": str(junit_path),
    }
    json_path.write_text(json.dumps(summary, indent=2))
    print(f"\nEval summary written to {json_path}")

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
