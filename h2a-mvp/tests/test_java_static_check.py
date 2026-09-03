"""The `static` rung, made real. [3.10]

There is no free SAP compiler, so this is the strongest check available without a licensed
platform: does the generated Java parse, and does every type it names resolve to something
that will exist?

The care is all in the second question, because a Hybris extension names three kinds of
type and only one is in the output. Treating a platform-generated model as missing would
bury every real problem under a hundred false ones; treating any `*Model` as present would
miss the case that actually happens — a DAO written for an itemtype nobody declared.
"""

import textwrap

import pytest

from src import assurance
from src.adapters.java_static_check import check, check_tree, generated_model_types

GOOD = textwrap.dedent("""\
    package com.acme.loyalty.service.impl;

    import com.acme.loyalty.service.PricingService;

    public class DefaultPricingService implements PricingService
    {
        @Override
        public Double applySpendDiscount(Double subtotal)
        {
            throw new UnsupportedOperationException("Not migrated yet");
        }
    }
    """)


def test_a_parsing_file_with_resolvable_types_is_clean():
    assert check(GOOD, "F.java", emitted={"PricingService"}) == []


def test_a_file_that_does_not_parse_is_reported_and_not_checked_further():
    issues = check("package x; public class Broken { void f( { } }", "Broken.java")
    assert len(issues) == 1
    assert issues[0]["rule"] == "java_syntax"
    assert "does not parse" in issues[0]["message"]


def test_a_type_nothing_emits_is_unresolved():
    """The defect this found in our own DAO: `implements <Item>Dao`, never emitted."""
    code = "package x; public class D implements AcmeLoyaltyAccountDao { }"
    issues = check(code, "D.java", emitted={"D"})
    assert [i["rule"] for i in issues] == ["unresolved_type"]
    assert "AcmeLoyaltyAccountDao" in issues[0]["message"]


def test_a_platform_generated_model_resolves_when_its_itemtype_is_declared():
    """`AcmeLoyaltyAccountModel` is absent from the output and not missing — the platform
    build writes it from items.xml."""
    items = '<items><itemtypes><itemtype code="AcmeLoyaltyAccount"/></itemtypes></items>'
    code = ("package x; public class D { public AcmeLoyaltyAccountModel find() "
            "{ return null; } }")
    assert check(code, "D.java", emitted={"D"}, items_xml=items) == []


def test_the_same_model_is_unresolved_when_nobody_declared_the_itemtype():
    """A DAO written for an itemtype that does not exist. Assuming any `*Model` resolves
    would miss exactly this."""
    code = ("package x; public class D { public GhostModel find() { return null; } }")
    issues = check(code, "D.java", emitted={"D"}, items_xml="<items/>")
    assert issues and "GhostModel" in issues[0]["message"]


def test_itemtypes_become_model_names():
    items = ('<items><itemtypes><itemtype code="Order"/>'
             '<itemtype code="AcmeLoyaltyAccount"/></itemtypes></items>')
    assert generated_model_types(items) == {"OrderModel", "AcmeLoyaltyAccountModel"}


def test_platform_api_resolves_without_being_emitted():
    code = ("package x; import de.hybris.platform.servicelayer.search.FlexibleSearchQuery;"
            " public class D { FlexibleSearchQuery q; ModelService ms; }")
    assert check(code, "D.java", emitted={"D"}) == []


def test_jdk_types_resolve():
    code = "package x; public class D { java.util.List<String> f(Integer i) { return null; } }"
    assert check(code, "D.java", emitted={"D"}) == []


def test_an_imported_type_resolves_by_its_import():
    code = "package x; import com.other.Thing; public class D { Thing t; }"
    assert check(code, "D.java", emitted={"D"}) == []


# ── the rung ──────────────────────────────────────────────────────────────────

def test_a_clean_tree_reaches_the_static_rung(tmp_path):
    (tmp_path / "res").mkdir()
    (tmp_path / "res" / "acme-items.xml").write_text(
        '<items><itemtypes><itemtype code="Acme"/></itemtypes></items>', encoding="utf-8")
    (tmp_path / "PricingService.java").write_text(
        "package p; public interface PricingService { Double f(Double d); }",
        encoding="utf-8")
    (tmp_path / "DefaultPricingService.java").write_text(GOOD, encoding="utf-8")

    got = check_tree(str(tmp_path))
    assert got["files"] == 2 and got["issues"] == []
    assert got["rung"] == assurance.STATIC


def test_a_partial_pass_is_not_a_rung(tmp_path):
    """One clean file and one broken one is not "statically checked". A rung describes
    the whole output or it describes nothing."""
    (tmp_path / "Ok.java").write_text("package p; public class Ok { }", encoding="utf-8")
    (tmp_path / "Bad.java").write_text("package p; class Bad { void f( { } }",
                                       encoding="utf-8")
    got = check_tree(str(tmp_path))
    assert got["issues"] and got["rung"] == assurance.NONE


def test_an_empty_tree_does_not_claim_the_rung(tmp_path):
    """Nothing to check is not the same as everything checked."""
    assert check_tree(str(tmp_path))["rung"] == assurance.NONE


# ── through the adapter ───────────────────────────────────────────────────────

def test_the_target_validates_through_the_checker():
    from src.adapters.hybris_target import ADAPTER

    assert ADAPTER.validate(GOOD, "F.java", {}, {"emitted_types": {"PricingService"}}) == []
    bad = ADAPTER.validate("package x; class B { void f( { } }", "B.java", {}, {})
    assert bad and bad[0]["rule"] == "java_syntax"


def test_verify_reports_the_static_rung_when_it_has_a_tree(tmp_path):
    from src.adapters.hybris_target import ADAPTER

    (tmp_path / "Ok.java").write_text("package p; public class Ok { }", encoding="utf-8")

    class _Req:
        output_dir = str(tmp_path)

    r = ADAPTER.verify(_Req(), {}, log=lambda *a, **k: None)
    assert r["ran"] is True and r["success"] is True
    assert r["rung"] == assurance.STATIC
    assert "No compiler ran" in r["message"]


def test_verify_still_reports_none_with_nothing_to_read():
    from src.adapters.hybris_target import ADAPTER

    r = ADAPTER.verify(None, {}, log=lambda *a, **k: None)
    assert r["rung"] == assurance.NONE and r["ran"] is False


def test_an_inline_qualified_reference_is_taken_at_its_word():
    """Whether `com.other.Thing` exists is a question only a real classpath answers.
    Flagging it would make this rung claim to be one."""
    code = "package x; public class D { com.other.Thing t; }"
    assert check(code, "D.java", emitted={"D"}) == []


def test_an_unqualified_unknown_is_still_flagged():
    """The distinction: a bare name had to come from somewhere in this extension."""
    code = "package x; public class D { Thing t; }"
    assert check(code, "D.java", emitted={"D"})
