"""
rule_ledger.py — completeness measured in *business rules*, not files.

The completeness ledger proves every ingested class is accounted for. That is the
wrong unit for the question a customer actually asks, which is never "did you convert
all the files" but "does it still do what it did". A migration can convert 100% of
classes and still lose the rule that says orders over ₹5000 get a 10% discount.

So this ledger takes every business rule the Comprehender extracted and follows it
through to the generated code, giving each one a verdict:

    asserted     — implemented, and the generated test references what it describes
    implemented  — present in a built artifact, but no test evidence for it
    at_risk      — its target failed to generate; the rule needs manual migration
    dropped      — no artifact carries it (its class was skipped, or it was lost)

`dropped` is the row that matters and that nothing else reports: a rule extracted from
the source that no generated artifact accounts for.

**On the strength of "asserted":** it is a *heuristic* — the test's text overlaps the
rule's distinctive terms (see parity._rule_covered). That is real evidence and it is
honest to report, but it is not proof of behavioral equivalence. Proof needs the
characterization-test harness (replaying the customer's own recorded cases); this
ledger is what makes the gap visible in the meantime.
"""

from __future__ import annotations

import hashlib

from src.parity import _rule_covered, _has_assertions

_STATUS_ORDER = {"dropped": 0, "at_risk": 1, "implemented": 2, "asserted": 3}


def rule_id(source_class: str, rule: str) -> str:
    """Stable short id for a rule, so it can be tracked across runs and reports."""
    return "R-" + hashlib.md5(f"{source_class}|{rule}".strip().encode("utf-8")).hexdigest()[:8]


def build_rule_ledger(bb) -> dict:
    """Follow every extracted business rule through to the generated code."""
    # Which artifact (if any) carries each source class, and did it build?
    art_of: dict[str, object] = {}
    for a in bb.artifacts:
        for c in a.source_classes:
            name = c.get("class_name")
            if name:
                art_of[name] = a

    # Why a class produced no artifact — the reason a rule ends up dropped.
    skip_reason: dict[str, str] = {}
    for p in bb.plan:
        if p.target_kind == "Skip":
            for c in p.source_classes:
                skip_reason[c.get("class_name")] = p.rationale or "skipped by the plan"
    for sk in getattr(bb, "frontend_skipped", []) or []:
        skip_reason.setdefault(sk.get("class_name", ""), sk.get("reason", "no business logic"))

    rows: list[dict] = []
    for source_class, u in (bb.comprehensions or {}).items():
        if not isinstance(u, dict):
            continue
        for rule in (u.get("business_rules") or []):
            rule = (rule or "").strip()
            if not rule:
                continue
            art = art_of.get(source_class)
            if art is None:
                status = "dropped"
                evidence = skip_reason.get(source_class) or "no generated artifact carries this rule"
                target = "—"
            elif getattr(art, "status", "") == "error":
                status = "at_risk"
                evidence = "the target failed to generate — migrate this rule by hand"
                target = art.target_name
            else:
                target = art.target_name
                test_code = getattr(art, "test_class", "") or ""
                if _rule_covered(rule, test_code):
                    status, evidence = "asserted", "the generated test references this rule's terms"
                elif not _has_assertions(test_code):
                    status, evidence = "implemented", "no assertions in the generated test"
                else:
                    status, evidence = "implemented", "tests exist but none clearly cover this rule"
            rows.append({
                "id": rule_id(source_class, rule), "rule": rule,
                "source": source_class, "target": target,
                "status": status, "evidence": evidence,
            })

    rows.sort(key=lambda r: (_STATUS_ORDER.get(r["status"], 9), r["source"], r["rule"]))
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    total = len(rows)
    preserved = counts.get("asserted", 0) + counts.get("implemented", 0)
    return {
        "rules": rows,
        "summary": {
            "total": total,
            "asserted": counts.get("asserted", 0),
            "implemented": counts.get("implemented", 0),
            "at_risk": counts.get("at_risk", 0),
            "dropped": counts.get("dropped", 0),
            "preserved": preserved,
            # The headline: of the rules we found, how many are backed by a test.
            "assured_pct": round(100.0 * counts.get("asserted", 0) / total) if total else None,
            "preserved_pct": round(100.0 * preserved / total) if total else None,
        },
    }


def headline(summary: dict) -> str:
    """One line a stakeholder can read without context."""
    t = summary.get("total") or 0
    if not t:
        return ("No business rules were extracted — run with a real provider "
                "(mock comprehension does not infer rules).")
    line = (f"{summary['asserted']}/{t} business rules preserved and asserted "
            f"({summary.get('assured_pct', 0)}%)")
    tail = []
    if summary.get("implemented"):
        tail.append(f"{summary['implemented']} implemented without test evidence")
    if summary.get("at_risk"):
        tail.append(f"{summary['at_risk']} at risk")
    if summary.get("dropped"):
        tail.append(f"{summary['dropped']} DROPPED")
    return line + (" · " + ", ".join(tail) if tail else "")


def write_rules_md(output_dir: str, ledger: dict) -> str:
    """BUSINESS_RULES.md — the artifact that answers 'did it still do what it did?'."""
    from pathlib import Path

    s = ledger.get("summary") or {}
    rows = ledger.get("rules") or []
    out = ["# Business Rule Ledger", "",
           "Completeness measured in **business rules**, not files. Every rule the "
           "Comprehender found in the source is listed below with what happened to it.", "",
           f"**{headline(s)}**", ""]

    if s.get("dropped"):
        out += [f"> ⚠️ **{s['dropped']} rule(s) are not carried by any generated artifact.** "
                "These are the highest-risk items in the migration — review them before go-live.", ""]

    out += ["| Status | Count | Meaning |", "|---|---|---|",
            f"| `asserted` | {s.get('asserted', 0)} | Implemented, and the generated test references it |",
            f"| `implemented` | {s.get('implemented', 0)} | Present in generated code, but no test evidence |",
            f"| `at_risk` | {s.get('at_risk', 0)} | Its target failed to generate — migrate by hand |",
            f"| `dropped` | {s.get('dropped', 0)} | **No artifact carries this rule** |", "",
            "> **How `asserted` is decided:** the generated test's text overlaps the rule's "
            "distinctive terms. That is real evidence, but it is a heuristic — not proof of "
            "behavioral equivalence. Treat it as *\"a test plausibly covers this\"*, and use "
            "org-verified runs plus your own regression suite for proof.", ""]

    for status in ("dropped", "at_risk", "implemented", "asserted"):
        group = [r for r in rows if r["status"] == status]
        if not group:
            continue
        out += [f"## {status} ({len(group)})", "",
                "| Id | Rule | From | Target | Evidence |", "|---|---|---|---|---|"]
        for r in group:
            rule = r["rule"].replace("|", "\\|")
            out.append(f"| `{r['id']}` | {rule} | `{r['source']}` | `{r['target']}` | {r['evidence']} |")
        out.append("")

    path = Path(output_dir) / "BUSINESS_RULES.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return str(path)
