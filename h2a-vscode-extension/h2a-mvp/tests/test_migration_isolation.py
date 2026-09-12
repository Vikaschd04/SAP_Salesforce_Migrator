"""The two migrations must not be able to reach into each other. [4.6]

Every defect this file guards against was live, in the shipped tree, under 1311 passing
tests and two golden baselines. They shared one cause: **the identity of the running
migration did not survive the thread boundary**, and every consumer treated its absence as
"the shipped pair" rather than as an error.

`runctx.propagate` copied the provider, the model and the credential into pool workers and
silently omitted the pipeline id — so inside `_map_parallel`, which is where all
comprehension and generation happens at the default concurrency of 8, an Adobe→Hybris run
had no identity. Fifteen call sites then read `get(pid) if pid else default_pipeline()`
and answered *Salesforce*:

    packs.prompt("generate")     "Translate the following SAP Hybris class into
                                  Salesforce Apex." — in a PHP→Java migration
    packs.mappings()             Salesforce type mappings (`Text(255)`)
    pipeline.current_target()    None → the Apex validator over generated Java, raising
                                  `java_syntax_leak: Java 'package' statement found` on a
                                  correct package declaration, escalating it to a
                                  frontier-model repair round, and leaving every artifact
                                  `needs_review` for a reason that did not exist
    llm._mock_language()         "Apex" → the mock wrote Apex into `.java` artifacts, and
                                  the Adobe golden baseline recorded it as correct

The tests below are written against the *seam*, not against the symptoms. A future
regression in any one of those consumers fails here, and so does a new per-run variable
that someone forgets to propagate.
"""

import re
from concurrent.futures import ThreadPoolExecutor

import pytest

from src import packs, pipeline, runctx
from src.agentic.orchestrator import _map_parallel

BOTH = ["hybris->salesforce", "adobe->hybris"]


# ── the thread boundary ───────────────────────────────────────────────────────

@pytest.mark.parametrize("pid", BOTH)
def test_a_worker_thread_knows_which_migration_it_is_running(pid):
    """The regression that made every other one possible.

    `_map_parallel` is the real build path: `workers > 1` and `len(items) > 1` is the
    default for any run with more than one target.
    """
    runctx.set_overrides(pipeline_id=pid)

    def probe(_):
        return runctx.pipeline_id()

    assert _map_parallel(probe, [1, 2, 3, 4], 4) == [pid] * 4


def test_propagate_carries_every_per_run_variable():
    """A ratchet against the exact shape of the original defect.

    `propagate` used to name three of the five ContextVars by hand. Anything added to
    `runctx` after that was invisible to every parallel LLM call — which is how a per-run
    *spend cap* came to be unenforced on the calls that spend nearly all of the money.
    """
    runctx.set_overrides(provider="mock", model="m", api_key="k", cost_cap=7.5,
                         pipeline_id="adobe->hybris")
    expected = [v.get() for v in runctx._VARS]
    assert all(e is not None for e in expected), "set_overrides did not set every var"

    def probe(_):
        return [v.get() for v in runctx._VARS]

    with ThreadPoolExecutor(max_workers=2) as pool:
        got = list(pool.map(runctx.propagate(probe), [1, 2]))
    assert got == [expected, expected]


# ── what a worker resolves ────────────────────────────────────────────────────

@pytest.mark.parametrize("pid,wanted_pack,first_word", [
    ("hybris->salesforce", "hybris_to_salesforce", "Translate"),
    ("adobe->hybris", "adobe_to_hybris", "Migrate"),
])
def test_prompts_and_mappings_resolve_per_pipeline_inside_a_worker(pid, wanted_pack,
                                                                   first_word):
    runctx.set_overrides(pipeline_id=pid)

    def probe(_):
        return (packs.pack_name(), packs.prompt("generate").split()[0],
                packs.prompt("comprehend").splitlines()[0],
                packs.prompt("generate_system").splitlines()[0])

    pack, word, comprehend, system = _map_parallel(probe, [1, 2], 2)[0]
    assert pack == wanted_pack
    assert word == first_word
    # No prompt for one pipeline may name the other pipeline's target platform.
    forbidden = "Salesforce" if pid == "adobe->hybris" else "Adobe Commerce"
    assert forbidden not in comprehend
    assert forbidden not in system


