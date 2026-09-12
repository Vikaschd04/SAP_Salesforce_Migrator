"""No run may describe itself in the other migration's words. [1.63]

This defect has now been found and fixed five times, in five different surfaces: the
reports (1.39), the MIGRATION_PLAN prose (1.39), the Builder's RAG grounding (1.51), the
system prompt and response schema (1.56–1.58), and the cockpit (1.61–1.62). Every time it
was fixed by hand, in one place, and every time it came back somewhere else — because
platform vocabulary keeps being written into code that has no business owning it.

A user watching an Adobe→Hybris run was told their hazards mattered "On Salesforce", that
their generated Java was "Salesforce Apex", and that they should connect an org with
`sf org login web` to a platform that has no orgs.

So this stops being a matter of remembering. It runs both migrations and reads everything
a person is shown — every event the cockpit renders, every report a reviewer opens — and
fails if either speaks the other's language.

    pytest tests/test_no_cross_platform_leak.py
"""

import contextlib
import io
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: Words that belong to one platform and are wrong in the other's run. Deliberately the
#: unambiguous ones: `Flow` and `Model` are English before they are platform nouns, and a
#: check that cries wolf is one people learn to skip.
VOCABULARY = {
    "salesforce": re.compile(
        r"\b(Salesforce|Apex|SObject|SOQL|sfdx|force-app|fflib|governor limit|"
        r"Visualforce|@isTest)\b|\bsf org\b|\w+__c\b", re.I),
    "hybris": re.compile(
        r"\b(Hybris|FlexibleSearch|ImpEx|items\.xml|Backoffice|Spartacus|"
        r"AbstractJobPerformable|CronJobModel)\b", re.I),
}

#: A run may name the *other* platform when it is deliberately comparing itself to it.
#: The forecast says its estimates are "carried over from the Hybris→Salesforce pair; NOT
#: measured on PHP→Java", which is the honest thing to say and mentions both by name.
ALLOWED = re.compile(
    r"carried over from|NOT measured on|Hybris→Salesforce|Adobe→Hybris|"
    r"hybris->salesforce|adobe->hybris", re.I)


#: Filesystem paths are facts about where the code lives, not about the migration. This
#: repository is checked out under `SAP_Salesforce_Converter`, so every absolute path in
#: every event contains the word — and flagging that would make the guard unusable on the
#: one machine it most needs to run on.
_PATHS = re.compile(r"[\w./\\-]*[/\\][\w./\\ -]*")


def _offending(text: str, forbidden: re.Pattern) -> list:
    out = []
    for line in (text or "").splitlines():
        if ALLOWED.search(line):
            continue
        prose = _PATHS.sub(" ", line)
        m = forbidden.search(prose)
        if m:
            out.append(f"{m.group(0)!r} in: {line.strip()[:110]}")
    return out


def _run(corpus: str):
    """One migration, capturing everything a person would be shown."""
    import tempfile

    from src.agentic.orchestrator import run_agentic_migration

    out = pathlib.Path(tempfile.mkdtemp())
    events: list = []
    with contextlib.redirect_stdout(io.StringIO()):
        run_agentic_migration(str(ROOT / "Testing" / corpus), str(out), offline=True,
                              on_event=events.append)
    return events, out


@pytest.mark.slow
def test_an_adobe_to_hybris_run_never_speaks_salesforce():
    """Checked in this direction only, and deliberately.

    Salesforce is neither the source nor the target of Adobe→Hybris, so *any* mention is
    wrong and a word list can say so without judgement. The reverse is not symmetric:
    Hybris→Salesforce reads Hybris source, so it names Hybris constantly and correctly —
    in file paths, in anti-patterns about the source, in "On SAP Hybris:" describing what
    the original does. Only the sentences about what it *produces* would be wrong there,
    and no regex can tell those apart. A check that cannot be precise should not pretend.
    """
    corpus, pattern = "appointment-demo", VOCABULARY["salesforce"]
    events, out = _run(corpus)

    # What the cockpit renders.
    problems = []
    for e in events:
        # The source tree legitimately contains the source platform's own file names.
        if e.get("type") in ("discovery", "analyzed"):
            continue
        problems += [f"event {e.get('type')}: {p}"
                     for p in _offending(json.dumps(e, default=str), pattern)]

    # What a reviewer reads. The output *path* is a filesystem fact, not prose.
    for md in sorted(out.glob("*.md")):
        text = "\n".join(l for l in md.read_text(encoding="utf-8").splitlines()
                         if "**Output**" not in l and "**Source**" not in l)
        problems += [f"{md.name}: {p}" for p in _offending(text, pattern)]

    assert not problems, (
        f"an Adobe→Hybris run used Salesforce vocabulary:\n  " + "\n  ".join(problems[:12]))


