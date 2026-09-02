"""Rounding contracts, unscaled division, and money in a float. [1.17]

This is the failure class no other gate in the engine can see. Everything else asks
whether the migrated code is *shaped* right: it compiles, it deploys, the Critic approves
it, a reviewer signs it off. A discount that rounded HALF_UP at two places in Java and
lands on Apex's default instead passes every one of those checks and is wrong by a
fraction of a cent — on every order, forever. It is not found in review; it is found in a
reconciliation months later.

The rules therefore extract the contract from the source, where it is written down,
rather than trusting a model to reproduce it from memory.
"""

import textwrap

from src.radar import _divide_arity, _money_findings


def _find(src, rule=None):
    lines = src.splitlines()
    out = _money_findings(src, "Svc.java", "Svc", lines)
    return [f for f in out if rule is None or f["rule"] == rule]


# ── the rounding contract ─────────────────────────────────────────────────────

def test_repeated_sites_are_one_contract_not_five_hazards():
    """Five identical setScale calls are one decision. The count still matters."""
    src = textwrap.dedent("""\
        public class Svc {
            BigDecimal a() { return x.setScale(2, RoundingMode.HALF_UP); }
            BigDecimal b() { return y.setScale(2, RoundingMode.HALF_UP); }
            BigDecimal c() { return z.setScale(2, RoundingMode.HALF_UP); }
        }
        """)
    got = _find(src, "ROUNDING_CONTRACT")
    assert len(got) == 1
    assert "3 place(s)" in got[0]["hazard"]
    assert got[0]["line"] == 2, "cite the first site, not the last"
    assert "System.RoundingMode.HALF_UP" in got[0]["fix"], "the fix must be actionable Apex"


def test_two_different_contracts_are_two_findings():
    src = ("x.setScale(2, RoundingMode.HALF_UP);\n"
           "y.setScale(4, RoundingMode.HALF_EVEN);\n")
    got = _find(src, "ROUNDING_CONTRACT")
    assert len(got) == 2
    hazards = " ".join(g["hazard"] for g in got)
    assert "2 decimal place(s), HALF_UP" in hazards
    assert "4 decimal place(s), HALF_EVEN" in hazards


def test_the_legacy_rounding_constant_form_is_understood():
    """Older Hybris code says BigDecimal.ROUND_HALF_UP, not RoundingMode.HALF_UP."""
    assert _find("x.setScale(2, BigDecimal.ROUND_HALF_UP);", "ROUNDING_CONTRACT")


def test_a_scaled_divide_is_a_contract_too():
    got = _find("total.divide(qty, 2, RoundingMode.HALF_UP);", "ROUNDING_CONTRACT")
    assert len(got) == 1
    assert not _find("total.divide(qty, 2, RoundingMode.HALF_UP);", "UNSCALED_DIVIDE"), \
        "a divide that names its scale is the good case, not a hazard"


# ── unscaled division ─────────────────────────────────────────────────────────

def test_unscaled_divide_is_flagged():
    got = _find("BigDecimal r = total.divide(count);", "UNSCALED_DIVIDE")
    assert len(got) == 1 and got[0]["severity"] == "high"


def test_a_nested_call_in_the_divisor_is_still_one_argument():
    """`divide(BigDecimal.valueOf(qty))` has one argument. Counting commas would say two."""
    assert _divide_arity("x.divide(BigDecimal.valueOf(qty))", len("x.divide(") - 1) == 1
    assert _divide_arity("x.divide(a, 2, RoundingMode.HALF_UP)", len("x.divide(") - 1) == 3
    assert len(_find("x.divide(BigDecimal.valueOf(qty));", "UNSCALED_DIVIDE")) == 1


def test_other_arithmetic_is_not_division():
    for expr in ("x.multiply(y);", "x.add(y);", "x.subtract(y);", "divided = true;"):
        assert not _find(expr, "UNSCALED_DIVIDE"), expr


# ── money in a float ──────────────────────────────────────────────────────────

def test_float_money_is_flagged_by_name_and_type_together():
    assert _find("private double totalPrice;", "FLOAT_MONEY")
    assert _find("float discountRate = 0.1f;", "FLOAT_MONEY")


def test_a_float_that_is_not_money_is_left_alone():
    for decl in ("double ratio;", "float weight;", "double latitude;", "int totalPrice;"):
        assert not _find(decl, "FLOAT_MONEY"), decl


def test_float_money_explains_that_apex_will_disagree_with_the_recording():
    """The migrated code is *more* correct, so characterization will show a difference.

    Reading that difference as a migration defect wastes a day. The hazard says so.
    """
    got = _find("double subtotalAmount;", "FLOAT_MONEY")[0]
    assert "more correct" in got["hazard"]
    assert "legacy error, not a migration defect" in got["hazard"]


# ── the corpus ────────────────────────────────────────────────────────────────

def test_the_reference_corpus_contract_is_found_once():
    from pathlib import Path

    from src.radar import scan

    corpus = Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-hybris"
    found = [f for f in scan(str(corpus))["findings"] if f["rule"] == "ROUNDING_CONTRACT"]
    assert len(found) == 1, "DefaultPricingService states one contract, in five places"
    assert found[0]["source_class"] == "DefaultPricingService"
    assert "2 decimal place(s), HALF_UP" in found[0]["hazard"]
