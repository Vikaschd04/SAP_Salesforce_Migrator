"""
verify.py — Real Salesforce compile/deploy verification via the `sf` CLI.

This is the deterministic ground truth that regex lints cannot provide: it asks a
real Salesforce org to compile the generated metadata (dry-run deploy) and,
optionally, run the generated Apex tests for code coverage.

It degrades gracefully:
  - if the `sf` CLI is not installed        -> {"available": False, ...}
  - if no org is authorised / reachable      -> {"available": True, "ran": False, "message": ...}
  - on a successful dry run                   -> {"success": True/False, "errors": [...]}

Requires (to run live):
  - Salesforce CLI:  https://developer.salesforce.com/tools/salesforcecli
  - An authorised org:  `sf org login web`  (or a scratch org)

Nothing here is invoked automatically unless `verify.deploy` is enabled in
config.yaml or `--verify` is passed, so a keyless/orgless run is unaffected.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path


def sf_available() -> bool:
    return shutil.which("sf") is not None


def _run(cmd: list[str], cwd: str, timeout: int = 600) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def deploy_check(output_dir: str, target_org: str | None = None,
                 run_tests: bool = False) -> dict:
    """
    Dry-run deploy the generated force-app to verify it compiles.

    Returns:
        {
          "available": bool,   # sf CLI present
          "ran": bool,         # a dry run actually executed
          "success": bool,     # compiled cleanly
          "errors": [ {file, line, problem}, ... ],
          "coverage": float|None,
          "message": str,
        }
    """
    result = {"available": sf_available(), "ran": False, "success": False,
              "errors": [], "coverage": None, "per_class_coverage": [], "message": ""}
    if not result["available"]:
        result["message"] = "Salesforce CLI (`sf`) not found on PATH — skipping deploy verification."
        return result

    force_app = Path(output_dir) / "force-app"
    if not force_app.exists():
        result["message"] = f"No force-app directory in {output_dir}."
        return result

    cmd = ["sf", "project", "deploy", "start", "--dry-run",
           "--source-dir", "force-app", "--json", "--ignore-conflicts"]
    if target_org:
        cmd += ["--target-org", target_org]
    if run_tests:
        cmd += ["--test-level", "RunLocalTests"]

    try:
        code, stdout, stderr = _run(cmd, cwd=output_dir)
    except FileNotFoundError:
        result["message"] = "Salesforce CLI invocation failed (not found)."
        return result
    except subprocess.TimeoutExpired:
        result["message"] = "Deploy verification timed out."
        return result

    try:
        data = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        result["message"] = (stderr or stdout or "sf returned non-JSON output").strip()[:500]
        return result

    # `sf` returns status 0 on success. On auth/connection failure it errors before
    # touching the org — surface that as "ran=False" rather than a code failure.
    payload = data.get("result", data)
    if data.get("status") not in (0, None) and not payload.get("details"):
        msg = data.get("message", "") or (stderr or "")
        if any(t in msg.lower() for t in ("no default", "no org", "not been authorized", "expired access")):
            result["ran"] = False
            result["message"] = ("No authorised Salesforce org. Run `sf org login web` "
                                  "(or create a scratch org) to enable live verification.")
            return result

    result["ran"] = True
    details = payload.get("details", {}) if isinstance(payload, dict) else {}
    failures = details.get("componentFailures", []) or []
    if isinstance(failures, dict):
        failures = [failures]
    for f in failures:
        result["errors"].append({
            "file": f.get("fileName") or f.get("fullName", ""),
            "line": f.get("lineNumber"),
            "problem": f.get("problem", ""),
        })
    result["success"] = bool(payload.get("success", not result["errors"]))

    cov = (details.get("runTestResult", {}) or {}).get("codeCoverage")
    if cov:
        try:
            covered = sum(int(c.get("numLocations", 0)) - int(c.get("numLocationsNotCovered", 0)) for c in cov)
            total = sum(int(c.get("numLocations", 0)) for c in cov)
            result["coverage"] = round(100.0 * covered / total, 1) if total else None
            # Per-class coverage so the coverage-heal loop knows which classes to strengthen.
            per_class = []
            for c in cov:
                loc = int(c.get("numLocations", 0))
                if loc <= 0:
                    continue
                uncov = int(c.get("numLocationsNotCovered", 0))
                per_class.append({"name": c.get("name") or c.get("id", ""),
                                  "coverage": round(100.0 * (loc - uncov) / loc, 1)})
            result["per_class_coverage"] = per_class
        except Exception:
            pass

    result["message"] = "Compiled cleanly." if result["success"] else f"{len(result['errors'])} component failure(s)."
    return result


# ── Self-healing deploy loop ──────────────────────────────────────────────────
#
# The deterministic ground truth (deploy_check) tells us *exactly* what the
# Salesforce compiler rejected — file, line, and problem. Instead of merely
# reporting those, we feed them straight back into the LLM repair loop, rewrite
# the offending class on disk, and re-deploy — closing the loop until the output
# compiles cleanly or the repair budget is exhausted. This is the difference
# between "validation as a proxy" and "output verified against a real org".

def _basename(file_str: str) -> str:
    """Normalise a deploy-error file path to a bare class filename (Foo.cls)."""
    return Path(file_str).name if file_str else ""


def _errors_to_issues(errors: list) -> list:
    """Convert deploy component failures into the issue shape repair() expects."""
    issues = []
    for e in errors:
        line = e.get("line")
        problem = (e.get("problem") or "").strip()
        message = f"Line {line}: {problem}" if line else problem
        issues.append({"rule": "deploy_error", "message": message, "severity": "ERROR"})
    return issues


# Deploy errors that indicate a *missing custom field/object* — fixable by
# augmenting the schema/metadata, not by repairing Apex.
_META_ERROR_RES = [
    (re.compile(r"no such column '?([A-Za-z]\w*__c)'? on (?:entity|sobject) '?([A-Za-z]\w*__c)'?", re.I), "field_on_obj"),
    (re.compile(r"no customfield named ([A-Za-z]\w*__c)\.([A-Za-z]\w*__c)", re.I), "obj_dot_field"),
    (re.compile(r"sobject type '?([A-Za-z]\w*__c)'? is not supported", re.I), "obj"),
    (re.compile(r"invalid type:\s*([A-Za-z]\w*__c)", re.I), "obj"),
]


def _parse_metadata_errors(errors: list) -> list:
    """Extract {object, field, kind} for deploy errors that name a missing custom
    field or object, so the heal loop can add it to the schema instead of trying
    to LLM-repair the Apex."""
    targets, seen = [], set()
    for e in errors:
        problem = e.get("problem") or ""
        for rx, kind in _META_ERROR_RES:
            for m in rx.finditer(problem):
                if kind == "field_on_obj":
                    field, obj = m.group(1), m.group(2)
                elif kind == "obj_dot_field":
                    obj, field = m.group(1), m.group(2)
                else:
                    obj, field = m.group(1), None
                key = (obj, field)
                if key in seen:
                    continue
                seen.add(key)
                targets.append({"object": obj, "field": field,
                                "kind": "object" if field is None else "field"})
    return targets


def deploy_and_heal(output_dir: str, generated: list, *,
                    schema: dict | None = None, signatures: list | None = None,
                    offline: bool = False, target_org: str | None = None,
                    run_tests: bool = False, max_attempts: int = 2,
                    auto_repair: bool = True, source_corpus: str = "",
                    coverage_threshold: float = 75.0, log=print) -> dict:
    """
    Deploy-verify the generated Apex against a real org and self-heal until it is
    green, using the real deploy feedback three ways:

      1. **Metadata healing** — a "missing custom field/object" error becomes a
         schema addition (evidence-gated by the Hybris source) + re-emitted
         SObject metadata, not an Apex repair.
      2. **Apex repair** — remaining compiler errors are fed back into the LLM
         repair loop and the offending class is rewritten.
      3. **Coverage healing** — once it compiles, if `run_tests` coverage is below
         `coverage_threshold` (Salesforce's 75%), the under-covered classes' tests
         are strengthened and re-deployed.

    `generated` and `schema` are mutated in place and the corresponding files are
    rewritten, so the on-disk output and the feasibility report reflect the healed
    state. Returns the final deploy_check result augmented with a "healing" summary.
    """
    schema = schema if schema is not None else {}
    classes_dir = Path(output_dir) / "force-app" / "main" / "default" / "classes"

    healing = {"rounds": [], "healed_files": [], "healed_metadata": [],
               "coverage_strengthened": []}

    def _coverage_low(res: dict) -> bool:
        return bool(run_tests and res.get("coverage") is not None
                    and res["coverage"] < coverage_threshold)

    result = deploy_check(output_dir, target_org=target_org, run_tests=run_tests)
    if not auto_repair or not result["available"] or not result["ran"]:
        result["healing"] = healing
        return result
    if result["success"] and not _coverage_low(result):
        result["healing"] = healing
        return result

    # Imported here to avoid a module-load cycle (validate -> llm -> ...).
    from src.validate import repair
    from src.schema import _evidenced_in_source, infer_field_type
    from src.metadata_generator import write_schema_metadata
    from src.generate import strengthen_tests

    index = {}
    for gen in generated:
        name = gen["target_name"]
        index[f"{name}.cls"] = (gen, "main_class")
        index[f"{name}Test.cls"] = (gen, "test_class")

    def _heal_compile(res: dict, round_num: int) -> bool:
        round_info = {"round": round_num, "type": "compile", "metadata": [], "files": []}
        changed = False
        handled_tokens: set = set()

        # (a) Metadata healing — add evidenced missing objects/fields.
        for t in _parse_metadata_errors(res["errors"]):
            obj, field = t["object"], t["field"]
            if t["kind"] == "object":
                if obj and obj not in schema and _evidenced_in_source(obj, source_corpus):
                    schema[obj] = {"code": obj[:-3], "fields": {}}
                    healing["healed_metadata"].append(obj)
                    round_info["metadata"].append({"added_object": obj})
                    handled_tokens.add(obj.lower())
                    changed = True
            elif field and obj:
                schema.setdefault(obj, {"code": obj[:-3], "fields": {}})
                if field not in schema[obj]["fields"] and _evidenced_in_source(field, source_corpus):
                    ftype = infer_field_type(field, source_corpus)
                    schema[obj]["fields"][field] = ftype
                    healing["healed_metadata"].append(f"{obj}.{field}")
                    round_info["metadata"].append({"added_field": f"{obj}.{field}", "type": ftype})
                    handled_tokens.add(field.lower())
                    changed = True
        if round_info["metadata"]:
            write_schema_metadata(output_dir, schema)  # idempotent full re-emit
            log(f"    ⚕ Metadata heal (round {round_num}): +{len(round_info['metadata'])} object/field(s)")

        # (b) Apex repair — remaining errors on generated classes.
        by_file: dict[str, list] = {}
        for err in res["errors"]:
            by_file.setdefault(_basename(err.get("file", "")), []).append(err)
        for fname, errs in by_file.items():
            remaining = [e for e in errs
                         if not any(tok in (e.get("problem") or "").lower() for tok in handled_tokens)]
            if not remaining:
                round_info["files"].append({"file": fname, "repaired": False, "reason": "resolved via metadata"})
                continue
            entry = index.get(fname)
            if not entry:
                round_info["files"].append({"file": fname, "repaired": False, "reason": "not a generated Apex class"})
                continue
            gen, cfield = entry
            code = gen.get(cfield, "")
            issues = _errors_to_issues(remaining)
            log(f"    ⚕ Healing {fname} (round {round_num}): {len(remaining)} compiler error(s)")
            try:
                healed = repair(code, issues, attempt=round_num, offline=offline,
                                signatures=signatures, schema=schema)
            except Exception as ex:  # repair must never abort the whole run
                round_info["files"].append({"file": fname, "repaired": False, "reason": str(ex)[:120]})
                continue
            if healed and healed.strip() and healed != code:
                gen[cfield] = healed
                (classes_dir / fname).write_text(healed, encoding="utf-8")
                if fname not in healing["healed_files"]:
                    healing["healed_files"].append(fname)
                round_info["files"].append({"file": fname, "repaired": True})
                changed = True
            else:
                round_info["files"].append({"file": fname, "repaired": False, "reason": "no change produced"})

        healing["rounds"].append(round_info)
        return changed

    def _heal_coverage(res: dict, round_num: int) -> bool:
        round_info = {"round": round_num, "type": "coverage", "classes": []}
        per = res.get("per_class_coverage") or []
        low = [c for c in per
               if c.get("coverage") is not None and c["coverage"] < coverage_threshold
               and not str(c.get("name", "")).endswith("Test")]
        if not low:  # no per-class breakdown — strengthen every target
            low = [{"name": g["target_name"], "coverage": res.get("coverage")} for g in generated]
        changed = False
        for c in low:
            name = str(c.get("name", ""))
            gen = next((g for g in generated if g["target_name"] == name), None)
            if not gen:
                continue
            test_fname = f"{name}Test.cls"
            log(f"    ⚕ Strengthening tests for {name} "
                f"({c.get('coverage')}% < {coverage_threshold}%)")
            try:
                new_test = strengthen_tests(gen.get("main_class", ""), gen.get("test_class", ""),
                                            name, c.get("coverage"), schema=schema, offline=offline)
            except Exception as ex:
                round_info["classes"].append({"class": name, "strengthened": False, "reason": str(ex)[:120]})
                continue
            if new_test and new_test.strip() and new_test != gen.get("test_class", ""):
                gen["test_class"] = new_test
                (classes_dir / test_fname).write_text(new_test, encoding="utf-8")
                if test_fname not in healing["coverage_strengthened"]:
                    healing["coverage_strengthened"].append(test_fname)
                round_info["classes"].append({"class": name, "strengthened": True, "from": c.get("coverage")})
                changed = True
            else:
                round_info["classes"].append({"class": name, "strengthened": False, "reason": "no change"})
        healing["rounds"].append(round_info)
        return changed

    for round_num in range(1, max_attempts + 1):
        if not result["success"]:
            changed = _heal_compile(result, round_num)
        elif _coverage_low(result):
            changed = _heal_coverage(result, round_num)
        else:
            break
        if not changed:
            log("  ⚠ Heal round produced no changes — stopping.")
            break
        result = deploy_check(output_dir, target_org=target_org, run_tests=run_tests)
        if result["success"] and not _coverage_low(result):
            cov = f" ({result['coverage']}% coverage)" if result.get("coverage") is not None else ""
            log(f"  ✓ Deploy green after {round_num} healing round(s){cov}.")
            break

    result["healing"] = healing
    return result