@pytest.mark.parametrize("pid,platform", [("hybris->salesforce", "salesforce"),
                                          ("adobe->hybris", "hybris")])
def test_the_objective_validator_routes_to_the_right_platform_inside_a_worker(pid,
                                                                              platform):
    runctx.set_overrides(pipeline_id=pid)

    def probe(_):
        t = pipeline.current_target()
        return getattr(t, "platform", None)

    assert _map_parallel(probe, [1, 2], 2) == [platform, platform]


JAVA = """package com.acme.core.service;

public class PricingService
{
    public double total(final double amount)
    {
        return amount;
    }
}
"""


def test_generated_java_is_not_judged_by_the_apex_validator():
    """The concrete cost of the leak, pinned as a test.

    Under the defect this produced `ERROR java_syntax_leak: Java 'package' statement
    found` and a `missing_with_sharing` warning — against a correct Hybris class, from
    inside the worker that had just generated it.
    """
    runctx.set_overrides(pipeline_id="adobe->hybris")

    def probe(_):
        return pipeline.validate_artifact(JAVA, "PricingService.java", {}, {})

    for issues in _map_parallel(probe, [1, 2], 2):
        rules = {i["rule"] for i in issues}
        assert "java_syntax_leak" not in rules
        assert "missing_with_sharing" not in rules


def test_a_class_this_migration_emits_is_not_reported_as_an_unresolved_type():
    """The Hybris checker reads `planned_targets`; for three items nobody passed it.

    Every generated test class named the class under test, which this run emits, and the
    checker — validating one file in isolation — called it missing. The Critic escalated
    that to an ERROR, which drove a repair round against a type that was never absent.
    """
    runctx.set_overrides(pipeline_id="adobe->hybris")
    test_class = """package com.acme.core.service;

public class PricingServiceTest
{
    public void testTotal()
    {
        final PricingService service = new DefaultPricingService();
    }
}
"""
    bare = pipeline.validate_artifact(test_class, "PricingServiceTest.java", {}, {})
    assert any(i["rule"] == "unresolved_type" for i in bare), (
        "precondition: with no context the sibling class is unresolvable")

    ctx = {"planned_targets": ["PricingService"]}
    with_ctx = pipeline.validate_artifact(test_class, "PricingServiceTest.java", {}, ctx)
    assert not [i for i in with_ctx if i["rule"] == "unresolved_type"]


# ── the Critic reviews for the platform it is building for ────────────────────

@pytest.mark.parametrize("pid,target_lang,source_lang", [
    ("hybris->salesforce", "Apex", "Java"),
    ("adobe->hybris", "Java", "PHP"),
])
def test_the_critic_reviews_in_the_target_platforms_vocabulary(pid, target_lang,
                                                               source_lang):
    from src.agentic import critic

    runctx.set_overrides(pipeline_id=pid)
    src, tgt, criteria, terms, heading = critic._review_vocabulary()
    assert (src, tgt) == (source_lang, target_lang)

    if pid == "adobe->hybris":
        # The review prompt used to *require* fflib layering, `Security.stripInaccessible`
        # and governor limits of generated Java. Naming a Salesforce construct in order to
        # forbid it ("touches no SOQL, no `with sharing`") is the opposite problem and is
        # deliberate — so this checks for the Salesforce APIs and frameworks that only
        # make sense as a requirement.
        for word in ("fflib", "stripInaccessible", "bulkified", "governor limit",
                     "SObject", "Selector owns"):
            assert word.lower() not in criteria.lower(), (
                f"Salesforce requirement {word!r} in the SAP Hybris review criteria")
            assert word.lower() not in heading.lower()
        assert "FlexibleSearch" in criteria, "the Hybris review says nothing Hybris-specific"
        assert critic._target_extension() == ".java"
        assert critic._platform_label() == "SAP Hybris"
    else:
        # The shipped review is unchanged: same four headings, same words.
        assert "FFLIB" in criteria and "stripInaccessible" in criteria
        assert "GOVERNOR" in criteria
        assert critic._target_extension() == ".cls"
        assert critic._platform_label() == "Salesforce"


