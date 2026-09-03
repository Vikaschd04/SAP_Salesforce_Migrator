"""Adobe Commerce hazards, framed against SAP Hybris. [2.10]

The Hybris radar asks what Salesforce will refuse to do. This asks the same question one
platform pair over, and the answers differ in kind: Salesforce fails at *limits*, Hybris
fails at *expressiveness*. PHP lets Magento do things a statically typed, single-
inheritance, Spring-wired platform has no construct for — and the dangerous ones all
convert into something that looks right.

Each test names the failure it is protecting against, because a hazard rule that fires
for a reason nobody wrote down is one nobody trusts.
"""

import textwrap
from pathlib import Path

from src.adapters.magento_radar import headline, scan

MAGENTO = str(Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-magento")


def _by_rule(root=MAGENTO):
    out = {}
    for f in scan(root)["findings"]:
        out.setdefault(f["rule"], []).append(f)
    return out


def test_the_fixture_trips_every_rule_it_was_built_to_trip():
    found = set(_by_rule())
    assert {"AROUND_PLUGIN", "QUERY_IN_LOOP", "RAW_SQL", "OBJECT_MANAGER",
            "OBSERVER_MUTATES_PAYLOAD", "EAV_DATA_PATCH", "MAGIC_DATA_ACCESS",
            "STORE_SCOPED_CONFIG", "CLUSTER_CRON", "LAYOUT_RUNTIME_MOVE"} <= found


def test_the_around_plugin_is_critical_when_it_provably_skips_proceed():
    """[G2] Hybris interceptors cannot decline to call through. This one does."""
    hit = _by_rule()["AROUND_PLUGIN"][0]
    assert hit["severity"] == "critical"
    assert "decorator bean" in hit["fix"], "name the one Hybris construct that can do it"


def test_an_unreadable_around_plugin_is_raised_but_not_as_certain(tmp_path):
    """Unknown is not the same as safe, and not the same as proven either."""
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "di.xml").write_text(
        '<config><type name="T"><plugin name="p" type="Gone\\Missing"/></type></config>',
        encoding="utf-8")
    hit = [f for f in scan(str(tmp_path))["findings"] if f["rule"] == "AROUND_PLUGIN"][0]
    assert hit["severity"] == "high"
    assert "could not be read" in hit["hazard"]


def test_a_passthrough_around_plugin_is_not_reported(tmp_path):
    """It always proceeds, so an interceptor expresses it. Raising it would be noise."""
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "di.xml").write_text(
        '<config><type name="T"><plugin name="p" type="A\\P"/></type></config>',
        encoding="utf-8")
    (tmp_path / "A").mkdir()
    (tmp_path / "A" / "P.php").write_text(
        "<?php class P { public function aroundX($s, callable $proceed) "
        "{ return $proceed(); } }", encoding="utf-8")
    assert not [f for f in scan(str(tmp_path))["findings"] if f["rule"] == "AROUND_PLUGIN"]


def test_the_n_plus_one_is_found_in_the_observer():
    hit = _by_rule()["QUERY_IN_LOOP"][0]
    assert hit["file"].endswith("TierCheckObserver.php")
    assert hit["severity"] == "critical"


def test_a_query_outside_a_loop_is_not_an_n_plus_one(tmp_path):
    (tmp_path / "Svc.php").write_text(
        "<?php class Svc { function f() { $this->conn->fetchAll($s); "
        "foreach ($rows as $r) { $total += $r['x']; } } }", encoding="utf-8")
    assert not [f for f in scan(str(tmp_path))["findings"] if f["rule"] == "QUERY_IN_LOOP"]


def test_the_observer_mutation_explains_the_async_difference():
    """[G3] Magento is synchronous and ordered; Hybris EventService is neither."""
    hit = _by_rule()["OBSERVER_MUTATES_PAYLOAD"][0]
    assert "asynchronously" in hit["hazard"] and "no ordering" in hit["hazard"]


def test_eav_names_the_attributes_and_the_ones_it_cannot_see():
    """[G1] Attributes added through the admin UI are in no file at all."""
    hit = _by_rule()["EAV_DATA_PATCH"][0]
    assert "acme_loyalty_tier" in hit["hazard"] and "acme_points_balance" in hit["hazard"]
    assert "exported from the live system" in hit["fix"]


def test_raw_sql_says_the_tables_will_not_exist():
    hit = _by_rule()["RAW_SQL"][0]
    assert "will not exist after" in hit["hazard"]


def test_object_manager_explains_why_it_breaks_the_dependency_graph():
    hit = _by_rule()["OBJECT_MANAGER"][0]
    assert "constructor" in hit["hazard"]


def test_php_imports_are_not_mistaken_for_traits(tmp_path):
    """`use Magento\\Framework\\...;` is an import. Flagging those would drown the report."""
    (tmp_path / "A.php").write_text(
        "<?php\nnamespace X;\nuse Magento\\Framework\\Event\\Observer;\n"
        "use Magento\\Store\\Model\\ScopeInterface;\nclass A {}\n", encoding="utf-8")
    assert not [f for f in scan(str(tmp_path))["findings"] if f["rule"] == "PHP_TRAIT"]


def test_an_actual_trait_use_is_flagged(tmp_path):
    (tmp_path / "A.php").write_text(
        "<?php\nclass A {\n    use LoggerAwareTrait;\n}\n", encoding="utf-8")
    hits = [f for f in scan(str(tmp_path))["findings"] if f["rule"] == "PHP_TRAIT"]
    assert len(hits) == 1
    assert "single inheritance" in hits[0]["hazard"]


def test_one_finding_per_rule_per_file():
    """Four getData calls in one class are one decision, not four hazards."""
    magic = [f for f in _by_rule()["MAGIC_DATA_ACCESS"]]
    assert len(magic) == len({f["file"] for f in magic})


def test_findings_are_ordered_most_severe_first():
    sev = [f["severity"] for f in scan(MAGENTO)["findings"]]
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    assert sev == sorted(sev, key=lambda s: rank[s])


def test_every_hazard_names_what_hybris_would_do_instead():
    """"This is hard" is not actionable; a migration is a sequence of decisions."""
    for f in scan(MAGENTO)["findings"]:
        assert f["fix"] and len(f["fix"]) > 40, f["rule"]


def test_a_clean_project_reports_nothing(tmp_path):
    (tmp_path / "Plain.php").write_text(
        "<?php\nnamespace X;\nclass Plain { public function add(int $a, int $b): int "
        "{ return $a + $b; } }\n", encoding="utf-8")
    r = scan(str(tmp_path))
    assert r["summary"]["total"] == 0
    assert "No Magento-specific" in headline(r["summary"])


def test_the_headline_counts_by_severity():
    assert "critical" in headline(scan(MAGENTO)["summary"])
