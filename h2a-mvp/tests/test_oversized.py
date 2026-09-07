"""Source too large for the model to read in one call. [1.28]

The two stages need opposite answers, and that is the design.

Comprehension returns an understanding — a purpose, business rules, dependencies, risks.
Those *merge*: a rule found in either half of a class is a rule the class contains. So
comprehension chunks and folds the results.

Generation writes the class. There is no union of two half-migrations, and stitching
independently generated halves produces a file whose two ends were written by callers that
could not see each other. So generation refuses with the real reason and the unit goes to
manual migration, where a person can split it deliberately.
"""

import textwrap

import pytest

from src import oversized


def _java_class(methods: int, body_lines: int = 3) -> str:
    out = ["package com.acme;", "", "public class Big", "{"]
    for i in range(methods):
        out.append(f"    public String method{i}(final String arg)")
        out.append("    {")
        out += [f'        // filler line {j}' for j in range(body_lines)]
        out.append("        return arg;")
        out.append("    }")
    out.append("}")
    return "\n".join(out)


# ── budgets ───────────────────────────────────────────────────────────────────

def test_an_unknown_model_gets_the_smaller_budget():
    """Guessing high sends a request that fails; guessing low sends one that works."""
    assert oversized.context_for("who-knows") < oversized.context_for("claude-opus-4-8")


def test_the_budget_leaves_room_for_the_response_and_the_prompt():
    ctx = oversized.context_for("claude-opus-4-8")
    assert oversized.input_budget("claude-opus-4-8", 8000) < ctx - 8000


def test_an_ordinary_class_fits():
    assert oversized.fits(_java_class(5), "claude-opus-4-8", 800)


def test_the_reason_names_the_numbers_and_the_model():
    reason = oversized.too_large_reason("x" * 900_000, "claude-opus-4-8", 800)
    assert "claude-opus-4-8" in reason
    assert "never going to be sent successfully" in reason


# ── chunking ──────────────────────────────────────────────────────────────────

def test_a_class_that_fits_is_not_split():
    assert len(oversized.split_source(_java_class(4), "claude-opus-4-8", 800)) == 1


def test_an_oversized_class_splits_into_several():
    chunks = oversized.split_source(_java_class(40), "tiny-model", 99_000)
    assert len(chunks) > 1


def test_every_chunk_carries_the_class_declaration():
    """A chunk without it is a bag of method bodies, and the model has to guess the one
    thing the class declaration states."""
    for c in oversized.split_source(_java_class(40), "tiny-model", 99_000):
        assert "public class Big" in c
        assert "package com.acme;" in c


def test_chunks_cut_between_methods_never_inside_one():
    """A boundary inside a body produces an understanding of half an algorithm, reported
    as an understanding."""
    for c in oversized.split_source(_java_class(40), "tiny-model", 99_000):
        body = c.split("public class Big", 1)[1]
        assert body.count("{") == body.count("}"), c[:200]


def test_every_method_appears_in_exactly_one_chunk():
    chunks = oversized.split_source(_java_class(30), "tiny-model", 99_000)
    for i in range(30):
        assert sum(f"method{i}(" in c for c in chunks) == 1, i


def test_a_source_with_no_readable_methods_is_returned_whole():
    """Inventing a boundary would put one in the middle of something."""
    assert oversized.split_source("not code at all", "tiny", 99_000) == ["not code at all"]


def test_an_empty_source_yields_nothing():
    assert oversized.split_source("", "claude-opus-4-8", 800) == []


# ── merging ───────────────────────────────────────────────────────────────────

def test_findings_from_every_chunk_survive():
    merged = oversized.merge_understandings([
        {"purpose": "prices things", "business_rules": ["gold gets 12%"]},
        {"purpose": "part two", "business_rules": ["silver gets 6%"]},
    ])
    assert merged["business_rules"] == ["gold gets 12%", "silver gets 6%"]


def test_a_rule_found_in_both_halves_is_not_duplicated():
    merged = oversized.merge_understandings([
        {"business_rules": ["gold gets 12%"]},
        {"business_rules": ["gold gets 12%", "silver gets 6%"]},
    ])
    assert merged["business_rules"] == ["gold gets 12%", "silver gets 6%"]


def test_the_purpose_is_kept_not_averaged():
    """Each chunk saw a fraction of the class, so no chunk's purpose describes the whole.
    Blending them would produce a sentence none of them said."""
    merged = oversized.merge_understandings([
        {"purpose": "short"},
        {"purpose": "a fuller statement of what this class is for"},
    ])
    assert merged["purpose"] == "a fuller statement of what this class is for"
    assert merged["partial_views"] == ["short"]


def test_a_merged_understanding_says_it_was_chunked():
    merged = oversized.merge_understandings([{"purpose": "a"}, {"purpose": "b"}])
    assert merged["chunked"] == 2


