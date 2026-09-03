"""Configuration, seed data and scheduled jobs on the way to Hybris. [3.5, 3.6]

A Magento codebase contains almost no data — the code declares structure and the database
holds everything else. What the code *does* hold is configuration, and it is not
incidental: `discountThreshold = 200` in di.xml **is** the discount policy. Lose it and the
migrated service is correct and wrong at once — the logic survives, the numbers it applies
do not, and that reviews well.
"""

from pathlib import Path

import pytest

from src import ir
from src.adapters.hybris_data import (LIVE_ONLY, _cron_to_quartz, build_bean_properties,
                                      build_cron_impex, build_job_performable,
                                      build_properties, build_seed_impex)

MAGENTO = str(Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-magento")


@pytest.fixture(scope="module")
def model():
    from src.adapters.php_reader import available
    if not available():
        pytest.skip("tree-sitter-php not installed")
    from src.adapters.adobe_source import ADAPTER
    return ADAPTER.read(MAGENTO)


# ── 3.5 · configuration ───────────────────────────────────────────────────────

def test_injected_constants_become_properties(model):
    props = build_properties(model.extra["di"]["arguments"], "acmeloyalty")
    assert "acmeloyalty.pricingservice.discountthreshold=200" in props
    assert "acmeloyalty.pricingservice.spenddiscountrate=0.10" in props


def test_each_property_records_where_it_came_from(model):
    props = build_properties(model.extra["di"]["arguments"], "acmeloyalty")
    assert "PricingService.discountThreshold — from" in props
    assert "di.xml" in props


def test_the_file_says_why_these_are_not_plumbing(model):
    props = build_properties(model.extra["di"]["arguments"], "acmeloyalty")
    assert "business policy" in props


def test_no_configuration_is_stated_rather_than_left_blank():
    assert "No configuration was injected" in build_properties([], "acmeloyalty")


def test_the_values_are_also_wired_onto_the_bean(model):
    """A property nothing reads is a property that did not migrate."""
    beans = build_bean_properties(model.extra["di"]["arguments"], "acmeloyalty")
    assert "defaultPricingService" in beans
    names = {n for n, _ in beans["defaultPricingService"]}
    assert names == {"discountThreshold", "spendDiscountRate"}


# ── 3.5 · seed data, and refusing to invent it ────────────────────────────────

def test_the_seed_impex_has_no_rows(model):
    """Every row would be invented. An ImpEx with plausible sample rows is the kind of
    file somebody loads into an environment assuming it came from somewhere."""
    impex = build_seed_impex("acmeloyalty", model.data_model.types)
    data_lines = [ln for ln in impex.splitlines()
                  if ln.strip() and not ln.lstrip().startswith("#")]
    assert data_lines == []


def test_it_names_what_must_come_out_of_the_live_system(model):
    impex = build_seed_impex("acmeloyalty", model.data_model.types)
    for name, _ in LIVE_ONLY:
        assert name in impex
    assert "admin UI" in impex, "the EAV residue argument has to survive to here too"


def test_the_headers_it_does_show_are_idempotent(model):
    impex = build_seed_impex("acmeloyalty", model.data_model.types)
    assert "INSERT_UPDATE AcmeLoyaltyAccount;" in impex
    assert "code[unique=true]" in impex


def test_an_eav_extension_gets_no_seed_header(model):
    """Those attributes hang off a platform type; seeding them is a customer export."""
    impex = build_seed_impex("acmeloyalty", model.data_model.types)
    assert "INSERT_UPDATE Customer;" not in impex


# ── 3.6 · cron ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("unix,quartz", [
    ("0 2 * * *", "0 0 2 * * ?"),
    ("30 3 * * 0", "0 30 3 ? * 1"),      # Unix Sunday is 0, Quartz Sunday is 1
    ("15 1 1 * *", "0 15 1 1 * ?"),
    ("*/5 * * * *", "0 */5 * * * ?"),
])
def test_unix_cron_becomes_quartz(unix, quartz):
    assert _cron_to_quartz(unix) == quartz


def test_the_day_of_week_shift_is_applied():
    """Sunday in Unix is 0 and in Quartz is 1. Off by one runs the job on Saturday, and
    nothing fails — it simply happens on the wrong day."""
    assert _cron_to_quartz("0 0 * * 0").endswith(" 1")


def test_an_unparseable_schedule_emits_no_trigger():
    """A guessed schedule is worse than an absent one: absent is noticed."""
    assert _cron_to_quartz("@daily") == ""
    job = ir.ScheduledJob(name="odd", cron="@daily", implemented_by="X::run")
    impex = build_cron_impex([job], "com.acme.loyalty", "acmeloyalty")
    assert "TRIGGER NOT EMITTED" in impex
    assert "Set the schedule by hand" in impex


def test_the_cron_impex_creates_job_cronjob_and_trigger(model):
    impex = build_cron_impex(model.jobs, "com.acme.loyalty", "acmeloyalty")
    assert "INSERT_UPDATE ServicelayerJob;code[unique=true];springId" in impex
    assert "INSERT_UPDATE CronJob;code[unique=true];job(code)" in impex
    assert "INSERT_UPDATE Trigger;cronJob(code)[unique=true];cronExpression" in impex


def test_node_affinity_is_named_as_a_decision_not_guessed(model):
    """A Magento job runs once per cluster; a Hybris job runs per node."""
    impex = build_cron_impex(model.jobs, "com.acme.loyalty", "acmeloyalty")
    assert "runs on every node unless a trigger names one" in impex
    assert "deployment decision" in impex


def test_the_job_class_extends_the_platform_base(model):
    java = build_job_performable(model.jobs[0], "com.acme.loyalty")
    assert "extends AbstractJobPerformable<CronJobModel>" in java
    assert "public PerformResult perform(final CronJobModel cronJob)" in java


def test_an_unmigrated_job_throws_rather_than_reporting_success(model):
    """Returning a SUCCESS PerformResult would make a job that does nothing look healthy
    in the Hybris admin console, every night, indefinitely."""
    java = build_job_performable(model.jobs[0], "com.acme.loyalty")
    assert "UnsupportedOperationException" in java
    assert "TODO migrate:" in java


def test_the_job_class_parses_and_resolves(model):
    from src.adapters.java_static_check import check

    java = build_job_performable(model.jobs[0], "com.acme.loyalty")
    assert check(java, "J.java", emitted={"AcmeLoyaltyExpirePointsJobPerformable"}) == []
