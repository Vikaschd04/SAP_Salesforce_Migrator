"""Magento's XML wiring, read into the IR. [2.4–2.7]

Magento keeps in XML what Hybris keeps in Spring and items.xml, and all of it decides how
the PHP is *reached* — which is the part a migration loses first, exactly as a Hybris
lifecycle hook loses its invocation.

The sharpest case, and most of what these tests are about, is the `around` plugin.
Magento lets it decline to call `$proceed`, so the original method never runs. Hybris
interceptors cannot express that, and a converter that maps `around` onto an interceptor
produces code that always calls through — a silent behaviour change in the construct most
likely to be carrying a deliberate business decision.
"""

import textwrap
from pathlib import Path

from src import ir
from src.adapters.magento_config import (classify_plugins, read_crontab, read_db_schema,
                                         read_di, read_events)

MAGENTO = str(Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-magento")


# ── 2.4 · di.xml ──────────────────────────────────────────────────────────────

def test_a_preference_is_recorded_as_a_global_substitution():
    prefs = read_di(MAGENTO)["preferences"]
    assert len(prefs) == 1
    assert prefs[0]["for"].endswith("PricingServiceInterface")
    assert prefs[0]["type"].endswith("Model\\PricingService")


def test_plugins_are_read_with_their_target_and_order():
    plugins = {p["name"]: p for p in read_di(MAGENTO)["plugins"]}
    assert set(plugins) == {"acme_loyalty_subtotal", "acme_loyalty_order_total"}
    assert plugins["acme_loyalty_order_total"]["on"].endswith("Sales\\Model\\Order")
    assert plugins["acme_loyalty_order_total"]["sort_order"] == 20


def test_constructor_arguments_are_captured():
    args = {a["name"]: a["value"] for a in read_di(MAGENTO)["arguments"]}
    assert args["discountThreshold"] == "200"
    assert args["spendDiscountRate"] == "0.10"


def test_an_around_plugin_that_can_skip_proceed_is_flagged():
    """G2. Hybris has no construct for this, so it must never be quietly converted."""
    plugins = {p["name"]: p for p in classify_plugins(MAGENTO, read_di(MAGENTO)["plugins"])}
    order = plugins["acme_loyalty_order_total"]
    assert order["around_methods"] == ["aroundGetGrandTotal"]
    assert order["can_skip_original"] is True


def test_a_plugin_with_no_around_method_is_not_flagged():
    """The flag has to be specific or it stops meaning anything."""
    plugins = {p["name"]: p for p in classify_plugins(MAGENTO, read_di(MAGENTO)["plugins"])}
    assert plugins["acme_loyalty_subtotal"]["can_skip_original"] is False


def test_an_around_plugin_that_always_proceeds_is_not_flagged(tmp_path):
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "di.xml").write_text(textwrap.dedent("""\
        <config><type name="Some\\Target">
          <plugin name="p" type="Acme\\Loyalty\\Plugin\\Passthrough"/>
        </type></config>
        """), encoding="utf-8")
    php = tmp_path / "Acme" / "Loyalty" / "Plugin"
    php.mkdir(parents=True)
    (php / "Passthrough.php").write_text(
        "<?php\nclass Passthrough {\n"
        "  public function aroundGet($s, callable $proceed) { return $proceed(); }\n}\n",
        encoding="utf-8")

    p = classify_plugins(str(tmp_path), read_di(str(tmp_path))["plugins"])[0]
    assert p["around_methods"] == ["aroundGet"]
    assert p["can_skip_original"] is False, "it always calls through; Hybris can express it"


def test_a_plugin_whose_class_is_missing_says_unknown_not_false(tmp_path):
    """Absent evidence is not evidence of absence — and False here would be a claim."""
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "di.xml").write_text(
        '<config><type name="T"><plugin name="p" type="Gone\\Missing"/></type></config>',
        encoding="utf-8")
    p = classify_plugins(str(tmp_path), read_di(str(tmp_path))["plugins"])[0]
    assert p["can_skip_original"] is None


# ── 2.5 · events.xml ──────────────────────────────────────────────────────────

def test_observers_are_read_with_their_event():
    obs = {o["name"]: o for o in read_events(MAGENTO)}
    assert obs["acme_loyalty_award_points"]["event"] == "sales_order_place_after"
    assert obs["acme_loyalty_award_points"]["instance"].endswith("AwardPointsObserver")


def test_observers_record_that_magento_dispatches_them_synchronously():
    """Hybris EventService is asynchronous by default; the difference travels with them."""
    assert all(o["synchronous"] for o in read_events(MAGENTO))


# ── 2.6 · crontab.xml ─────────────────────────────────────────────────────────

def test_cron_jobs_become_scheduled_jobs():
    jobs = {j.name: j for j in read_crontab(MAGENTO)}
    assert isinstance(next(iter(jobs.values())), ir.ScheduledJob)
    assert jobs["acme_loyalty_expire_points"].cron == "0 2 * * *"
    assert jobs["acme_loyalty_expire_points"].implemented_by.endswith("ExpirePoints::execute")


def test_the_cron_group_is_kept():
    """A Magento job runs once per cluster; a Hybris cronjob needs node affinity. [G9]"""
    assert all("#default" in j.file for j in read_crontab(MAGENTO))


# ── 2.7 · db_schema.xml ───────────────────────────────────────────────────────

def test_tables_become_data_types_with_mapped_column_types():
    types = {t.code: t for t in read_db_schema(MAGENTO)}
    acct = types["acme_loyalty_account"]
    by_name = {a["name"]: a for a in acct.attributes}
    assert by_name["lifetime_spend"]["type"] == "BigDecimal"
    assert by_name["points_balance"]["type"] == "Integer"
    assert by_name["enrolled_at"]["type"] == "DateTime"
    assert by_name["code"]["type"] == "String"


def test_nullable_false_becomes_required():
    acct = next(t for t in read_db_schema(MAGENTO) if t.code == "acme_loyalty_account")
    assert next(a for a in acct.attributes if a["name"] == "code")["required"] is True


def test_a_unique_constraint_reaches_the_column():
    acct = next(t for t in read_db_schema(MAGENTO) if t.code == "acme_loyalty_account")
    assert [a["name"] for a in acct.attributes if a["unique"]] == ["code"]


def test_every_table_says_it_is_only_the_declared_half():
    """EAV attributes are runtime rows. Presenting tables alone as the model is the lie."""
    for t in read_db_schema(MAGENTO):
        assert "EAV" in t.undeclared_note


# ── shared ────────────────────────────────────────────────────────────────────

def test_vendor_config_is_ignored(tmp_path):
    v = tmp_path / "vendor" / "magento" / "module-x" / "etc"
    v.mkdir(parents=True)
    (v / "events.xml").write_text(
        '<config><event name="x"><observer name="o" instance="I"/></event></config>',
        encoding="utf-8")
    assert read_events(str(tmp_path)) == []


def test_malformed_xml_does_not_break_the_read(tmp_path):
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "crontab.xml").write_text("<config><group", encoding="utf-8")
    assert read_crontab(str(tmp_path)) == []