def test_the_check_can_actually_fail():
    """A guard that cannot fail guards nothing — and this one is only as good as its
    word list, which is easy to write too narrowly to ever fire."""
    assert _offending("Generated Salesforce Apex", VOCABULARY["salesforce"])
    assert _offending("query it with FlexibleSearch", VOCABULARY["hybris"])
    assert _offending("connect with sf org login web", VOCABULARY["salesforce"])
    assert _offending("deploys Order__c", VOCABULARY["salesforce"])


def test_a_deliberate_comparison_is_allowed():
    """The forecast says its numbers are "carried over from the Hybris→Salesforce pair;
    NOT measured on PHP→Java". Naming both is the honest thing to do there."""
    assert not _offending(
        "carried over from the Hybris→Salesforce pair; NOT measured on PHP→Java",
        VOCABULARY["salesforce"])


# ── absence has to survive the crossing into JavaScript [1.64] ───────────────

@pytest.mark.slow
def test_a_target_with_no_org_sends_no_org_data():
    """The first review gate on an Adobe→Hybris run said:

        Target org not inspected — . This migration is planned against the source
        alone; connect an org with `sf org login web` to reconcile against what it
        already contains.

    SAP Hybris has no orgs, and the engine had skipped the check correctly since 1.33.
    The Blackboard's default for `orgfit` is `{}`, and an empty dict is falsy in Python
    and **truthy** in JavaScript — so the gate sent "no org data" and the cockpit read
    "an org object with no fields". The dangling `— .` is the missing `reason`.

    Checked at the *gate payload*, because an unsupervised run builds no gates and
    looking at the wrong one is how this was first misdiagnosed as a stale deploy.
    """
    import tempfile

    from src.agentic.orchestrator import run_agentic_migration

    seen = {}

    def gate(name, payload):
        seen[name] = payload
        return {"decision": "approve"}

    with contextlib.redirect_stdout(io.StringIO()):
        run_agentic_migration(str(ROOT / "Testing" / "appointment-demo"),
                              tempfile.mkdtemp(), offline=True, gate=gate)

    assert "discovery" in seen, "no discovery gate was built"
    assert seen["discovery"].get("orgfit") is None, (
        "an empty container reads as presence in the browser")


@pytest.mark.slow
def test_no_gate_field_is_an_empty_container():
    """The general form. Any `{}` or `[]` on this wire is a Python author meaning
    "nothing" and a TypeScript reader seeing "something" — every one is a rendered panel
    with no content in it, waiting to be found by a user rather than a test."""
    import tempfile

    from src.agentic.orchestrator import run_agentic_migration

    seen = {}

    def gate(name, payload):
        seen[name] = payload
        return {"decision": "approve"}

    with contextlib.redirect_stdout(io.StringIO()):
        run_agentic_migration(str(ROOT / "Testing" / "appointment-demo"),
                              tempfile.mkdtemp(), offline=True, gate=gate)

    # `processes` is exempt: its reader guards on `.length`, so an empty list is read as
    # emptiness rather than presence. Listed by name so the exemption is a decision.
    guarded = {"processes"}
    empties = [f"{g}.{k}" for g, p in seen.items() for k, v in p.items()
               if k not in guarded and (v == {} or v == [])]
    assert not empties, f"empty containers cross the wire as truthy: {empties}"
