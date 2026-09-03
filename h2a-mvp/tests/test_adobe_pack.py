"""The Adobe Commerce → SAP Hybris knowledge pack. [3.8]

A pack is the platform-pair knowledge a migration runs on, and it is *data* — which is
most of what makes a second pipeline adapters-plus-content rather than a rewrite. That
only holds if both packs answer the same contract, so these tests compare them rather than
checking one in isolation.

The content tests are deliberately about the things this pair gets *wrong*. A prompt that
says "use a decorator" without saying why an interceptor silently always calls through
produces an interceptor.
"""

import re
from pathlib import Path

import pytest

from src import packs, runctx

PACKS = Path(__file__).resolve().parent.parent / "packs"
ADOBE = PACKS / "adobe_to_hybris"
SALESFORCE = PACKS / "hybris_to_salesforce"


@pytest.fixture
def adobe_pack():
    """Pin the pipeline, then put it back exactly as it was.

    Restoring it to a *different* value rather than to the previous one leaked into every
    later test in the session: `current_target()` stopped being None outside a v2 run, and
    two seam tests failed for a reason that had nothing to do with them.
    """
    token = runctx._pipeline_id.set("adobe->hybris")
    try:
        yield
    finally:
        runctx._pipeline_id.reset(token)


def _placeholders(path: Path) -> set:
    return set(re.findall(r"\{(\w+)\}", path.read_text(encoding="utf-8")))


# ── both packs answer the same contract ───────────────────────────────────────

def test_both_packs_have_the_same_prompts():
    assert ({p.name for p in (ADOBE / "prompts").glob("*.txt")} ==
            {p.name for p in (SALESFORCE / "prompts").glob("*.txt")})


@pytest.mark.parametrize("name", ["comprehend.txt", "generate.txt", "repair.txt",
                                  "generate_system.txt"])
def test_a_prompt_uses_only_placeholders_its_counterpart_uses(name):
    """A pack that invents a placeholder renders with a literal `{foo}` in the prompt and
    nothing fails — the model simply reads a stray brace."""
    assert _placeholders(ADOBE / "prompts" / name) == \
        _placeholders(SALESFORCE / "prompts" / name)


def test_the_placeholder_names_are_platform_neutral():
    """They are the shared contract. `{java_source}` holding PHP and `{apex_code}` holding
    Java is the same mistake 1.14 fixed in the provenance keys."""
    everything = set()
    for p in (ADOBE / "prompts").glob("*.txt"):
        everything |= _placeholders(p)
    for banned in ("java_source", "apex_code", "apex_kind"):
        assert banned not in everything
    assert {"source_code", "target_code", "target_kind"} <= everything


def test_the_pack_resolves_from_the_run_context(adobe_pack):
    assert packs.pack_dir().name == "adobe_to_hybris"
    for name in ("comprehend", "generate", "generate_system", "repair"):
        assert packs.prompt(name).strip()


def test_the_mappings_cover_every_layer_the_reader_produces(adobe_pack):
    """A layer with no rules generates against no guidance at all."""
    from src.adapters.php_reader import _LAYERS

    produced = {layer for _, layer in _LAYERS} - {"Test", "View", "Controller", "Trait",
                                                  "Command", "Setup"}
    assert produced <= set(packs.mappings()["layers"]) | {"Api"}


# ── the prompts say the right platform ────────────────────────────────────────

def test_no_prompt_asks_for_salesforce():
    """The failure mode is silent: a generate prompt mentioning SOQL produces Apex-shaped
    Java, which parses as neither."""
    for p in (ADOBE / "prompts").glob("*.txt"):
        text = p.read_text().lower()
        for banned in ("soql", "@istest", "with sharing", "__c", "governor limit"):
            # Allowed only where the prompt is forbidding it.
            for line in text.splitlines():
                if banned in line:
                    assert "never" in line or "no " in line or "not " in line, \
                        f"{p.name}: {line.strip()[:80]}"


def test_the_system_prompt_names_the_hybris_idioms():
    text = (ADOBE / "prompts" / "generate_system.txt").read_text()
    for idiom in ("AbstractJobPerformable", "setter injection", "FlexibleSearch",
                  "items.xml", "BigDecimal"):
        assert idiom in text, idiom


def test_the_system_prompt_forbids_silent_no_ops():
    """A method that silently does nothing ships; one that refuses is noticed."""
    text = (ADOBE / "prompts" / "generate_system.txt").read_text()
    assert "UnsupportedOperationException" in text
    assert "silently does nothing is worse" in text


def test_the_comprehend_prompt_reads_php_as_php():
    text = (ADOBE / "prompts" / "comprehend.txt").read_text()
    assert "docblock" in text
    assert "getData" in text
    assert "di.xml" in text, "a plugin's purpose is in its wiring, not its class"


def test_the_comprehend_prompt_asks_for_this_pairs_risks():
    text = (ADOBE / "prompts" / "comprehend.txt").read_text()
    for risk in ("$proceed", "mutates the object carried by the event", "float",
                 "ObjectManager"):
        assert risk in text, risk


# ── the knowledge corpus ──────────────────────────────────────────────────────

def test_the_corpus_covers_what_this_pair_gets_wrong():
    names = {p.name for p in (ADOBE / "knowledge").glob("*.md")}
    assert {"flexiblesearch.md", "interceptor_vs_decorator.md", "items_and_models.md",
            "cronjobs.md", "php_to_java_types.md"} <= names


def test_the_decorator_document_explains_why_the_wrong_choice_is_quiet():
    """A model that has read "use a decorator" still writes an interceptor unless it has
    read why an interceptor silently always calls through."""
    text = " ".join((ADOBE / "knowledge" / "interceptor_vs_decorator.md").read_text().split())
    assert "always calls through" in text
    assert "nothing in review looks odd" in text


def test_the_cron_document_carries_both_behavioural_differences():
    text = (ADOBE / "knowledge" / "cronjobs.md").read_text()
    assert "0 30 3 ? * 1" in text, "the day-of-week shift, with a worked example"
    assert "every node" in text


def test_the_items_document_distinguishes_extending_from_declaring():
    text = (ADOBE / "knowledge" / "items_and_models.md").read_text()
    assert 'autocreate="false" generate="false"' in text
    assert "half a customer" in text


def test_the_types_document_refuses_to_infer_from_usage():
    text = (ADOBE / "knowledge" / "php_to_java_types.md").read_text()
    assert "Usage is **not** a source" in text or "not** a source" in text
    assert "BigDecimal" in text


def test_every_knowledge_document_is_substantial():
    """A stub in the corpus is retrieved, injected, and teaches nothing."""
    for p in (ADOBE / "knowledge").glob("*.md"):
        if p.name == "README.md":
            continue
        assert len(p.read_text()) > 600, p.name


def test_the_readme_no_longer_calls_itself_a_scaffold():
    assert "Scaffold." not in (ADOBE / "README.md").read_text()
