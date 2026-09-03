"""The architecture holds two platforms — proven, not asserted.

A design that accepts a second pipeline *in principle* is not proven to accept one. So the
Adobe→Hybris pipeline is registered while still scaffolded: detection, resolution, pack
loading, the runnable guard and the purity rule are all exercised against two entries.

The scaffolds raise rather than returning empty values, and the guard refuses to start a
run with them. An adapter returning `[]` would let a migration walk every stage, convert
nothing, and report a clean ledger over an empty output — success-shaped failure, which is
the single outcome this product exists to prevent.
"""
import pytest

from src import packs, pipeline


@pytest.fixture(autouse=True)
def _registered():
    pipeline.ensure_registered()


# ── the registry holds both ──────────────────────────────────────────────────

def test_both_pipelines_are_registered():
    ids = {p.id for p in pipeline.available()}
    assert ids == {"hybris->salesforce", "adobe->hybris"}


def test_the_shipped_pipeline_is_still_the_default():
    """Adding a second pipeline must not change what an unqualified run means."""
    assert pipeline.default_pipeline().id == "hybris->salesforce"


def test_only_the_shipped_pipeline_is_runnable():
    assert pipeline.get("hybris->salesforce").implemented is True
    assert pipeline.get("adobe->hybris").implemented is False


def test_the_guard_refuses_a_scaffolded_pipeline():
    """Fails when a run is resolved — before a file is read or a token spent."""
    with pytest.raises(NotImplementedError, match="not implemented yet"):
        pipeline.require_runnable(pipeline.get("adobe->hybris"))


def test_the_guard_names_what_is_missing_and_where_to_look():
    """An error that says only 'not implemented' sends the reader hunting."""
    with pytest.raises(NotImplementedError) as e:
        pipeline.require_runnable(pipeline.get("adobe->hybris"))
    msg = str(e.value)
    # It names the half that is missing, and only that half. Once the source adapter
    # was built, saying "the adobe-commerce source is a scaffold" would have been false
    # — and a guard that misstates why it is blocking teaches people to ignore it.
    assert "hybris target" in msg
    assert "adobe-commerce source" not in msg
    assert "V2_DELIVERY_PLAN" in msg


def test_the_shipped_pipeline_passes_the_guard():
    assert pipeline.require_runnable(pipeline.get("hybris->salesforce")).shipped is True


# ── honesty about verification ───────────────────────────────────────────────

def test_the_hybris_target_declares_no_oracle():
    """Salesforce lends a free hosted compiler; SAP does not. Setting this True to make
    the reports look better would be exactly the overclaim the product refuses to make."""
    assert pipeline.get("adobe->hybris").verifiable is False
    assert pipeline.get("hybris->salesforce").verifiable is True


def test_hybris_verify_reports_the_absence_rather_than_a_clean_pass():
    from src.adapters.hybris_target import ADAPTER
    result = ADAPTER.verify("/tmp/anywhere", {})
    assert result["ran"] is False and result["success"] is False
    assert "statically checked, not verified" in result["message"]


# ── scaffolds fail loudly ────────────────────────────────────────────────────

# plan() is built [3.2b], so it is no longer in this list — the list is what is *still*
# a scaffold, and leaving a working method in it would make the guard describe the
# adapter wrongly in the direction that flatters the roadmap.
@pytest.mark.parametrize("call", [
    lambda a: a.emit("/tmp/x", [], None, {}),
    lambda a: a.validate("code", "F.java", {}, {}),
])
def test_hybris_target_methods_raise_with_their_delivery_item(call):
    from src.adapters.hybris_target import ADAPTER
    with pytest.raises(NotImplementedError) as e:
        call(ADAPTER)
    assert getattr(e.value, "item", ""), "the error should name the item that implements it"


