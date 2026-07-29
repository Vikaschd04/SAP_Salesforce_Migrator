"""
critic.py — the Critic / Reviewer agent (adversarial quality gate).

The linear pipeline only checks that code compiles. The Critic reviews what a
compiler can't: does the Apex actually preserve the original Java behavior, does
it follow fflib patterns, is it secure (FLS / sharing / stripInaccessible), and
is it bulk-safe? It returns structured findings; the orchestrator feeds any
ERROR-level findings back into one bounded repair round.

Deterministic floor: it always runs the objective validator (governor + schema)
so even under `mock`/offline it's a real gate. The LLM review runs only on a real
provider — with `mock` the Critic returns just the objective findings (usually
none, since the Builder already repaired them), so the run stays deterministic.
"""

from __future__ import annotations

from src.agentic.router import route_model
from src.validate import validate_all
from src.llm import call_structured, _load_config, _get_provider

CRITIC_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "revise"]},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["ERROR", "WARNING"]},
                    "category": {"type": "string"},
                    "message": {"type": "string"},
                    # A concrete, actionable fix for this finding — what to change and how.
                    "suggestion": {"type": "string"},
                },
                "required": ["severity", "category", "message", "suggestion"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdict", "findings"],
    "additionalProperties": False,
}


class CriticAgent:
    name = "Critic"

    def review(self, artifact, schema: dict, *, offline: bool = False, retriever=None) -> list:
        """Return findings [{severity, category, message}] for a generated artifact."""
        # Frontend artifacts are reviewed as LWC bundles, not Apex.
        if getattr(artifact, "layer", "") == "Component":
            return self._review_lwc(artifact, offline, retriever)

        findings = []

        # 1. Objective floor — governor + schema grounding on the final code.
        for code, fname in ((artifact.main_class, f"{artifact.target_name}.cls"),
                            (artifact.test_class, f"{artifact.target_name}Test.cls")):
            for i in validate_all(code, fname, schema):
                findings.append({"severity": i["severity"], "category": i["rule"],
                                 "message": i["message"]})

        # 2. LLM adversarial review (real provider only), grounded in retrieved docs.
        provider = _get_provider(_load_config())
        if provider != "mock" and not offline:
            findings += self._llm_review(artifact, schema, offline, retriever)

        artifact.critic_findings = findings
        return findings

    def _review_lwc(self, artifact, offline: bool, retriever=None) -> list:
        """Objective LWC checks (always) + adversarial LWC review (real provider only)."""
        from src.validate_lwc import validate_lwc
        findings = [{"severity": i["severity"], "category": i["rule"], "message": i["message"]}
                    for i in validate_lwc(artifact.lwc_bundle or {})]

        provider = _get_provider(_load_config())
        if provider != "mock" and not offline:
            findings += self._llm_review_lwc(artifact, offline, retriever)

        artifact.critic_findings = findings
        return findings

    def _llm_review_lwc(self, artifact, offline: bool, retriever=None) -> list:
        config = _load_config()
        src = "\n\n".join(f"// {c.get('class_name', '?')}\n{c.get('source', '')}"
                          for c in artifact.source_classes)
        b = artifact.lwc_bundle or {}
        grounding = ""
        if retriever is not None:
            grounding = retriever.grounding_block(
                "LWC template getter for:each if:true @api @wire CustomEvent accessibility review")
        prompt = (
            f"Adversarially review this generated LWC bundle `{artifact.target_name}` against the "
            "original Angular component. Report only real problems, most severe first:\n"
            "  1. BEHAVIOR — is every rule/computation from the Angular component preserved?\n"
            "  2. TEMPLATE — no expressions in { } (must be property/getter); for:each has key; "
            "if:true / lwc:if used correctly\n"
            "  3. API — @api for inputs, CustomEvent for outputs, @wire/imperative Apex for data\n"
            "  4. ACCESSIBILITY — labels/alt/roles preserved\n\n"
            f"== Original Angular ==\n{src}\n\n"
            f"== Generated LWC .js ==\n{b.get('js','')}\n\n"
            f"== Generated LWC .html ==\n{b.get('html','')}\n\n"
            + (grounding + "\n\n" if grounding else "")
            + "For every finding include a concrete `suggestion` — the specific change to make "
            "(e.g. 'move the `{a+b}` expression into a getter `get total()`'). Return verdict "
            "'revise' with ERROR findings for anything that breaks behavior or violates LWC "
            "template rules; otherwise 'pass'."
        )
        try:
            result = call_structured(
                f"critic_lwc_{artifact.target_name}", prompt, CRITIC_SCHEMA,
                config.get("max_tokens", {}).get("generate", 4000),
                offline=offline, effort=config.get("effort", {}).get("generate", "high"),
                model=route_model(config, f"critic_{artifact.target_name}"))
            return (result.get("parsed") or {}).get("findings", []) or []
        except Exception:
            return []

    def _llm_review(self, artifact, schema: dict, offline: bool, retriever=None) -> list:
        config = _load_config()
        from src.schema import schema_prompt_block
        sources = "\n\n".join(f"// {c.get('class_name', '?')}\n{c.get('source', '')}"
                              for c in artifact.source_classes)
        rules = "\n".join(f"- {r}" for r in (artifact.business_rules or [])) or "- (none captured)"
        grounding = ""
        if retriever is not None:
            grounding = retriever.grounding_block(
                f"{artifact.apex_pattern} security FLS sharing governor limits bulkification fflib review")
        prompt = (
            f"Adversarially review this generated Apex `{artifact.target_name}` "
            f"({artifact.apex_pattern} pattern). Report only real problems, most severe first:\n"
            "  1. BEHAVIOR — does it preserve what the original Java did? (the business rules below)\n"
            "  2. SECURITY — FLS via Security.stripInaccessible, correct 'with sharing'\n"
            "  3. FFLIB — Selector owns SOQL, Service stateless/bulkified, Controller thin\n"
            "  4. GOVERNOR — no SOQL/DML in loops, bulk-safe collections\n\n"
            f"== Business rules to preserve ==\n{rules}\n\n"
            f"== Original Java ==\n{sources}\n\n"
            f"== Generated Apex ==\n{artifact.main_class}\n\n"
            f"== SObject schema ==\n{schema_prompt_block(schema or {})}\n\n"
            + (grounding + "\n\n" if grounding else "")
            + "For every finding include a concrete `suggestion` — the specific change to make "
            "(e.g. 'wrap the SOQL in a bulk collection outside the for-loop', 'add "
            "Security.stripInaccessible on the query results'). Return verdict 'revise' with ERROR "
            "findings for anything that breaks behavior, security, or governor limits; otherwise 'pass'."
        )
        try:
            result = call_structured(
                f"critic_{artifact.target_name}", prompt, CRITIC_SCHEMA,
                config.get("max_tokens", {}).get("generate", 4000),
                offline=offline, effort=config.get("effort", {}).get("generate", "high"),
                model=route_model(config, f"critic_{artifact.target_name}"),
            )
            return (result.get("parsed") or {}).get("findings", []) or []
        except Exception:  # a failed review must never abort the run
            return []