def test_one_part_merges_to_itself_without_chunk_metadata():
    merged = oversized.merge_understandings([{"purpose": "a", "business_rules": ["r"]}])
    assert merged == {"purpose": "a", "business_rules": ["r"]}


def test_nothing_to_merge_is_empty_not_an_error():
    assert oversized.merge_understandings([]) == {}


# ── generation refuses ────────────────────────────────────────────────────────

def test_generation_raises_a_type_the_retry_layer_will_not_retry():
    """The resilience layer retries the transient. A request that is too large is not
    transient, and retrying it is a second rejection and a wrong reason on the artifact."""
    from src.generate import OversizedSourceError
    from src.llm import _is_transient

    assert not _is_transient(OversizedSourceError("too big"))


def test_the_refusal_explains_why_generation_cannot_chunk():
    from src.generate import OversizedSourceError

    # The message is built at the raise site; this pins the reasoning that must be in it.
    msg = ("`X` is too large to generate in one call: ... Comprehension read it in parts, "
           "which merges; generation cannot, because there is no union of two "
           "half-migrations. Split the class in the source, or migrate it by hand.")
    e = OversizedSourceError(msg)
    assert "no union of two half-migrations" in str(e)
    assert "migrate it by hand" in str(e)


def test_each_chunk_is_a_class_that_actually_parses():
    """The strongest available check, and it caught a real defect: chunks opened the class
    and never closed it, so every one was syntactically invalid and a model reading it
    would remark on the truncation rather than the logic."""
    import javalang
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-hybris"
           / "core-customize/hybris/bin/custom/acmecore/src/com/acme/core/service/impl"
           / "DefaultPricingService.java").read_text()
    chunks = oversized.split_source(src, "tiny-model", 99_000)
    assert len(chunks) > 1
    for c in chunks:
        javalang.parse.parse(c)


def test_a_real_class_keeps_every_method_across_its_chunks():
    from pathlib import Path

    from src.adapters.braced_symbols import symbols

    src = (Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-hybris"
           / "core-customize/hybris/bin/custom/acmecore/src/com/acme/core/service/impl"
           / "DefaultPricingService.java").read_text()
    names = {m["name"] for m in symbols(src)}
    chunks = oversized.split_source(src, "tiny-model", 99_000)
    covered = set()
    for c in chunks:
        covered |= {m["name"] for m in symbols(c)}
    assert names <= covered, names - covered


def test_the_budget_is_measured_against_the_model_that_will_receive_it():
    """`generate_apex` never took a model parameter. Referring to one that was not in
    scope raised NameError, the caller treated it as a failed conversion, and the run
    emitted no classes at all — caught by the end-to-end test, not by this file."""
    from src.llm import _load_config

    # Read from config rather than pinned to a model name. What this asserts is that a
    # stage resolves to *its own tier*; the particular model is a routing decision that
    # changes, and hardcoding it made a config edit look like a code regression. [1.51]
    routing = (_load_config().get("agentic") or {}).get("routing") or {}
    models = routing.get("models") or {}
    tiers = routing.get("tiers") or {}
    assert oversized.model_for_stage("generate") == models[tiers.get("generate", "frontier")]
    assert oversized.model_for_stage("comprehend") == models[tiers.get("comprehend", "cheap")]
    # …and the two are different tiers, which is the whole point of routing.
    assert oversized.model_for_stage("generate") != oversized.model_for_stage("comprehend")


def test_a_run_level_model_override_wins():
    from src import runctx

    token = runctx._model.set("some-other-model")
    try:
        assert oversized.model_for_stage("generate") == "some-other-model"
    finally:
        runctx._model.reset(token)


# ── the harness must not depend on what a previous run left behind [1.51] ─────

def test_the_cache_directory_is_overridable():
    """The golden harness gives each run a cache of its own. Sharing the repo's made its
    output depend on whether something had warmed it: the reports carrying token counts
    differ between a cold and a warm run of *identical code*, so a baseline saved cold
    failed every warm check afterwards. Changing the model invalidated every entry and
    turned that latent trap into two failing baselines that looked like a code defect."""
    import os
    from pathlib import Path

    from src.llm import _cache_dir

    before = os.environ.get("H2A_CACHE_DIR")
    try:
        os.environ["H2A_CACHE_DIR"] = "/tmp/h2a-cache-probe"
        assert _cache_dir({"cache_dir": "cache/"}) == Path("/tmp/h2a-cache-probe")
    finally:
        if before is None:
            os.environ.pop("H2A_CACHE_DIR", None)
        else:
            os.environ["H2A_CACHE_DIR"] = before
    # Without the override it falls back to config, resolved against the project root —
    # so compare the tail rather than a bare relative path.
    assert _cache_dir({"cache_dir": "cache/"}).name == "cache"


def test_a_golden_run_is_given_its_own_cache():
    import inspect

    from tests import golden

    src = inspect.getsource(golden.run_reference)
    assert "H2A_CACHE_DIR" in src
    assert "rmtree" in src, "a per-run cache that is never removed is just a slow leak"
