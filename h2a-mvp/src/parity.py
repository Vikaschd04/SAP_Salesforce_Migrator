"""
parity.py — Behavioral parity harness (Phase 0).

Full behavioral equivalence — running the Hybris Java and the generated Apex on
the same inputs and diffing outputs — needs a runnable Hybris instance and
representative data, which we don't have at generation time. What we *can* do
here, honestly and today, is score how well the generated tests assert the
behavior the model itself comprehended: the class's **business rules**.

For each target we check whether every comprehended business rule has a
corresponding assertion in the generated `@isTest` class (keyword-overlap
heuristic), and emit a per-rule parity map plus an overall parity score. This is
a *proxy* for behavioral equivalence — a reviewable checklist and a number that
moves — not a dual-execution oracle. The oracle is Phase 1+ (needs runnable
Hybris); this makes the tests assert behavior instead of merely covering lines.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.generate import extract_method_signatures

# Common words that carry no behavioral signal for keyword matching.
_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "when", "then",
    "must", "should", "will", "shall", "each", "all", "any", "not", "are", "was",
    "has", "have", "its", "their", "value", "values", "method", "class", "given",
    "using", "based", "which", "returns", "return", "should", "these", "those",
    "there", "where", "over", "such", "than", "also", "only", "used", "uses",
}

# Fraction of a rule's keywords that must surface in the test to call it covered.
_COVERAGE_THRESHOLD = 0.4


def _keywords(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-zA-Z]{4,}", text.lower()) if w not in _STOP]


def _has_assertions(test_code: str) -> bool:
    return bool(re.search(r"System\.assert|Assert\.", test_code or "", re.IGNORECASE))


def _rule_covered(rule: str, test_code: str) -> bool:
    """A rule is 'covered' when the test asserts *and* enough of the rule's
    distinctive words appear in the test source. Uses whole-word matching so a
    rule word like 'orders' isn't falsely matched inside a class name like
    'OrderServiceTest'."""
    if not _has_assertions(test_code):
        return False
    keywords = set(_keywords(rule))
    if not keywords:
        return False
    test_lower = (test_code or "").lower()
    hits = sum(1 for k in keywords if re.search(r"\b" + re.escape(k) + r"\b", test_lower))
    return hits / len(keywords) >= _COVERAGE_THRESHOLD


def build_parity(generated: list[dict]) -> dict:
    """
    Score behavioral parity across all generated targets.

    Each `generated` entry is expected to carry `business_rules` (merged from the
    comprehensions of its source classes), `main_class`, `test_class`,
    `target_name`, and `source_classes`.
    """
    targets = []
    total_rules = covered_rules = 0
    targets_with_tests = 0

    for gen in generated:
        rules = gen.get("business_rules", []) or []
        test_code = gen.get("test_class", "")
        if _has_assertions(test_code):
            targets_with_tests += 1

        rule_rows = []
        for rule in rules:
            covered = _rule_covered(rule, test_code)
            rule_rows.append({"rule": rule, "covered": covered})
            total_rules += 1
            covered_rules += 1 if covered else 0

        score = round(100.0 * sum(r["covered"] for r in rule_rows) / len(rule_rows)) if rule_rows else None
        targets.append({
            "target": gen.get("target_name", "Unknown"),
            "sources": [c.get("class_name") for c in gen.get("source_classes", [])],
            "apex_methods": extract_method_signatures(gen.get("main_class", ""), gen.get("target_name", "")),
            "rules": rule_rows,
            "score": score,
        })

    overall_score = round(100.0 * covered_rules / total_rules) if total_rules else None
    return {
        "targets": targets,
        "overall": {
            "rules_total": total_rules,
            "rules_covered": covered_rules,
            "score": overall_score,
            "targets_with_tests": targets_with_tests,
            "targets_total": len(generated),
        },
    }


def _covered_count(gen: dict) -> int:
    """How many of a target's business rules its current test class asserts."""
    test_code = gen.get("test_class", "")
    return sum(1 for r in (gen.get("business_rules") or []) if _rule_covered(r, test_code))


