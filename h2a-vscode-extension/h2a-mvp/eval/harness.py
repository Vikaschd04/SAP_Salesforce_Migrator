"""
eval/harness.py — Measurable quality scoring for a migration output.

This exists so prompt/model changes can be judged objectively instead of by
eyeballing. It scores what is measurable without hand-written golden Apex:

  - validation_pass_rate : fraction of generated .cls files with no ERROR issues
  - schema_violations    : count of unknown object/field references
  - artifact_coverage    : fraction of expected target classes that were produced
  - compiles             : real sf-CLI dry-run result (if an org is available)
  - golden_similarity    : token-overlap vs golden files (only if provided)

Add golden pairs under eval/cases/<name>/ with `input/` (Hybris source) and,
optionally, `expected/` (reference Apex) — see eval/README.md.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.ingest import ingest
from src.schema import build_schema
from src.validate import validate_all


def _expected_targets(input_dir: str) -> set[str]:
    """Predict target class names from the source (mirrors generate.plan_targets)."""
    from src.generate import plan_targets
    classes = ingest(input_dir)["classes"]
    return {t["target_name"] for t in plan_targets(classes)}


def _schema_for(input_dir: str) -> dict:
    res = ingest(input_dir)
    return build_schema(res["item_types"], res.get("relations", []))


def _token_overlap(a: str, b: str) -> float:
    ta = set(re.findall(r"[A-Za-z_]\w+", a))
    tb = set(re.findall(r"[A-Za-z_]\w+", b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def score_output(input_dir: str, output_dir: str, *, run_deploy: bool = False,
                 golden_dir: str | None = None) -> dict:
    schema = _schema_for(input_dir)
    classes_dir = Path(output_dir) / "force-app" / "main" / "default" / "classes"
    cls_files = sorted(classes_dir.glob("*.cls")) if classes_dir.exists() else []

    total, passed, schema_violations = 0, 0, 0
    per_file = {}
    for f in cls_files:
        code = f.read_text(encoding="utf-8")
        issues = validate_all(code, f.name, schema)
        errors = [i for i in issues if i["severity"] == "ERROR"]
        schema_violations += sum(1 for i in issues if i["rule"] in ("unknown_field", "unknown_sobject"))
        total += 1
        if not errors:
            passed += 1
        per_file[f.name] = {"errors": len(errors), "warnings": len(issues) - len(errors)}

    expected = _expected_targets(input_dir)
    produced = {f.stem for f in cls_files if not f.stem.endswith("Test")}
    covered = expected & produced
    coverage = len(covered) / len(expected) if expected else 1.0

    scorecard = {
        "input": input_dir,
        "output": output_dir,
        "files_total": total,
        "validation_pass_rate": round(passed / total, 3) if total else 0.0,
        "schema_violations": schema_violations,
        "artifact_coverage": round(coverage, 3),
        "expected_targets": sorted(expected),
        "missing_targets": sorted(expected - produced),
        "per_file": per_file,
        "compiles": None,
        "coverage_pct": None,
        "golden_similarity": None,
    }

    if run_deploy:
        from src.verify import deploy_check
        v = deploy_check(output_dir)
        scorecard["compiles"] = v.get("success") if v.get("ran") else None
        scorecard["coverage_pct"] = v.get("coverage")

    if golden_dir and Path(golden_dir).exists():
        sims = []
        for gf in Path(golden_dir).glob("*.cls"):
            out_f = classes_dir / gf.name
            if out_f.exists():
                sims.append(_token_overlap(gf.read_text(encoding="utf-8"),
                                           out_f.read_text(encoding="utf-8")))
        scorecard["golden_similarity"] = round(sum(sims) / len(sims), 3) if sims else None

    return scorecard
