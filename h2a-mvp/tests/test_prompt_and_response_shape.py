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

@pytest.fixture(autouse=True)
def _no_pipeline_leak():
    """`runctx` is a ContextVar with no scoping of its own, so a test that pins a pipeline
    pins it for everything that runs afterwards in the same process. Doing that here broke
    eight provenance tests that pass in isolation — the pollution, not the code."""
    import src.runctx as R

    before = R._pipeline_id.get()
    yield
    R._pipeline_id.set(before)


@pytest.fixture
def hybris_prompt():
    """Sections passed explicitly — which is the contract now, and the point of 1.57."""
    from src.adapters.hybris_target import ADAPTER

    return build_system_prompt(_load_mappings(), {}, ADAPTER.prompt_sections)


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
    from src.adapters.salesforce_target import ADAPTER

    sp = build_system_prompt(_load_mappings(), {}, ADAPTER.prompt_sections)
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


# ── the fix has to reach the worker thread [1.57] ────────────────────────────

def test_the_sections_are_passed_in_not_looked_up():
    """The first version of this fix asked `pipeline.current_target()`, which reads a
    ContextVar that is not set inside the Builder's worker threads. It silently returned
    the Salesforce defaults, so two paid runs produced Apex again and looked as though
    the fix had done nothing.

    1.51 fixed this exact mistake in `builders.py` and the lesson did not carry: never
    resolve run identity from ambient state when the caller already holds it.
    """
    import inspect

    from src.generate import _prompt_sections

    src = inspect.getsource(_prompt_sections)
    assert "current_target" not in src.split('"""')[2], "resolved from ambient state again"


def test_the_builder_hands_them_over():
    import inspect

    from src.agentic import builders

    assert "prompt_sections=" in inspect.getsource(builders.BuilderAgent.build)


def test_a_target_without_sections_keeps_the_historical_headings():
    """The v1 path pins no pipeline and is Salesforce by construction."""
    from src.generate import build_system_prompt, _load_mappings

    sp = build_system_prompt(_load_mappings(), {}, None)
    assert "Target SObject schema" in sp


# ── a prompt fix must invalidate what the old prompt produced [1.57] ─────────

def test_the_recipe_covers_the_prompts():
    """`recipe_hash` claimed to be the "identity of how output is produced" and omitted
    the prompts. So the prompt was fixed, every cached artifact stayed valid — provider,
    model, schema and mappings were unchanged — and the next run replayed the same Apex.
    A stale cache that survives the fix for its own staleness makes a corrected system
    look uncorrected."""
    from src.agentic.incremental import recipe_hash

    base = dict(provider="anthropic", model="claude-opus-5", schema={}, mappings={})
    a = recipe_hash(**base, prompts={"generate_system": "be a Hybris engineer"})
    b = recipe_hash(**base, prompts={"generate_system": "be a Salesforce engineer"})
    assert a != b


def test_the_recipe_reads_the_running_pipelines_prompts():
    """Two migrations have different prompts; hashing one while running the other would
    be worse than hashing neither."""
    from src import runctx
    from src.agentic.incremental import pack_prompts

    runctx.set_overrides(pipeline_id="adobe->hybris")
    got = pack_prompts()
    assert "generate_system" in got and got["generate_system"]
    assert "Hybris" in got["generate_system"]
