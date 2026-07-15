"""
eval/run_eval.py — Migrate an input project and print a quality scorecard.

Usage (from the h2a-mvp directory):
    python -m eval.run_eval --input <hybris_dir> [--provider mock] [--deploy] [--golden <dir>]

With --provider mock it runs keyless and deterministically, so it is safe for CI
as a regression gate on the *deterministic* pipeline (parsing, planning, schema
grounding, validation, SFDX layout). Use the real provider to gate translation
quality.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile

from src.pipeline_driver import run_repo_migration
from eval.harness import score_output


def main():
    ap = argparse.ArgumentParser(prog="run_eval")
    ap.add_argument("--input", required=True, help="Hybris source directory")
    ap.add_argument("--output", default=None, help="Output dir (default: temp)")
    ap.add_argument("--provider", default=None, help="anthropic | mock (overrides config)")
    ap.add_argument("--deploy", action="store_true", help="Also run sf-CLI compile check")
    ap.add_argument("--golden", default=None, help="Directory of reference .cls for similarity")
    args = ap.parse_args()

    if args.provider:
        os.environ["H2A_PROVIDER"] = args.provider

    output = args.output or tempfile.mkdtemp(prefix="h2a_eval_")
    run_repo_migration(args.input, output)

    scorecard = score_output(args.input, output, run_deploy=args.deploy, golden_dir=args.golden)

    print("\n═══ EVAL SCORECARD ═══")
    print(json.dumps(scorecard, indent=2))

    # Non-zero exit if the deterministic pipeline regressed (no output or ERRORs).
    ok = scorecard["files_total"] > 0 and scorecard["validation_pass_rate"] >= 1.0 \
        and not scorecard["missing_targets"]
    print("\nRESULT:", "PASS ✅" if ok else "FAIL ❌")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