def close_parity_gaps(generated: list[dict], output_dir: str, *, offline: bool = False,
                      schema: dict | None = None, max_attempts: int = 1, log=print) -> dict:
    """
    Turn the parity harness from a *measurement* into an *improvement*: for every
    target with un-asserted business rules, ask the model to add assertions for
    exactly those rules, rewrite the test class on disk + in memory, and re-score
    — up to `max_attempts` rounds.

    Returns {"targets_improved": [...], "rules_closed": int, "rounds": int}.
    """
    from src.generate import strengthen_parity

    classes_dir = Path(output_dir) / "force-app" / "main" / "default" / "classes"
    summary = {"targets_improved": [], "rules_closed": 0, "rounds": 0}

    for attempt in range(1, max_attempts + 1):
        pending = []
        for gen in generated:
            rules = gen.get("business_rules") or []
            if not rules:
                continue
            test_code = gen.get("test_class", "")
            uncovered = [r for r in rules if not _rule_covered(r, test_code)]
            if uncovered:
                pending.append((gen, uncovered))
        if not pending:
            break

        summary["rounds"] = attempt
        improved_this_round = False
        for gen, uncovered in pending:
            name = gen["target_name"]
            before = _covered_count(gen)
            log(f"    ⚕ Strengthening {name} tests to assert {len(uncovered)} business rule(s)")
            try:
                new_test = strengthen_parity(gen.get("main_class", ""), gen.get("test_class", ""),
                                             name, uncovered, schema=schema, offline=offline)
            except Exception as ex:  # never abort the run for a parity miss
                log(f"      ⚠ parity strengthen failed for {name}: {str(ex)[:120]}")
                continue
            # Never overwrite a good test with empty or non-Apex (e.g. a truncated
            # JSON wrapper that couldn't be parsed) — keep the original instead.
            if (not new_test or not new_test.strip() or new_test.lstrip().startswith("{")
                    or new_test == gen.get("test_class", "")):
                continue
            gen["test_class"] = new_test
            test_path = classes_dir / f"{name}Test.cls"
            if test_path.parent.exists():
                test_path.write_text(new_test, encoding="utf-8")
            gained = _covered_count(gen) - before
            if gained > 0:
                summary["rules_closed"] += gained
                if name not in summary["targets_improved"]:
                    summary["targets_improved"].append(name)
                improved_this_round = True
        if not improved_this_round:
            break

    return summary


def write_parity_md(output_dir: str, parity: dict) -> str:
    """Write PARITY.md — the reviewable behavioral-parity checklist."""
    o = parity["overall"]
    lines = [
        "# Behavioral Parity Report",
        "",
        "Scores how well each generated `@isTest` class asserts the **business "
        "rules** comprehended from the Hybris source. This is a proxy for "
        "behavioral equivalence — a reviewable checklist, not a dual-execution "
        "oracle (that requires a runnable Hybris instance; see the roadmap).",
        "",
        "## Summary",
        "",
        f"- **Overall rule-assertion parity**: "
        + (f"{o['score']}% ({o['rules_covered']}/{o['rules_total']} business rules asserted)"
           if o["score"] is not None else "n/a (no business rules were comprehended)"),
        f"- **Targets with assertion-bearing tests**: {o['targets_with_tests']}/{o['targets_total']}",
        "",
        "> A rule counts as *asserted* when the test contains assertions and enough "
        "of the rule's distinctive terms appear in the test source. Uncovered rules "
        "are the highest-value place to strengthen the generated tests.",
        "",
    ]

    for t in parity["targets"]:
        lines.append(f"## {t['target']}")
        lines.append("")
        lines.append(f"- **Source Hybris**: {', '.join(t['sources']) or '—'}")
        score_str = f"{t['score']}%" if t["score"] is not None else "n/a"
        lines.append(f"- **Rule parity**: {score_str}")
        lines.append("")
        if t["apex_methods"]:
            lines.append("**Apex surface:**")
            lines.append("")
            for m in t["apex_methods"]:
                lines.append(f"- `{m}`")
            lines.append("")
        if t["rules"]:
            lines.append("| Business rule (from comprehension) | Asserted in test? |")
            lines.append("|---|---|")
            for r in t["rules"]:
                mark = "✅ yes" if r["covered"] else "❌ **no — strengthen test**"
                rule_txt = r["rule"].replace("|", "\\|")
                lines.append(f"| {rule_txt} | {mark} |")
            lines.append("")
        else:
            lines.append("_No business rules were comprehended for this target._")
            lines.append("")

    path = Path(output_dir) / "PARITY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)
