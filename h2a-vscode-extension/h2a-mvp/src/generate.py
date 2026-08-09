"""
generate.py — Apex code generation from comprehended Java classes.

Production rework:
  - Stable, reusable context (mapping rules, type table, constraints, SObject
    schema, output format) is built once as a *cached system prompt* so every
    class in a repo reuses it at ~0.1x token cost.
  - Generation uses **structured outputs** (a JSON schema) — no more scraping
    `===MARKER===` blocks from free-form text.
  - Only the *scoped* dependency signatures relevant to the class are injected,
    not every signature generated so far.
  - The SObject schema catalog is injected so the model writes SOQL against
    fields that actually exist.

Target mapping:
  DAO        → Selector
  Service    → Service   (Facade merged in)
  Controller → RestResource
  Model/DTO  → SObject (handled by metadata_generator; no Apex class)
  Utility    → Utility
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from src.llm import call_llm, _load_config
from src.schema import schema_prompt_block


# Structured-output schema for one generated artifact.
GENERATION_SCHEMA = {
    "type": "object",
    "properties": {
        "main_class": {"type": "string", "description": "Complete Apex main class source."},
        "test_class": {"type": "string", "description": "Complete @isTest Apex class source."},
        "sobject_refs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Custom objects (X__c) referenced by the main class.",
        },
        "mapping_notes": {"type": "string", "description": "Brief notes on mapping decisions."},
    },
    "required": ["main_class", "test_class", "mapping_notes"],
    "additionalProperties": False,
}

_SKIP_LAYERS = {"Model", "Facade"}


# ── Target planning ───────────────────────────────────────────────────────────

def _get_domain(class_name: str) -> str:
    name = class_name
    if name.startswith("Default"):
        name = name[len("Default"):]
    for suffix in ["Dao", "DAO", "Service", "Facade", "Controller", "Data", "Job"]:
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return name


def lwc_name(class_name: str) -> str:
    """LWC bundle name: camelCase, no 'Component' suffix. ProductListComponent → productList."""
    base = class_name[:-len("Component")] if class_name.endswith("Component") else class_name
    return (base[0].lower() + base[1:]) if base else base


def plan_targets(classes: list[dict]) -> list[dict]:
    """Plan which target Apex artifacts to generate from ingested classes."""
    targets = []
    # ALL of them, not the first. A Hybris facade is always an interface plus a
    # `Default*` implementation, so `next(...)` here silently dropped one of every
    # pair — it never reached a target's source_classes and surfaced downstream as
    # an `unaccounted` row in the completeness ledger on a perfectly normal codebase.
    facade_classes = [c for c in classes if c["layer"] == "Facade"]

    for cls in classes:
        if cls["layer"] in _SKIP_LAYERS:
            continue
        domain = _get_domain(cls["class_name"])
        if cls["layer"] == "DAO":
            target_name = f"{domain}Selector"
        elif cls["layer"] == "Service":
            target_name = f"{domain}Service"
        elif cls["layer"] == "Controller":
            target_name = f"{domain}Controller"
        elif cls["layer"] == "Utility":
            target_name = cls["class_name"]
        elif cls["layer"] == "Job":
            target_name = f"{domain}Scheduler"
        elif cls["layer"] == "Component":
            target_name = lwc_name(cls["class_name"])   # frontend → LWC bundle
        else:
            continue

        source_classes = [cls]
        if cls["layer"] == "Service" and facade_classes:
            source_classes.extend(facade_classes)

        targets.append({
            "target_name": target_name,
            "layer": cls["layer"],
            "source_classes": source_classes,
        })

    # A domain can hold facades with no service to fold them into (a facade over a
    # DAO, or over another extension's service). Without this they would vanish the
    # same way, just less often — so give them a target of their own.
    if facade_classes and not any(t["layer"] == "Service" for t in targets):
        domain = _get_domain(facade_classes[0]["class_name"])
        targets.append({
            "target_name": f"{domain}Service",
            "layer": "Service",
            "source_classes": list(facade_classes),
        })

    return _merge_by_name(targets)


def _merge_by_name(targets: list[dict]) -> list[dict]:
    """Collapse targets that resolve to the same Apex class into one.

    Names are derived from the domain and layer, so `PricingService` (the interface) and
    `DefaultPricingService` (its implementation) both resolve to `PricingService` — the
    universal Hybris idiom. Emitting them as two targets meant generating the same class
    twice and letting the second write win, quietly discarding the first. They are one
    artifact built from both sources, which is also what the LLM needs to see: an
    interface without its implementation is a signature with no behaviour.
    """
    merged: dict[str, dict] = {}
    for t in targets:
        cur = merged.get(t["target_name"])
        if cur is None:
            merged[t["target_name"]] = {**t, "source_classes": list(t["source_classes"])}
            continue
        # Keyed by (name, file), not name alone. Two extensions routinely ship a class
        # of the same simple name — `DefaultOrderService` in acmecore and again in
        # acmeb2b — and they are genuinely different classes. Apex has no namespaces, so
        # they must land in one artifact; deduping by name alone made one of them
        # disappear from that artifact's sources instead, taking its logic with it.
        seen = {(c.get("class_name"), c.get("file")) for c in cur["source_classes"]}
        for c in t["source_classes"]:
            key = (c.get("class_name"), c.get("file"))
            if key not in seen:
                cur["source_classes"].append(c)
                seen.add(key)
    return list(merged.values())


def prepend_review_flag(code: str, native_alt: str, rationale: str = "") -> str:
    """Prepend a MANUAL REVIEW banner to a fully-converted artifact whose logic may
    have a better native Salesforce home. The logic is always converted in full;
    this only marks it for a human to evaluate against `native_alt`."""
    if not native_alt or not code:
        return code
    note = (rationale or "").strip()
    banner = (
        "/*\n"
        f" * MANUAL REVIEW: {native_alt} may be a better long-term home for this logic.\n"
        " * It has been converted to Apex IN FULL for completeness — verify behavioral\n"
        f" * parity against {native_alt} before go-live"
        + (f".\n * Planner rationale: {note}\n" if note else ".\n")
        + " */\n"
    )
    return banner + code


# ── Prompt building ───────────────────────────────────────────────────────────

def _load_prompt_template() -> str:
    return (Path(__file__).resolve().parent / "prompts" / "generate.txt").read_text(encoding="utf-8")


def _load_system_template() -> str:
    path = Path(__file__).resolve().parent / "prompts" / "generate_system.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _load_mappings() -> dict:
    config = _load_config()
    mappings_file = config.get("mappings_file", "mappings/hybris_to_apex.yaml")
    path = Path(__file__).resolve().parent.parent / mappings_file
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get_layer_rules(mappings: dict, layer: str) -> tuple[str, str]:
    info = mappings.get("layers", {}).get(layer, {})
    apex_kind = info.get("apex_kind", "Unknown")
    rules = "\n".join(f"  - {r}" for r in info.get("rules", []))
    return apex_kind, rules


def _format_type_mappings(mappings: dict) -> str:
    return "\n".join(f"  {k} -> {v}" for k, v in mappings.get("types", {}).items())


def _format_constraints(mappings: dict) -> str:
    return "\n".join(f"  - {c}" for c in mappings.get("constraints", []))


def _format_dependency_sigs(dependency_sigs: list[str]) -> str:
    if not dependency_sigs:
        return "  (none — this is a leaf class in the dependency chain)"
    return "\n".join(f"  {s}" for s in dependency_sigs)


def build_system_prompt(mappings: dict, schema: dict | None) -> str:
    """
    Build the stable, cacheable system prompt: role + global rules + type table +
    constraints + SObject schema. Identical across every class in a repo, so it is
    sent once and re-read from cache thereafter.
    """
    parts = [_load_system_template().strip() or (
        "You are an expert Salesforce Apex engineer migrating SAP Hybris "
        "(Java/Spring) code to governor-limit-safe Apex following fflib-style "
        "Enterprise Patterns (Selectors for SOQL, stateless bulk-safe Services, "
        "RestResource controllers). Output pure Apex only — never Java packages, "
        "imports, or Spring annotations."
    )]
    parts.append("\n== Java -> Salesforce type mappings ==\n" + _format_type_mappings(mappings))
    parts.append("\n== Hard constraints (must always hold) ==\n" + _format_constraints(mappings))
    parts.append(
        "\n== Target SObject schema (write SOQL only against these objects/fields) ==\n"
        + schema_prompt_block(schema or {})
    )
    return "\n".join(parts)


def _build_source_summary(source_classes: list[dict], comprehensions: dict) -> tuple[str, str]:
    """Java + comprehension context for the generation prompt.

    Source is slimmed first (imports and generated accessors removed, logic and javadoc
    kept verbatim) — this is the frontier-tier call, so it is where prompt bytes cost the
    most."""
    # Defensive: real-world ingest can yield class dicts missing a field (odd syntax,
    # inner classes, non-Java files). A missing key must never crash generation.
    try:
        from src.slim import slim_classes, enabled as _slim_on
        from src.llm import _load_config
        if _slim_on(_load_config()):
            source_classes = slim_classes(source_classes)[0]
    except Exception:
        pass                      # slimming is an optimisation, never a dependency

    sources, comp_summaries = [], []
    for cls in (source_classes or []):
        name = cls.get("class_name", "UnknownClass")
        layer = cls.get("layer", "")
        source = cls.get("source", "")
        sources.append(f"// --- {name} ({layer}) ---\n{source}")
        comp = comprehensions.get(name, {})
        comp_summaries.append({"class": name, "layer": layer, **comp})
    return "\n\n".join(sources), json.dumps(comp_summaries, indent=2)


# ── Deterministic Java/Spring sanitisation ────────────────────────────────────

def _as_str(v) -> str:
    """Coerce a model-returned field to a string. A well-behaved provider returns
    a string; a misbehaving one (or a proxy) may return a dict/None — never let
    that crash downstream string handling."""
    return v if isinstance(v, str) else ""


def clean_java_artifacts(code: str) -> str:
    """Deterministically strip Java/Spring-isms and convert JUnit asserts."""
    if not isinstance(code, str) or not code:
        return ""
    lines = []
    for line in code.splitlines():
        clean = line.strip()
        if clean.startswith("package ") and clean.endswith(";"):
            continue
        if clean.startswith("import ") and clean.endswith(";") and (
            "java." in clean or "org.springframework" in clean or "com.example" in clean
        ):
            continue
        if clean in ("@Autowired", "@Service", "@Component", "@RestController",
                     "@RequestMapping", "@Override"):
            continue
        if clean.startswith("// package") or clean.startswith("// import"):
            continue
        lines.append(line)
    code = "\n".join(lines)

    # Only convert *bare* JUnit asserts — the (?<![\w.]) guard prevents matching an
    # already-qualified call like System.assertEquals(...) and double-prefixing it
    # into System.System.assertEquals(...).
    code = re.sub(r"(?<![\w.])assertEquals\s*\(", "System.assertEquals(", code)
    code = re.sub(r"(?<![\w.])assertNotEquals\s*\(", "System.assertNotEquals(", code)
    code = re.sub(r"(?<![\w.])assertNull\s*\(([^)]+)\)", r"System.assertEquals(null, \1)", code)
    code = re.sub(r"(?<![\w.])assertNotNull\s*\(([^)]+)\)", r"System.assertNotEquals(null, \1)", code)
    code = re.sub(r"(?<![\w.])assertTrue\s*\(", "System.assert(", code)
    code = re.sub(r"(?<![\w.])assertFalse\s*\(([^)]+)\)", r"System.assert(!(\1))", code)
    code = re.sub(r"\bassert\s+([^;:]+)\s*:\s*([^;]+);", r"System.assert(\1, \2);", code)
    code = re.sub(r"\bassert\s+([^;:]+)\s*;", r"System.assert(\1);", code)
    return code


# ── Response parsing (fallback for non-structured responses) ──────────────────

def _extract_field(raw: str, field: str) -> str:
    """
    Best-effort pull of a single Apex field from a model response that may be a
    JSON object, a fenced code block, or plain text. Critically, if the response
    is a JSON object for this field but is truncated/unparseable, return "" rather
    than let the raw `{"field": "..."}` wrapper get written to a .cls file.
    """
    s = (raw or "").strip()
    if not s:
        return ""
    if s.startswith("{"):
        try:
            obj = json.loads(s)
            if isinstance(obj, dict) and isinstance(obj.get(field), str):
                return obj[field]
        except Exception:
            pass
        if f'"{field}"' in s:      # a JSON object for this field that won't parse → give up
            return ""
    if "```" in s:
        blocks = re.findall(r"```(?:apex|java|cls)?\s*\n(.*?)```", s, re.DOTALL)
        if blocks:
            return blocks[0].strip()
    return s


def _parse_generation_response(content: str) -> dict:
    # A structured response that wasn't pre-parsed (e.g. truncated JSON) — try JSON first.
    stripped = (content or "").strip()
    if stripped.startswith("{"):
        try:
            obj = json.loads(stripped)
            if isinstance(obj, dict) and obj.get("main_class"):
                return {"main_class": obj.get("main_class", ""),
                        "test_class": obj.get("test_class", ""),
                        "mapping_notes": obj.get("mapping_notes", ""),
                        "sobject_refs": obj.get("sobject_refs", [])}
        except Exception:
            pass
    result = {"main_class": "", "test_class": "", "mapping_notes": "", "sobject_refs": []}
    m = re.search(r"===MAIN_CLASS===(.*?)===END_MAIN_CLASS===", content, re.DOTALL)
    if m:
        result["main_class"] = m.group(1).strip()
    m = re.search(r"===TEST_CLASS===(.*?)===END_TEST_CLASS===", content, re.DOTALL)
    if m:
        result["test_class"] = m.group(1).strip()
    m = re.search(r"===MAPPING_NOTES===(.*?)===END_MAPPING_NOTES===", content, re.DOTALL)
    if m:
        result["mapping_notes"] = m.group(1).strip()
    if not result["main_class"] and "```" in content:
        blocks = re.findall(r"```(?:apex|java|cls)?\s*\n(.*?)```", content, re.DOTALL)
        if blocks:
            result["main_class"] = blocks[0].strip()
        if len(blocks) >= 2:
            result["test_class"] = blocks[1].strip()
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def generate_apex(
    target: dict,
    comprehensions: dict,
    dependency_sigs,
    *,
    offline: bool = False,
    schema: dict | None = None,
    mappings: dict | None = None,
    grounding: str = "",
) -> dict:
    """
    Generate the Apex class + test class for one target artifact.

    Args:
        target: plan dict from plan_targets().
        comprehensions: class_name -> comprehension result.
        dependency_sigs: scoped list[str] of upstream signatures, OR a legacy
            dict {target_name: [sigs]} (flattened for backward compatibility).
        schema: SObject schema (from schema.build_schema).
        mappings: pre-loaded mapping rules (avoids re-reading the yaml per call).
    """
    config = _load_config()
    max_tokens = config.get("max_tokens", {}).get("generate", 4000)
    effort = config.get("effort", {}).get("generate", "high")
    mappings = mappings or _load_mappings()

    target_name = target["target_name"]
    layer = target["layer"]
    apex_kind, layer_rules = _get_layer_rules(mappings, layer)

    if isinstance(dependency_sigs, dict):
        flat = []
        for sigs in dependency_sigs.values():
            flat.extend(sigs)
        dependency_sigs = flat

    combined_source, combined_comp = _build_source_summary(target["source_classes"], comprehensions)

    system_prompt = build_system_prompt(mappings, schema)
    template = _load_prompt_template()
    user_prompt = template.format(
        comprehension_json=combined_comp,
        java_source=combined_source,
        apex_kind=apex_kind,
        layer_rules=layer_rules,
        dependency_signatures=_format_dependency_sigs(dependency_sigs),
        target_class_name=target_name,
    )
    if grounding:
        user_prompt += "\n\n" + grounding

    result = call_llm(
        stage=f"generate_{target_name}",
        prompt=user_prompt,
        max_tokens=max_tokens,
        offline=offline,
        system_prompt=system_prompt,
        json_schema=GENERATION_SCHEMA,
        effort=effort,
    )

    parsed = result.get("parsed")
    if not parsed:  # defensive fallback for legacy/marker responses
        parsed = _parse_generation_response(result.get("content", ""))

    return {
        "target_name": target_name,
        "main_class": clean_java_artifacts(_as_str(parsed.get("main_class"))),
        "test_class": clean_java_artifacts(_as_str(parsed.get("test_class"))),
        "mapping_notes": _as_str(parsed.get("mapping_notes")),
        "sobject_refs": parsed.get("sobject_refs") if isinstance(parsed.get("sobject_refs"), list) else [],
        "provider": result.get("provider", ""),
    }


_STRENGTHEN_SCHEMA = {
    "type": "object",
    "properties": {"test_class": {"type": "string",
                                  "description": "The complete, expanded @isTest class."}},
    "required": ["test_class"],
    "additionalProperties": False,
}


def strengthen_tests(main_code: str, test_code: str, target_name: str,
                     current_coverage, *, schema: dict | None = None,
                     offline: bool = False) -> str:
    """
    Expand a generated test class to raise its Apex code coverage above the 75%
    Salesforce deploy threshold — the coverage-heal counterpart to repair().

    Adds test methods for untested branches, error paths, and bulk (200-record)
    scenarios, keeping the existing tests and asserting real outcomes. Grounded
    in the SObject schema so it only references fields that exist.
    """
    config = _load_config()
    max_tokens = config.get("max_tokens", {}).get("generate", 4000)
    effort = config.get("effort", {}).get("generate", "high")
    cov_str = f"~{current_coverage}%" if current_coverage is not None else "below 75%"

    prompt = (
        f"The Apex class `{target_name}` has {cov_str} test coverage — below the 75% "
        "Salesforce requires to deploy. Expand its @isTest class with additional test "
        "methods covering untested branches, null/empty and error paths, and a bulk "
        "(200-record) scenario. Keep all existing test methods. Use "
        "Test.startTest()/Test.stopTest(), assert real outcomes (not just that code ran), "
        "and reference only fields present in the schema. Output pure Apex.\n\n"
        f"== Class under test ==\n{main_code}\n\n"
        f"== Current test class ==\n{test_code}\n\n"
        f"== SObject schema (use only these fields) ==\n{schema_prompt_block(schema or {})}\n\n"
        "Return the COMPLETE expanded @isTest class."
    )

    result = call_llm(
        stage=f"strengthen_{target_name}",
        prompt=prompt,
        max_tokens=max_tokens,
        offline=offline,
        json_schema=_STRENGTHEN_SCHEMA,
        effort=effort,
    )

    parsed = result.get("parsed")
    if parsed and parsed.get("test_class"):
        content = parsed["test_class"]
    else:
        content = _extract_field(result.get("content", ""), "test_class")
    return clean_java_artifacts(content)


def strengthen_parity(main_code: str, test_code: str, target_name: str,
                      uncovered_rules: list, *, schema: dict | None = None,
                      offline: bool = False) -> str:
    """
    Add test assertions for the specific business rules a generated test class
    does NOT yet assert — the parity-driven counterpart to strengthen_tests().

    Where strengthen_tests() chases line coverage, this chases *behavioral*
    coverage: each named rule (comprehended from the Hybris source) gets an
    explicit assertion, turning "tests that run" into "tests that check the
    original logic still holds".
    """
    config = _load_config()
    max_tokens = config.get("max_tokens", {}).get("generate", 4000)
    effort = config.get("effort", {}).get("generate", "high")
    rules_block = "\n".join(f"- {r}" for r in uncovered_rules) or "- (none)"

    prompt = (
        f"The @isTest class for `{target_name}` does not yet assert these business "
        "rules carried over from the original Hybris logic:\n\n"
        f"{rules_block}\n\n"
        "Add focused test methods that build the scenario and ASSERT each rule "
        "explicitly — include the negative/error case where the rule implies one "
        "(e.g. a rule about rejecting bad input should assert the exception). Keep "
        "every existing test method. Use Test.startTest()/Test.stopTest(), assert "
        "real outcomes, and reference only fields present in the schema.\n\n"
        f"== Class under test ==\n{main_code}\n\n"
        f"== Current test class ==\n{test_code}\n\n"
        f"== SObject schema (use only these fields) ==\n{schema_prompt_block(schema or {})}\n\n"
        "Return the COMPLETE expanded @isTest class."
    )

    result = call_llm(
        stage=f"parity_{target_name}",
        prompt=prompt,
        max_tokens=max_tokens,
        offline=offline,
        json_schema=_STRENGTHEN_SCHEMA,
        effort=effort,
    )

    parsed = result.get("parsed")
    if parsed and parsed.get("test_class"):
        content = parsed["test_class"]
    else:
        content = _extract_field(result.get("content", ""), "test_class")
    return clean_java_artifacts(content)


def extract_method_signatures(apex_code: str, class_name: str) -> list[str]:
    """Extract public/global method signatures for downstream dependency injection."""
    sigs = []
    pattern = r"(?:public|global)\s+(?:static\s+)?(\S+)\s+(\w+)\s*\(([^)]*)\)"
    for match in re.finditer(pattern, apex_code):
        return_type, method_name, params = match.group(1), match.group(2), match.group(3).strip()
        sigs.append(f"{class_name}.{method_name}({params}) : {return_type}")
    return sigs


# ── Output writer (SFDX layout) ───────────────────────────────────────────────

_APEX_CLS_META = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">\n'
    "    <apiVersion>60.0</apiVersion>\n    <status>Active</status>\n</ApexClass>\n"
)


def _write_apex_class(classes_dir, name: str, main_class: str, test_class: str,
                      cls_meta: str) -> list[str]:
    """Write an Apex class (+ its test) with metadata. Returns the paths written."""
    created = []
    for suffix, body in ((".cls", main_class), ("Test.cls", test_class)):
        if suffix == "Test.cls" and not (body and body.strip()):
            continue
        cls_path = classes_dir / f"{name}{suffix}"
        cls_path.write_text(body or "", encoding="utf-8")
        (classes_dir / f"{name}{suffix}-meta.xml").write_text(cls_meta, encoding="utf-8")
        created += [str(cls_path), str(classes_dir / f"{name}{suffix}-meta.xml")]
    return created


def _write_lwc_bundle(lwc_dir, name: str, bundle: dict) -> list[str]:
    """Write an LWC bundle folder: <name>.js/.html/.css/.js-meta.xml + __tests__/<name>.test.js."""
    if not bundle:
        return []
    folder = lwc_dir / name
    folder.mkdir(parents=True, exist_ok=True)
    created = []
    files = [(f"{name}.js", bundle.get("js", "")),
             (f"{name}.html", bundle.get("html", "")),
             (f"{name}.js-meta.xml", bundle.get("meta", ""))]
    if bundle.get("css", "").strip():
        files.append((f"{name}.css", bundle["css"]))
    for fname, body in files:
        (folder / fname).write_text(body, encoding="utf-8")
        created.append(str(folder / fname))
    if bundle.get("test", "").strip():
        tests = folder / "__tests__"
        tests.mkdir(exist_ok=True)
        (tests / f"{name}.test.js").write_text(bundle["test"], encoding="utf-8")
        created.append(str(tests / f"{name}.test.js"))
    return created


def write_outputs(output_dir: str, generated: list[dict], item_types: list[dict],
                  mappings: dict) -> list[str]:
    """Write generated Apex + SFDX config + MAPPING.md in standard SFDX layout."""
    out = Path(output_dir)
    classes_dir = out / "force-app" / "main" / "default" / "classes"
    config_dir = out / "config"
    classes_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    created = []

    sfdx_project = {
        "packageDirectories": [{"path": "force-app", "default": True}],
        "name": "salesforce-h2a-project",
        "namespace": "",
        "sfdxclientversion": "2.0.0",
        "sourceApiVersion": "60.0",
    }
    p = out / "sfdx-project.json"
    p.write_text(json.dumps(sfdx_project, indent=2), encoding="utf-8")
    created.append(str(p))

    scratch_def = {
        "orgName": "H2A Migration Scratch Org",
        "edition": "Developer",
        "features": ["EnableSetPasswordInApi"],
        "settings": {"lightningExperienceSettings": {"enableS1DesktopEnabled": True}},
    }
    p = config_dir / "project-scratch-def.json"
    p.write_text(json.dumps(scratch_def, indent=2), encoding="utf-8")
    created.append(str(p))

    cls_meta = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">\n'
        "    <apiVersion>60.0</apiVersion>\n    <status>Active</status>\n</ApexClass>\n"
    )
    lwc_dir = out / "force-app" / "main" / "default" / "lwc"
    for gen in generated:
        name = gen["target_name"]
        # Frontend target → LWC bundle (+ its @AuraEnabled Apex controller), not a .cls.
        if gen.get("layer") == "Component":
            created += _write_lwc_bundle(lwc_dir, name, gen.get("lwc_bundle", {}))
            ctrl = gen.get("apex_controller") or {}
            if ctrl.get("main_class"):
                created += _write_apex_class(classes_dir, ctrl.get("name") or f"{name}Controller",
                                             ctrl.get("main_class", ""), ctrl.get("test_class", ""),
                                             cls_meta)
            continue
        for suffix, field in ((".cls", "main_class"), ("Test.cls", "test_class")):
            cls_path = classes_dir / f"{name}{suffix}"
            cls_path.write_text(gen.get(field, ""), encoding="utf-8")
            created.append(str(cls_path))
            meta_path = classes_dir / f"{name}{suffix}-meta.xml"
            meta_path.write_text(cls_meta, encoding="utf-8")
            created.append(str(meta_path))

    mapping_md = _build_mapping_md(generated, item_types, mappings)
    p = out / "MAPPING.md"
    p.write_text(mapping_md, encoding="utf-8")
    created.append(str(p))
    return created


def _build_mapping_md(generated: list[dict], item_types: list[dict], mappings: dict) -> str:
    lines = ["# Hybris-to-Apex Mapping Report", "", "## SObject Mapping", ""]
    type_map = mappings.get("types", {})
    for item in item_types:
        lines.append(f"### {item['name']} -> {item['name']}__c")
        lines.append("")
        lines.append("| Hybris Field | Java Type | Apex Field | Apex Type |")
        lines.append("|---|---|---|---|")
        for field in item.get("fields", []):
            apex_type = type_map.get(field["type"], "Text(255)")
            lines.append(f"| {field['name']} | {field['type']} | {field['name']}__c | {apex_type} |")
        lines.append("")

    lines += ["## Layer Mapping", "", "| Hybris Layer | Hybris Class | Apex Class | Apex Kind |", "|---|---|---|---|"]
    layer_info = mappings.get("layers", {})
    for gen in generated:
        source_names = ", ".join(c["class_name"] for c in gen.get("source_classes", []))
        layer = gen.get("layer", "Unknown")
        apex_kind = layer_info.get(layer, {}).get("apex_kind", "Unknown")
        lines.append(f"| {layer} | {source_names} | {gen['target_name']} | {apex_kind} |")
    lines.append("")

    lines += ["## Detailed Mapping Notes", ""]
    for gen in generated:
        lines.append(f"### {gen['target_name']}")
        lines.append("")
        lines.append(gen.get("mapping_notes") or "(No additional notes)")
        lines.append("")

    lines += ["## Constraints Applied", ""]
    for constraint in mappings.get("constraints", []):
        lines.append(f"- {constraint}")
    lines.append("")
    return "\n".join(lines)