def test_adobe_read_accounts_for_every_file_it_saw():
    """`read()` is built now [2.3-2.12]. What it must never do is *look* complete.

    The original scaffold raised rather than returning an empty model, because "0 classes,
    nothing unaccounted for" reads exactly like a clean migration of an empty codebase.
    The same danger survives implementation in a different form: a file that could not be
    parsed, silently dropped, produces a model that is wrong and confident. So the test
    is no longer "does it raise" but "does every file it saw end up somewhere".
    """
    from pathlib import Path

    from src.adapters.adobe_source import ADAPTER
    from src.adapters.php_reader import available, read_tree

    if not available():
        pytest.skip("tree-sitter-php not installed")

    corpus = str(Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-magento")
    model = ADAPTER.read(corpus)
    accounted = (len(model.units) + len(model.tests) + len(model.skipped)
                 + len(model.unreadable))
    assert accounted == len(read_tree(corpus)), "a file in no bucket is a file lost"
    assert model.platform == "adobe-commerce"


def test_adobe_read_refuses_rather_than_degrading_without_a_parser(monkeypatch):
    """No tree-sitter means no PHP. Returning what the XML alone yields would be a model
    with every business rule missing and nothing saying so."""
    from src.adapters import adobe_source, php_reader

    monkeypatch.setattr(php_reader, "available", lambda: False)
    with pytest.raises(NotImplementedError) as e:
        adobe_source.ADAPTER.read("/tmp/anywhere")
    assert "tree-sitter" in str(e.value)


def test_adobe_detect_returns_a_verdict_instead_of_raising():
    """detect() runs across every registered source to identify a codebase. One
    unimplemented platform must not break identification of the others."""
    report = pipeline.get("adobe->hybris").source.detect("/tmp/anywhere")
    assert report["verdict"] == "reject"
    assert report["confidence"] == 0


def test_detection_of_the_real_corpus_still_works_with_two_sources_registered():
    """The regression that matters: adding a scaffolded source must not disturb
    identification of a codebase the shipped pipeline handles."""
    platform, report = pipeline.detect("../Testing/acme-commerce-hybris")
    assert platform == "hybris"
    assert report.get("confidence", 0) > 0


def test_resolve_still_picks_the_shipped_pipeline_for_a_hybris_codebase():
    assert pipeline.resolve("../Testing/acme-commerce-hybris").id == "hybris->salesforce"


# ── packs ────────────────────────────────────────────────────────────────────

def test_both_packs_exist_on_disk():
    assert set(packs.available()) == {"hybris_to_salesforce", "adobe_to_hybris"}


def test_each_pipeline_resolves_to_its_own_pack():
    assert packs.pack_dir("hybris->salesforce").name == "hybris_to_salesforce"
    assert packs.pack_dir("adobe->hybris").name == "adobe_to_hybris"


def test_a_missing_adobe_prompt_does_not_fall_back_to_the_apex_one():
    """The worst available failure: generating Apex for a Hybris target because the
    prompt was missing and the shipped pack answered instead."""
    with pytest.raises(FileNotFoundError, match="adobe_to_hybris"):
        packs.prompt("generate", "adobe->hybris")


def test_the_source_model_carries_everything_phase_3_will_need():
    """The contract between the halves. Phase 3 reads exactly this and nothing else."""
    from pathlib import Path

    from src.adapters.adobe_source import ADAPTER
    from src.adapters.php_reader import available

    if not available():
        pytest.skip("tree-sitter-php not installed")

    m = ADAPTER.read(str(Path(__file__).resolve().parents[2] / "Testing"
                         / "acme-commerce-magento"))

    assert [u.name for u in m.units], "units"
    assert {t.code for t in m.data_model.types} >= {"acme_loyalty_account", "customer"}
    assert [j.name for j in m.jobs] == ["acme_loyalty_expire_points",
                                        "acme_loyalty_recalculate_tiers"]
    assert len(m.behaviours) == 7, "recorded behaviour from PHPUnit"
    assert any(h.rule == "AROUND_PLUGIN" for h in m.hazards)

    # Wiring the IR does not model yet, carried verbatim rather than dropped: it is how
    # the PHP is *reached*, and that is the first thing a migration loses.
    assert m.extra["di"]["preferences"], "di.xml preferences"
    assert m.extra["observers"], "events.xml observers"
    assert m.extra["unresolved_types"], "types a human must decide"


def test_an_eav_entity_still_says_its_attribute_set_is_open():
    """It has to survive assembly. A note that is dropped on the way into the model is
    the same as never having written it."""
    from pathlib import Path

    from src.adapters.adobe_source import ADAPTER
    from src.adapters.php_reader import available

    if not available():
        pytest.skip("tree-sitter-php not installed")

    m = ADAPTER.read(str(Path(__file__).resolve().parents[2] / "Testing"
                         / "acme-commerce-magento"))
    customer = next(t for t in m.data_model.types if t.code == "customer")
    assert "admin UI" in customer.undeclared_note


def test_hybris_plan_no_longer_raises_but_the_pipeline_still_cannot_run():
    """3.2b built plan(). The pipeline is still blocked, and for a different reason —
    emit() and validate() are Phase 3's remaining half. Those are different claims and
    the guard has to keep them apart."""
    from src.adapters.hybris_target import ADAPTER

    assert ADAPTER.plan([], {}) == []
    assert not pipeline.get("adobe->hybris").implemented
