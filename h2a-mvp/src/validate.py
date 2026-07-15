"""
validate.py — Static validation + LLM repair.

Tier-1 (offline, deterministic) checks:
  - SOQL / DML inside for/while loops (governor limits)
  - Missing @isTest / missing assertions in test files
  - Missing 'with sharing' on Service/Controller main classes
  - Java/Spring syntax leaks
  - Unbalanced braces
Tier-2 (schema grounding): SOQL/field references to objects/fields that do not
exist in the items.xml-derived schema (see schema.validate_field_references).

`validate_all()` combines both. `repair()` sends the failing code + errors +
schema + upstream signatures back to the model for a targeted fix.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from src.llm import call_llm, _load_config
from src.schema import validate_field_references


# ── Tier-1 static checks ──────────────────────────────────────────────────────

def validate_tier1(apex_code: str, filename: str) -> list:
    issues = []
    is_test_file = filename.endswith("Test.cls") or "Test" in filename

    open_braces, close_braces = apex_code.count("{"), apex_code.count("}")
    if open_braces != close_braces:
        issues.append({
            "rule": "balanced_braces",
            "message": f"Unbalanced braces: {open_braces} open vs {close_braces} close.",
            "severity": "ERROR",
        })

    lines = apex_code.splitlines()
    brace_stack = []
    loop_pattern = re.compile(r"\b(for|while)\b")
    soql_pattern = re.compile(r"\[\s*SELECT\b|Database\.query\(", re.IGNORECASE)
    dml_pattern = re.compile(
        r"\b(insert|update|delete|undelete|upsert)\b\s+[^;]+;|"
        r"Database\.(insert|update|delete|upsert|undelete)\(",
        re.IGNORECASE,
    )

    for i, line in enumerate(lines, 1):
        clean = re.sub(r"//.*|/\*.*?\*/", "", line).strip()
        is_loop_start = bool(loop_pattern.search(clean)) and ("(" in clean or "{" in clean)
        for ch in clean:
            if ch == "{":
                brace_stack.append("loop" if is_loop_start else "other")
                is_loop_start = False
            elif ch == "}" and brace_stack:
                brace_stack.pop()
        if "loop" in brace_stack or is_loop_start:
            if soql_pattern.search(clean):
                issues.append({"rule": "soql_in_loop",
                               "message": f"Line {i}: SOQL query inside a loop.",
                               "severity": "ERROR"})
            if dml_pattern.search(clean) and not clean.startswith(("System.", "Assert.")):
                issues.append({"rule": "dml_in_loop",
                               "message": f"Line {i}: DML operation inside a loop.",
                               "severity": "ERROR"})

    if is_test_file:
        if "@isTest" not in apex_code:
            issues.append({"rule": "missing_istest",
                           "message": "Test class missing '@isTest' annotation.",
                           "severity": "ERROR"})
        if not re.search(r"System\.assert|Assert\.", apex_code, re.IGNORECASE):
            issues.append({"rule": "missing_assert",
                           "message": "Test class has no System.assert / Assert statement.",
                           "severity": "ERROR"})
    else:
        if ("Service" in filename or "Controller" in filename) and "with sharing" not in apex_code:
            issues.append({"rule": "missing_with_sharing",
                           "message": "Service/Controller class missing 'with sharing'.",
                           "severity": "WARNING"})

    if re.search(r"\bpackage\s+[\w\.]+;", apex_code):
        issues.append({"rule": "java_syntax_leak",
                       "message": "Java 'package' statement found.", "severity": "ERROR"})
    if "import org.springframework" in apex_code or "import java." in apex_code:
        issues.append({"rule": "java_syntax_leak",
                       "message": "Java/Spring 'import' statement found.", "severity": "ERROR"})
    if any(a in apex_code for a in ("@Autowired", "@Service", "@Component", "@RestController")):
        issues.append({"rule": "java_syntax_leak",
                       "message": "Java/Spring annotation found.", "severity": "ERROR"})
    return issues


def validate_all(apex_code: str, filename: str, schema: dict | None = None) -> list:
    """Tier-1 checks + schema field grounding."""
    issues = validate_tier1(apex_code, filename)
    if schema:
        issues.extend(validate_field_references(apex_code, schema))
    return issues


# ── LLM repair ────────────────────────────────────────────────────────────────

_REPAIR_SCHEMA = {
    "type": "object",
    "properties": {"code": {"type": "string", "description": "The corrected, complete Apex source."}},
    "required": ["code"],
    "additionalProperties": False,
}


def _load_repair_template() -> str:
    return (Path(__file__).resolve().parent / "prompts" / "repair.txt").read_text(encoding="utf-8")


def repair(apex_code: str, issues: list, *, attempt: int = 1, offline: bool = False,
           signatures: list | None = None, schema: dict | None = None,
           schemas: list | None = None) -> str:
    """Repair Apex using the LLM, grounded in the errors, schema, and signatures."""
    config = _load_config()
    max_tokens = config.get("max_tokens", {}).get("generate", 4000)

    issues_str = "\n".join(f"- [{i['severity']}] {i['rule']}: {i['message']}" for i in issues)

    mappings_file = config.get("mappings_file", "mappings/hybris_to_apex.yaml")
    mappings_path = Path(__file__).resolve().parent.parent / mappings_file
    with open(mappings_path, "r", encoding="utf-8") as f:
        mappings = yaml.safe_load(f)
    constraints_str = "\n".join(f"- {c}" for c in mappings.get("constraints", []))

    extra = ""
    if signatures:
        extra += "\n== Upstream signatures ==\n" + "\n".join(f"- {s}" for s in signatures[:100]) + "\n"
    if schema:
        from src.schema import schema_prompt_block
        extra += "\n== SObject schema ==\n" + schema_prompt_block(schema) + "\n"
    elif schemas:  # legacy list-of-item-type dicts
        extra += "\n== SObject schema ==\n"
        for item in schemas[:50]:
            name = item.get("code") or item.get("name")
            fields = [f.get("qualifier") or f.get("name") for f in item.get("attributes", item.get("fields", []))]
            fields = [f for f in fields if f]
            if fields:
                extra += f"- {name}__c: {', '.join(f'{f}__c' for f in fields)}\n"

    prompt = _load_repair_template().format(
        apex_code=apex_code, issues=issues_str, constraints=constraints_str)
    if extra:
        prompt = prompt.replace("== Instructions ==", extra + "\n== Instructions ==")

    result = call_llm(
        stage=f"repair_attempt_{attempt}",
        prompt=prompt,
        max_tokens=max_tokens,
        offline=offline,
        json_schema=_REPAIR_SCHEMA,
        effort=config.get("effort", {}).get("generate", "high"),
    )

    parsed = result.get("parsed")
    if parsed and parsed.get("code"):
        content = parsed["code"]
    else:
        content = result.get("content", "").strip()
        if "```" in content:
            blocks = re.findall(r"```(?:apex|java|cls)?\s*\n(.*?)```", content, re.DOTALL)
            if blocks:
                content = blocks[0].strip()

    from src.generate import clean_java_artifacts
    return clean_java_artifacts(content)