# ── unknown and unsupported ───────────────────────────────────────────────────

def test_an_unknown_pipeline_is_refused_rather_than_defaulted():
    pipeline.ensure_registered()
    with pytest.raises(KeyError) as e:
        pipeline.get("magento->salesforce")
    assert "unknown pipeline" in str(e.value)
    # The refusal names what *is* available, so the answer is actionable.
    assert "hybris->salesforce" in str(e.value)


def test_a_pipeline_with_no_knowledge_pack_is_refused_rather_than_given_the_shipped_one():
    """The worst failure this system can have, made impossible rather than unlikely.

    Registering a third pair and forgetting its pack used to hand it the Salesforce
    prompts — fluent, confident output for entirely the wrong platform.
    """
    runctx.set_overrides(pipeline_id="sap->netsuite")
    with pytest.raises(KeyError) as e:
        packs.pack_name()
    assert "no knowledge pack" in str(e.value)


def test_active_raises_outside_a_run_and_active_or_shipped_is_the_only_fallback():
    runctx._pipeline_id.set(None)
    with pytest.raises(pipeline.NoActivePipeline):
        pipeline.active()
    assert pipeline.active_or_shipped().id == "hybris->salesforce"
    assert pipeline.current_target() is None


def test_no_module_reintroduces_the_silent_salesforce_fallback():
    """A ratchet, in the spirit of the assurance-purity test.

    `get(pid) if pid else default_pipeline()` is the idiom that turned a lost context into
    a Salesforce run, fifteen times over. `default_pipeline()` still has two legitimate
    callers in the orchestrator — both deciding the *engine route*, which genuinely is the
    shipped pair — and `pipeline.py` itself. Anywhere else it is the bug coming back.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "src"
    #: The three callers that legitimately name the shipped pair, and why:
    #:   pipeline.py         defines it, and `active_or_shipped` is built on it
    #:   orchestrator.py     decides the *engine route* — v1 genuinely is this pair
    #:   pipeline_driver.py  refuses to run as anything else, by comparing against it
    allowed = {"pipeline.py", "orchestrator.py", "pipeline_driver.py"}
    offenders = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        # The idiom itself is banned everywhere, allowlist included: there is no file in
        # which "no pipeline pinned, so use Salesforce" is the right answer.
        for idiom in ("else pipeline.default_pipeline()", "else _pl.default_pipeline()",
                      "or pipeline.default_pipeline()", "or _pl.default_pipeline()"):
            if idiom in text:
                offenders.append(f"{path.relative_to(root)} ({idiom})")
        if "default_pipeline()" in text and path.name not in allowed:
            offenders.append(str(path.relative_to(root)))
    assert not offenders, (
        "use pipeline.active() inside a run, or pipeline.active_or_shipped() on a surface "
        "that must render a label outside one: " + ", ".join(offenders))


# ── the user's choice decides the run ─────────────────────────────────────────

def test_an_explicit_selection_outranks_detection():
    """The cockpit and the CLI both pin a selection; the orchestrator ignored it.

    `run_agentic_migration` called `resolve(input_dir)` with no id, so the filesystem
    decided which migration ran and the person who chose one was never consulted. It
    converged on the right answer only because each source currently has exactly one
    target — which is a property of today's registry, not of the design.
    """
    from tests import golden

    pipeline.ensure_registered()
    # A Java/Hybris codebase, with Adobe→Hybris explicitly asked for.
    chosen = pipeline.resolve(str(golden.CORPUS), "adobe->hybris")
    assert chosen.id == "adobe->hybris", "detection overrode an explicit selection"

    # And with nothing asked for, detection still decides.
    assert pipeline.resolve(str(golden.CORPUS)).id == "hybris->salesforce"
    assert pipeline.resolve(str(golden.ADOBE_CORPUS)).id == "adobe->hybris"


def test_a_selection_that_does_not_match_the_upload_fails_in_that_platforms_words():
    """Honouring the choice means the refusal is the chosen platform's, not the other's.

    The failure has to name what the *selected* migration was looking for — "no
    registration.php or etc/module.xml" — rather than silently running the migration the
    codebase happens to look like.
    """
    from tests import golden

    pipeline.ensure_registered()
    chosen = pipeline.resolve(str(golden.CORPUS), "adobe->hybris")
    pre = chosen.source.preflight(str(golden.CORPUS))
    assert pre["verdict"] == "reject"
    assert "Adobe Commerce" in pre["summary"]
    assert "Hybris" not in pre["summary"], "refused in the wrong platform's vocabulary"


def test_the_orchestrator_reads_the_selection_before_it_detects():
    """Asserted against the source, because the alternative is a full run per case.

    What matters is the order: the selection is read from `runctx` and handed to
    `resolve`, rather than `resolve` being called on the directory alone.
    """
    import inspect

    from src.agentic import orchestrator

    src = inspect.getsource(orchestrator.run_agentic_migration)
    assert "_selected = _runctx.pipeline_id()" in src
    assert "resolve(input_dir, _selected)" in src
    assert "resolve(input_dir)\n" not in src, (
        "an id-less resolve remains — detection can still override the selection")


def test_every_run_pins_its_identity_on_both_engine_paths():
    """The change that makes an unset pipeline id mean "not in a run" rather than "v1".

    While v1 left it unset, "no id" was indistinguishable from "the context was lost",
    and fifteen consumers resolved both to Salesforce.
    """
    import inspect

    from src.agentic import orchestrator

    src = inspect.getsource(orchestrator.run_agentic_migration)
    assert "_runctx.set_overrides(pipeline_id=(_pl.id if _pl is not None" in src, (
        "the identity is no longer pinned for both engine paths")


# ── what the *model* is shown, not what the user is ──────────────────────────

def test_the_generate_prompt_a_worker_sends_speaks_the_right_platform():
    """`test_no_cross_platform_leak` reads events and reports. This reads the prompt.

    That gap is exactly where this defect lived for three items. The leak test runs an
    Adobe→Hybris migration through the same worker threads and passed the whole time,
    because the wrong words were never rendered to anybody — they were in the request. The
    model was told "Translate the following SAP Hybris class into Salesforce Apex", asked
    for `Complete Apex main class source.`, handed Salesforce type mappings, and grounded
    under a heading that read "Target SObject schema (write SOQL only against these
    objects/fields)". What came back was then judged by the Apex validator.

    Captured from inside `_map_parallel`, because on the main thread it was always right.
    """
    import src.generate as gen
    from src.generate import generate_apex

    seen: list = []
    original = gen.call_llm

    def capture(**kw):
        # Captured and short-circuited: the prompt is the subject of this test, and
        # calling through would need either a provider or a populated cache.
        seen.append((kw.get("system_prompt", ""), kw.get("prompt", ""),
                     kw.get("json_schema") or {}))
        return {"parsed": {"main_class": "", "test_class": "", "mapping_notes": "",
                           "sobject_refs": []},
                "content": "", "provider": "stub", "model": "stub"}

    runctx.set_overrides(pipeline_id="adobe->hybris")
    target = {"target_name": "PricingService", "layer": "Model",
              "source_classes": [{"class_name": "Pricing", "layer": "Model",
                                  "source": "<?php class Pricing {}", "file": "Pricing.php"}]}
    gen.call_llm = capture
    try:
        def probe(_):
            _t = pipeline.active().target
            return generate_apex(target, {}, [], offline=False, schema={}, mappings=None,
                                 prompt_sections=getattr(_t, "prompt_sections", None),
                                 schema_text=getattr(_t, "schema_text", None))
        _map_parallel(probe, [1, 2], 2)
    finally:
        gen.call_llm = original

    assert seen, "no generation request was captured"

    # Naming the other platform in order to *forbid* it is the opposite of this defect,
    # and both packs do it deliberately — the Adobe system prompt says "Pure Java. No PHP,
    # and no Salesforce Apex", and the Hybris `schema_text` says "Never Apex: no SOQL, no
    # `with sharing`, no `__c` suffixes". Those lines are the fix, not the bug. What must
    # not appear is a Salesforce term in an *instruction to produce one*.
    prohibits = re.compile(r"\b(no|not|never|avoid|without|rather than|instead of)\b", re.I)

    for system, user, schema in seen:
        blob = "\n".join([system, user, str(schema)])
        for word in ("Salesforce Apex", "SObject", "SOQL", "@isTest", "__c",
                     "governor limit", "fflib", "with sharing"):
            offending = [ln for ln in blob.splitlines()
                         if word.lower() in ln.lower() and not prohibits.search(ln)]
            assert not offending, (
                f"{word!r} was asked for on an Adobe→Hybris generation:\n  "
                + "\n  ".join(offending[:4]))

        # And the affirmative half: the request has to name what it *is* building.
        assert "SAP Hybris" in blob, "the prompt never names the platform it builds for"
        assert "Complete Java class source" in blob, (
            "the response schema still describes the other platform's artifact")
        assert "Migrate the following Adobe Commerce" in blob, (
            "the generate template came from the wrong pack")


# ── stages that belong to one pair only ──────────────────────────────────────

def test_pair_specific_stages_are_gated_on_the_pair():
    """ImpEx, cronjob translation and parity strengthening all belong to one migration.

    Each reads the shipped pair's source *and* writes the shipped pair's target: ImpEx
    reads SAP Hybris `.impex` and writes Salesforce CSV plus `force-app` patches; the
    cronjob stage reads Hybris job definitions and writes `schedule.apex`; parity
    strengthening asks for an `@isTest` class and writes it under
    `force-app/main/default/classes`. All three ran on every pipeline.

    The first two were inert on Magento by luck — it has no `.impex` and no Hybris
    cronjob XML. Parity strengthening was not inert: it is skipped under `mock`, so no
    test ever ran it, and on a real Adobe→Hybris run it spent frontier-tier calls
    rewriting JUnit as Apex and kept the result in memory, where the final validation and
    every report then described it. [4.6]
    """
    import inspect

    from src.agentic import orchestrator

    src = inspect.getsource(orchestrator.run_agentic_migration)
    assert "_is_shipped_pair = _pl is None or _pl.id == default_pipeline().id" in src
    for stage in ("translate_impex_dir", "translate_cronjobs_dir"):
        before = src.split(stage)[0]
        assert "_is_shipped_pair" in before.rsplit("# ──", 1)[-1], (
            f"{stage} is not gated on the pipeline it belongs to")
    assert "_wants_strengthen and _can_strengthen" in src


def test_only_a_target_that_can_strengthen_tests_says_so():
    pipeline.ensure_registered()
    assert pipeline.get("hybris->salesforce").target.strengthens_tests is True
    assert pipeline.get("adobe->hybris").target.strengthens_tests is False


def test_each_target_declares_where_it_writes():
    """Shared code asked `force-app/**/*.cls` regardless of target, so the checkpoint's
    "files are already on disk" warning could not fire for a SAP Commerce extension."""
    pipeline.ensure_registered()
    sf = pipeline.get("hybris->salesforce").target.output_globs
    hy = pipeline.get("adobe->hybris").target.output_globs
    assert sf and hy and set(sf).isdisjoint(hy)
    assert all(g.endswith(".cls") for g in sf)
    assert all(g.endswith(".java") for g in hy)


def test_the_linear_engine_refuses_a_pipeline_it_cannot_run():
    """`pipeline_driver` is v1: Hybris ingest, Apex generator, Salesforce writer, by name.

    The cockpit offered it as an engine choice beside "agentic" with no restriction, so an
    Adobe Commerce project could be sent to it. It did not fail — the Hybris ingest found
    0 classes in a tree full of PHP, and the run walked every stage, converted nothing and
    wrote a clean report over an empty output. Success-shaped failure, which is the one
    outcome this product exists to prevent. [4.6]
    """
    import tempfile

    from src.pipeline_driver import run_repo_migration

    runctx.set_overrides(pipeline_id="adobe->hybris")
    with pytest.raises(NotImplementedError) as e:
        run_repo_migration("/nonexistent", tempfile.mkdtemp())
    assert "linear engine runs" in str(e.value)
    assert "agentic" in str(e.value), "the refusal does not say what to do instead"


# ── isolation in both directions ─────────────────────────────────────────────

def test_each_platforms_builder_helpers_are_silent_on_the_other_pipeline():
    """The Builder's grounding helpers are per-source-platform and must stay that way.

    Three of them (`_derived_queries`, `_transaction_shapes`, `_rest_shapes`) read SAP
    Hybris source and gate on `source_platform == "hybris"`; `_data_model_notes` reads
    Magento's data model. The gates were defeated in exactly the case that mattered —
    inside a worker, where the lost pipeline id resolved to the shipped pair and every
    `!= "hybris"` check passed. They found nothing in PHP, so the damage was latent; the
    gate being defeated at all is the defect. [4.6]
    """
    from src.agentic import builders

    php = [{"source": "<?php class Pricing { public function total() { return 1; } }"}]
    java = [{"source": "public class P { public void t() { flexibleSearchService.search(q); } }"}]

    runctx.set_overrides(pipeline_id="adobe->hybris")
    for helper in (builders._derived_queries, builders._transaction_shapes,
                   builders._rest_shapes):
        assert helper(java) == "", (
            f"{helper.__name__} read Hybris Java on an Adobe→Hybris run")

    runctx._pipeline_id.set("hybris->salesforce")
    assert builders._data_model_notes(
        type("BB", (), {"modelling": [{"action": "reported", "field": "x"}]})()) == "", (
        "Magento data-model notes reached a Hybris→Salesforce run")


def test_a_worker_cannot_defeat_those_gates():
    """The gates read the pipeline; the pipeline has to survive the thread."""
    from src.agentic import builders

    java = [{"source": "public class P { public void t() { flexibleSearchService.search(q); } }"}]
    runctx.set_overrides(pipeline_id="adobe->hybris")

    def probe(_):
        return builders._derived_queries(java)

    assert _map_parallel(probe, [1, 2], 2) == ["", ""]


def test_every_cli_migrate_command_accepts_and_propagates_the_selection():
    """`agent-migrate` took `--pipeline`; `repo-migrate` did not accept it at all.

    The VS Code extension passes `--pipeline` for *both* engines, so choosing the linear
    engine failed with `unrecognized arguments: --pipeline adobe->hybris` and an argparse
    usage dump — the person who chose a migration was shown a list of subcommands. A
    selection an entry point cannot accept is a selection that cannot be honoured. [4.6]
    """
    from src.main import build_parser

    parser = build_parser()
    for command in ("agent-migrate", "repo-migrate"):
        args = parser.parse_args([command, "--input", "/in", "--output", "/out",
                                  "--pipeline", "adobe->hybris"])
        assert args.pipeline == "adobe->hybris", f"{command} dropped the selection"
