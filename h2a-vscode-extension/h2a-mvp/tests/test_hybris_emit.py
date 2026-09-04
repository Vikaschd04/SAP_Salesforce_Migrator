"""Assembling one extension from every part. [3.1–3.6]

The pieces were built and tested separately; this is where they have to agree. Assembly is
where a generator's mistakes stop being local — a service naming a DAO nobody emitted, a
bean pointing at a class in the wrong package, a job called one thing in Java and another
in ImpEx. None of those are visible while testing an emitter alone, and every one is fatal
to a build or, worse, survives the build and fails at run time.

Three real defects surfaced the first two times this ran. They are the tests below.
"""

from pathlib import Path

import pytest

from src import assurance

MAGENTO = str(Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-magento")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from src.adapters.php_reader import available
    if not available():
        pytest.skip("tree-sitter-php not installed")

    from src.adapters.adobe_source import ADAPTER
    from src.adapters.hybris_emit import emit_extension
    from src.adapters.hybris_plan import plan_targets

    m = ADAPTER.read(MAGENTO)
    out = tmp_path_factory.mktemp("ext")
    targets = plan_targets(m.units + m.tests + m.skipped, m.extra["di"])
    result = emit_extension(str(out), name="acmeloyalty", package="com.acme.loyalty",
                            source_model=m, targets=targets)
    root = out / "hybris" / "bin" / "custom" / "acmeloyalty"
    return result, root


def _read(root, rel):
    return (root / rel).read_text(encoding="utf-8")


# ── the whole thing holds together ────────────────────────────────────────────

def test_the_assembled_extension_compiles(built):
    """It reached `static` until 1.37 put a real compiler on the output. On a machine
    with no `javac` the rung stays `static`, which is a fact about the machine rather
    than the output — so both are accepted, and neither may be lower."""
    result, _ = built
    assert result["static"]["issues"] == []
    assert result["static"]["rung"] in (assurance.STATIC, assurance.TYPECHECKED)
    assert assurance.ORDER.index(result["static"]["rung"]) >= assurance.ORDER.index(
        assurance.STATIC)


def test_where_a_compiler_exists_the_extension_actually_compiles(built):
    """The claim the `typechecked` rung rests on. Skipped rather than weakened where no
    compiler is installed."""
    import shutil

    if not shutil.which("javac"):
        pytest.skip("no Java compiler on this machine")
    result, _ = built
    assert result["static"]["rung"] == assurance.TYPECHECKED
    assert result["static"].get("compiler") is True


def test_it_writes_the_files_a_hybris_extension_needs(built):
    _, root = built
    for rel in ("extensioninfo.xml", "build.xml", "project.properties",
                "resources/acmeloyalty-items.xml", "resources/acmeloyalty-spring.xml",
                "resources/acmeloyalty-seed.impex", "resources/acmeloyalty-jobs.impex"):
        assert (root / rel).exists(), rel


# ── defect 1: two names for one job ───────────────────────────────────────────

def test_a_job_has_one_name_in_java_and_in_impex(built):
    """The planner named `ExpirePointsJobPerformable` from the PHP class; the emitter
    named `AcmeLoyaltyExpirePointsJobPerformable` from the crontab entry. Two names for
    one thing, and the ImpEx then wired a springId nothing defined."""
    _, root = built
    java = root / "src/com/acme/loyalty/jobs/ExpirePointsJobPerformable.java"
    assert java.exists()
    assert "class ExpirePointsJobPerformable" in java.read_text()
    assert "expirePointsJobPerformable" in _read(root, "resources/acmeloyalty-jobs.impex")


# ── defect 2: an ImpEx springId nothing defines ───────────────────────────────

def test_every_springid_the_impex_names_has_a_bean(built):
    """This deploys cleanly and fails when the cronjob first runs — later and quieter
    than a build failure, which is exactly why it earns a rule."""
    import re

    _, root = built
    spring = _read(root, "resources/acmeloyalty-spring.xml")
    impex = _read(root, "resources/acmeloyalty-jobs.impex")
    beans = set(re.findall(r'<bean\s+id="([^"]+)"', spring))
    for spring_id in re.findall(r"^;[^;\n]*;([A-Za-z]\w*)\s*$", impex, re.M):
        assert spring_id in beans, spring_id


def test_the_cross_reference_check_catches_a_dangling_bean(tmp_path):
    from src.adapters.hybris_emit import cross_reference_issues

    (tmp_path / "resources").mkdir()
    (tmp_path / "resources" / "x-spring.xml").write_text(
        '<beans><bean id="a" class="com.acme.Nothing"/></beans>', encoding="utf-8")
    issues = cross_reference_issues(tmp_path)
    assert [i["rule"] for i in issues] == ["bean_class_missing"]


def test_the_cross_reference_check_catches_a_dangling_springid(tmp_path):
    from src.adapters.hybris_emit import cross_reference_issues

    (tmp_path / "resources").mkdir()
    (tmp_path / "resources" / "x-spring.xml").write_text("<beans/>", encoding="utf-8")
    (tmp_path / "resources" / "x.impex").write_text(
        "INSERT_UPDATE ServicelayerJob;code[unique=true];springId\n;AJob;aPerformable\n",
        encoding="utf-8")
    issues = cross_reference_issues(tmp_path)
    assert [i["rule"] for i in issues] == ["impex_bean_missing"]
    assert "fails the first time it runs" in issues[0]["fix"]


def test_a_cross_reference_failure_drops_the_rung(tmp_path):
    """Java parsing cleanly is not the whole claim."""
    from src.adapters.hybris_emit import cross_reference_issues

    assert cross_reference_issues(tmp_path) == []


# ── defect 3: the bean class was the bean id ──────────────────────────────────

def test_the_bean_names_the_class_not_the_bean_id(built):
    """Hybris convention is bean id `defaultPricingService`, class
    `DefaultPricingService`. Using the id as the class named a class nothing emits."""
    _, root = built
    spring = _read(root, "resources/acmeloyalty-spring.xml")
    assert 'class="com.acme.loyalty.service.impl.DefaultPricingService"' in spring
    assert 'id="defaultPricingService"' in spring


def test_a_job_is_not_also_emitted_as_a_service(built):
    """Adding JOB to the emittable set made the target loop render jobs as services too:
    two files for one unit, one of them meaningless."""
    _, root = built
    assert not (root / "src/com/acme/loyalty/service/ExpirePointsService.java").exists()


# ── the migrated configuration ────────────────────────────────────────────────

def test_the_discount_policy_survives_into_the_wiring(built):
    """`discountThreshold = 200` *is* the discount rule. A service whose logic survived
    and whose numbers did not is wrong in a way that reviews well."""
    _, root = built
    props = _read(root, "project.properties")
    spring = _read(root, "resources/acmeloyalty-spring.xml")
    assert "acmeloyalty.pricingservice.discountthreshold=200" in props
    assert 'value="${acmeloyalty.pricingservice.discountthreshold}"' in spring


# ── what was planned and deliberately not written ─────────────────────────────

def test_every_planned_kind_is_now_written(built):
    """These four were the `manual` list until 1.34 — decorator, interceptor,
    event-listener and data. The first three got emitters; `data` never needed one,
    because a Magento data patch *is* the data model and `build_items_xml` had been
    writing its EAV attributes onto the platform type all along. Reporting it as unwritten
    claimed a loss that had not happened, which is this ledger's failure mode pointed the
    other way."""
    result, _ = built
    assert {m["kind"] for m in result["manual"]} == set()


def test_anything_still_unwritten_would_carry_a_reason(built):
    """The mechanism has to survive being empty: a kind with no emitter must still be
    reported rather than silently dropped, which is what it is for."""
    result, _ = built
    for m in result["manual"]:
        assert "no emitter for" in m["reason"]


def test_written_kinds_are_not_reported_as_manual(built):
    """Listing a job as manual would understate what the run produced — the same kind of
    lie as overstating it, pointed the other way."""
    result, _ = built
    assert not any(m["kind"] in ("service", "dao", "job") for m in result["manual"])
