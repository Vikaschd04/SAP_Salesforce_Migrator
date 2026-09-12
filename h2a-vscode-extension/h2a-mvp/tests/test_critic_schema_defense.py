"""A weaker model can drop a field the JSON schema declared 'required'.

CRITIC_SCHEMA marks severity/category/message/suggestion as required, but that is a hint
sent to the model, not an enforced contract — call_structured() parses whatever comes
back. Found on a real run: `minimax/minimax-m3:free` returned a Critic finding missing
`message`, and `apply_critic_repair()` did `f["message"]` unguarded, crashing with a raw
`KeyError: 'message'` instead of being reported as a finding with no explanation.

The repair loop then correctly caught the exception and flagged the target for manual
review rather than corrupting output — but the crash itself was a real gap: a smaller or
free-tier model producing schema-non-compliant output is not a hypothetical edge case,
it is the exact scenario anyone evaluating a cheaper model will hit.
"""
import pytest

from src.agentic.critic import CriticAgent, _normalise_findings
from src.agentic.builders import BuilderAgent


# ── the normaliser ──────────────────────────────────────────────────────────

def test_a_finding_missing_message_gets_a_fallback_not_dropped():
    """Missing text is not the same as no finding — the model still flagged something."""
    out = _normalise_findings([{"severity": "ERROR", "category": "security"}])
    assert len(out) == 1
    assert out[0]["message"]                      # non-empty fallback, not KeyError
    assert out[0]["severity"] == "ERROR"


def test_a_finding_with_no_classifiable_severity_is_dropped():
    """Nothing safe to do with a finding that cannot be sorted into ERROR or WARNING —
    guessing risks either firing an unwanted repair or swallowing a real ERROR."""
    assert _normalise_findings([{"category": "x", "message": "m"}]) == []
    assert _normalise_findings([{"severity": "info", "message": "m"}]) == []


def test_severity_is_case_normalised():
    out = _normalise_findings([{"severity": "error", "message": "m"}])
    assert out[0]["severity"] == "ERROR"


def test_non_dict_entries_are_skipped_not_fatal():
    assert _normalise_findings(["not a dict", None, 42]) == []


def test_a_fully_formed_finding_passes_through_unchanged():
    f = {"severity": "WARNING", "category": "fflib", "message": "no bulk guard",
         "suggestion": "wrap the DML"}
    assert _normalise_findings([f]) == [f]


def test_empty_and_none_input():
    assert _normalise_findings([]) == []
    assert _normalise_findings(None) == []


# ── the two call sites that consume raw model output ─────────────────────────

class _Artifact:
    target_name = "PricingService"
    apex_pattern = "Service"
    layer = "Service"
    main_class = "public class PricingService {}"
    test_class = "@isTest public class PricingServiceTest {}"
    business_rules = []
    source_classes = [{"class_name": "DefaultPricingService", "source": "class X {}"}]
    lwc_bundle = {}


def test_llm_review_survives_a_finding_missing_message(monkeypatch):
    """The exact shape seen on the real run: severity present, message absent."""
    import src.agentic.critic as critic_mod

    def fake_call_structured(*a, **k):
        return {"parsed": {"verdict": "revise",
                           "findings": [{"severity": "ERROR", "category": "security"}]}}

    monkeypatch.setattr(critic_mod, "call_structured", fake_call_structured)
    monkeypatch.setattr(critic_mod, "_get_provider", lambda cfg: "unorouter")

    agent = CriticAgent()
    findings = agent._llm_review(_Artifact(), schema={}, offline=False)
    assert len(findings) == 1
    assert findings[0]["message"]                 # never empty, never absent


def test_apply_critic_repair_does_not_crash_on_a_normalised_finding(monkeypatch):
    """End to end: a malformed model finding must reach the repair step without a
    raw KeyError bubbling up and aborting the build."""
    import src.agentic.builders as builders_mod

    monkeypatch.setattr(builders_mod, "repair",
                        lambda code, issues, **k: code + " // repaired")

    builder = BuilderAgent()
    art = _Artifact()
    art.main_class = "public class PricingService {}"
    # Simulate what _normalise_findings produces from a finding that arrived with no
    # message — this must not KeyError regardless of where it came from.
    findings = [{"severity": "ERROR", "category": "security", "message": "", "suggestion": ""}]
    changed = builder.apply_critic_repair(art, findings, schema={}, sigs={}, offline=False,
                                          max_repair=1)
    assert changed is True
    assert "repaired" in art.main_class


def test_apply_critic_repair_defends_even_an_unnormalised_finding(monkeypatch):
    """Belt and braces: even a raw finding with `message` missing entirely (not just
    empty) must not crash the actual line that failed on the real run."""
    import src.agentic.builders as builders_mod

    monkeypatch.setattr(builders_mod, "repair",
                        lambda code, issues, **k: code + " // repaired")

    builder = BuilderAgent()
    art = _Artifact()
    art.main_class = "public class PricingService {}"
    raw_finding = [{"severity": "ERROR", "category": "security"}]   # no "message" key at all
    changed = builder.apply_critic_repair(art, raw_finding, schema={}, sigs={}, offline=False,
                                          max_repair=1)
    assert changed is True
