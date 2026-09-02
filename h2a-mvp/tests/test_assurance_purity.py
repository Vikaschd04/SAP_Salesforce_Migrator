"""The assurance layer must not learn what platform it is judging. [1.15]

30% of the engine — the rule ledger, triage, blast radius, provenance, alignment,
characterization, replay, checkpoints, sign-off, forecast — is reused unchanged by every
pipeline. That reuse is the entire architectural bet: it is why a second migration path
costs adapters rather than a rewrite, and why the differentiator does not have to be
rebuilt per platform.

It is also the easiest thing to lose by accident. One `from src.adapters import ...` for a
quick fix, and the layer silently becomes Salesforce-only again — with nothing failing,
because the shipped pipeline is Salesforce and the tests would still pass.

So it is enforced rather than documented. Two rules:

**Hard, zero tolerance** — no assurance module may import an adapter or the pipeline
registry. This holds today with no exceptions, and any new violation fails CI.

**A ratchet** — platform vocabulary in code. Four modules still carry some, tracked below
against the item that clears each. The allowlist is exact, so adding a *new* platform word
to an already-listed module fails too. It can only shrink.
"""
import ast
import pathlib
import re

import pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"

ASSURANCE_MODULES = [
    "rule_ledger", "characterize", "provenance", "alignment", "triage",
    "blast", "replay", "signoff", "checkpoint", "forecast", "pricing",
]

_PLATFORM_WORD = re.compile(
    r"\bapex\b|\bsalesforce\b|\bsobject\b|\bsoql\b|__c\b|fflib|sfdx|\blwc\b|"
    r"\bhybris\b|\bimpex\b|\bmagento\b|\bphp\b",
    re.IGNORECASE,
)

#: Known platform vocabulary, and the delivery-plan item that removes it. Shrink only.
#: A module absent from this map must have none at all.
KNOWN_DEBT = {
    "characterize": ({"apex", "hybris"}, "1.13 — split into mine / plan / emit"),
    "provenance":   ({"apex"},           "1.14 — rename apex_* to target_*"),
    "alignment":    ({"apex"},           "1.14 — rename apex_* to target_*"),
    "signoff":      ({"apex", "salesforce"}, "1.14 — target-neutral report wording"),
}


def _module_path(name: str) -> pathlib.Path:
    return SRC / f"{name}.py"


def _code_only(src: str) -> str:
    """Source with docstrings and comments removed.

    Prose may name a platform — an example is often the clearest way to explain a rule.
    What must not happen is *logic* branching on one.
    """
    tree = ast.parse(src)
    out = src
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                out = out.replace(doc, "")
    return re.sub(r"#.*", "", out)


def _imports(src: str) -> set:
    names = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    return names


@pytest.mark.parametrize("module", ASSURANCE_MODULES)
def test_no_assurance_module_imports_an_adapter(module):
    """The hard rule. An adapter import is the layer choosing a platform."""
    offenders = sorted(
        i for i in _imports(_module_path(module).read_text())
        if "adapters" in i or i == "src.pipeline"
    )
    assert not offenders, (
        f"src/{module}.py imports {offenders} — the assurance layer must work for every "
        "pipeline, so it cannot depend on one platform's adapter or on the registry.")


@pytest.mark.parametrize("module", ASSURANCE_MODULES)
def test_platform_vocabulary_only_shrinks(module):
    """The ratchet. Existing debt is recorded; new debt fails."""
    found = {w.lower() for w in _PLATFORM_WORD.findall(_code_only(_module_path(module).read_text()))}
    allowed, owner = KNOWN_DEBT.get(module, (set(), ""))

    new = found - allowed
    assert not new, (
        f"src/{module}.py introduces platform vocabulary in code: {sorted(new)}. "
        "The assurance layer is shared by every pipeline — if this is genuinely "
        "unavoidable, add it to KNOWN_DEBT with the item that will remove it.")

    # Debt that has been paid must be removed from the map, or the ratchet loosens
    # silently and stops protecting anything.
    stale = allowed - found
    assert not stale, (
        f"src/{module}.py no longer contains {sorted(stale)} — remove it from KNOWN_DEBT "
        f"(owner: {owner}) so the ratchet stays tight.")


def test_the_debt_map_only_lists_real_assurance_modules():
    """A typo in KNOWN_DEBT would silently exempt nothing and protect nothing."""
    unknown = sorted(set(KNOWN_DEBT) - set(ASSURANCE_MODULES))
    assert not unknown, f"KNOWN_DEBT lists non-assurance modules: {unknown}"


def test_most_of_the_assurance_layer_is_already_clean():
    """The bet is only worth making if it is mostly true today, not aspirational."""
    clean = [m for m in ASSURANCE_MODULES if m not in KNOWN_DEBT]
    assert len(clean) >= len(ASSURANCE_MODULES) // 2, (
        f"only {len(clean)}/{len(ASSURANCE_MODULES)} assurance modules are platform-neutral")
