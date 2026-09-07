"""Two defects from the first Anthropic run of the Adobe→Hybris pipeline. [1.56]

The run cost $15 and was worth it. It produced Salesforce Apex — `public with sharing
class AppointmentDao`, `magemonk_appointment__c`, `Security.stripInaccessible` — on a
migration whose target is SAP Hybris, and merged raw JSON into `.java` files.

Neither was a model failing at a hard task. Both were us.

**The prompt contradicted itself.** `build_system_prompt` hardcoded Salesforce section
headings for *every* pipeline, so the Adobe→Hybris system prompt said, in the pack's own
words, "Output PURE Java only... never emit Salesforce Apex — no SOQL, no `with sharing`,
no `__c` suffixes" and then two sections later "Target SObject schema (write SOQL only
against these objects/fields)". A model resolving that against the concrete instruction is
behaving reasonably.

**The parser kept a wrapper it was written to reject.** Its docstring says the raw
`{"field": "..."}` must never reach a source file. It guarded the *expected* key and
nothing else, so a `{"code": "..."}` response fell through to the plain-text branch and
the brace-wrapped blob was stored as the class — then merged, escaped newlines and all,
into four emitted files.

The assurance layer did not miss any of this: it reported `Assurance: none — not known to
compile` and put all 20 artifacts in must-review. The output was bad and the run said so,
which is the distinction this project exists to hold.
"""

import json

import pytest

from src import runctx
from src.generate import _extract_field, build_system_prompt, _load_mappings


# ── the prompt says one thing ─────────────────────────────────────────────────

@pytest.fixture
def hybris_prompt(monkeypatch):
    runctx.set_overrides(pipeline_id="adobe->hybris")
    return build_system_prompt(_load_mappings(), {})


def test_a_hybris_prompt_never_asks_for_sobjects(hybris_prompt):
    """The heading that caused it. `SObject` has no meaning on this target, and asking
    for one told the model, concretely, that it was writing Salesforce."""
    assert "SObject" not in hybris_prompt


def test_a_hybris_prompt_names_the_target_type_system(hybris_prompt):
    assert "items.xml" in hybris_prompt
    assert "FlexibleSearch" in hybris_prompt


def test_the_type_mapping_heading_names_the_real_languages(hybris_prompt):
    """`Java -> Salesforce type mappings` on a PHP→Java migration is wrong twice."""
    assert "PHP -> Java type mappings" in hybris_prompt
    assert "Java -> Salesforce type mappings" not in hybris_prompt


def test_the_salesforce_prompt_is_unchanged():
    """That pipeline ships, and its baseline is byte-identical — the headings it had are
    the headings it keeps."""
    runctx.set_overrides(pipeline_id="hybris->salesforce")
    sp = build_system_prompt(_load_mappings(), {})
    assert "Java -> Salesforce type mappings" in sp
    assert "Target SObject schema" in sp


# ── the parser keeps only code ────────────────────────────────────────────────

def test_the_requested_shape_is_read():
    assert _extract_field(json.dumps({"main_class": "class A {}"}), "main_class") == "class A {}"


@pytest.mark.parametrize("key", ["code", "source", "java", "apex", "class", "content"])
def test_an_object_of_the_models_own_design_still_yields_the_code(key):
    """The real response was `{"code": "..."}`. Losing the class because the key was not
    the one we asked for is a worse outcome than reading it."""
    assert _extract_field(json.dumps({key: "class A {}"}), "main_class") == "class A {}"


def test_an_unrecognised_object_yields_nothing_rather_than_json():
    """The defect exactly: this used to return the raw JSON, which was then merged into a
    `.java` file complete with braces and escaped newlines. An empty class is a visible
    gap; a brace-wrapped blob is a file that looks generated and is not code."""
    got = _extract_field(json.dumps({"unexpected": "value"}), "main_class")
    assert got == ""


def test_truncated_json_yields_nothing():
    assert _extract_field('{"main_class": "class A', "main_class") == ""


def test_no_shape_ever_returns_something_beginning_with_a_brace():
    """The single property that would have prevented it."""
    for raw in ('{"code": "class A {}"}', '{"zzz": 1}', '{"main_class": "class A',
                '{not json at all', '{"main_class": "class A {}"}'):
        assert not _extract_field(raw, "main_class").lstrip().startswith("{"), raw


def test_plain_and_fenced_responses_still_work():
    assert _extract_field("class A {}", "main_class") == "class A {}"
    assert _extract_field("```java\nclass A {}\n```", "main_class") == "class A {}"
