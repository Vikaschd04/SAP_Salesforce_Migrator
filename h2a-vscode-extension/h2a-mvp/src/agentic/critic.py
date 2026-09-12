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
from src.llm import call_structured, _load_config, _get_provider
from src.pipeline import validate_artifact

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


def _normalise_findings(raw: list) -> list:
    """Defend against a model that does not honour the declared schema.

    CRITIC_SCHEMA marks severity/category/message/suggestion as `required`, but that is a
    hint to the model, not an enforced contract — call_structured() parses whatever comes
    back, and a weaker or free-tier model can drop a required field even though the schema
    asked for it. Downstream code (apply_critic_repair, the triage/report renderers) reads
    these dicts with direct key access in places, so a finding missing `message` used to
    raise a raw KeyError instead of being reported as a finding with no explanation.

    Findings with no usable severity are dropped — there is nothing safe to do with a
    finding that cannot be classified as ERROR or WARNING, and guessing one risks either
    triggering a repair loop the model never actually asked for, or silently swallowing a
    real ERROR.
    """
    out = []
    for f in raw or []:
        if not isinstance(f, dict):
            continue
        severity = str(f.get("severity", "")).upper()
        if severity not in ("ERROR", "WARNING"):
            continue
        out.append({
            "severity": severity,
            "category": f.get("category") or "critic",
            "message": f.get("message") or "(the model flagged this without an explanation)",
            "suggestion": f.get("suggestion") or "",
        })
    return out


#: What the Critic says when there is no pipeline to ask — the review still has to run.
#: These are the shipped pipeline's words, which is what this prompt always said.
_FALLBACK_CRITERIA = (
    "  2. SECURITY — FLS via Security.stripInaccessible, correct 'with sharing'\n"
    "  3. FFLIB — Selector owns SOQL, Service stateless/bulkified, Controller thin\n"
    "  4. GOVERNOR — no SOQL/DML in loops, bulk-safe collections")


def _active():
    """The running pipeline, or None outside a run."""
    try:
        from src import pipeline
        return pipeline.active()
    except Exception:
        return None


def _target_extension() -> str:
    """The running target's source-file extension. `.cls` outside a run."""
    p = _active()
    return getattr(p.target, "code_extension", ".cls") if p is not None else ".cls"


def _platform_label() -> str:
    """The target platform's name, for the retrieved-grounding heading."""
    p = _active()
    return (getattr(p.target, "label", "") or "").split(" (")[0] if p is not None else ""


def _review_vocabulary() -> tuple:
    """`(source_language, target_language, criteria, retrieval_terms, schema_heading)`.

    One function because these five always have to agree: a prompt that asks about
    "generated Java" under a heading that says "SObject schema" is the contradiction that
    made the model write Apex into a Hybris migration in the first place. [1.56]
    """
    p = _active()
    if p is None:
        return ("Java", "Apex", _FALLBACK_CRITERIA,
                "security FLS sharing governor limits bulkification fflib review",
                "SObject schema")
    src = getattr(p.source, "code_language", "source")
    tgt = getattr(p.target, "code_language", "target")
    criteria = getattr(p.target, "review_criteria", "") or _FALLBACK_CRITERIA
    terms = (getattr(p.target, "review_terms", "")
             or getattr(p.target, "retrieval_terms", "") or "review")
    # The schema heading is the target's own name for its data model, and the Builder's
    # `prompt_sections` already carries exactly that string.
    heading = ((getattr(p.target, "prompt_sections", None) or {}).get("schema")
               or "Target data model")
    return src, tgt, criteria, terms, heading


class CriticAgent:
    name = "Critic"

    def review(self, artifact, schema: dict, *, offline: bool = False, retriever=None,
               context: dict | None = None) -> list:
        """Return findings [{severity, category, message}] for a generated artifact.

        `context` carries what this run is building, for validators that need it — see
        `Blackboard.validation_context`. Omitted, the objective floor reports types the
        migration itself is generating as unresolvable. [4.6]
        """
        # Frontend artifacts are reviewed as LWC bundles, not Apex.
        if getattr(artifact, "layer", "") == "Component":
            return self._review_lwc(artifact, offline, retriever)

        findings = []

        # 1. Objective floor — governor + schema grounding on the final code.
        # The target's own extension. `.cls` was hardcoded here for both pipelines, so a
        # Hybris run asked the Java checker about `PricingService.cls`. The checker
        # happens not to read the extension, which is luck rather than design — and the
        # filename is what every issue this produces is reported under. [4.6]
        ext = _target_extension()
        for code, fname in ((artifact.main_class, f"{artifact.target_name}{ext}"),
                            (artifact.test_class, f"{artifact.target_name}Test{ext}")):
            for i in validate_artifact(code, fname, schema, context or {}):
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
            return _normalise_findings((result.get("parsed") or {}).get("findings", []))
        except Exception:
            return []

    def _llm_review(self, artifact, schema: dict, offline: bool, retriever=None) -> list:
        config = _load_config()
        from src.schema import schema_prompt_block
        sources = "\n\n".join(f"// {c.get('class_name', '?')}\n{c.get('source', '')}"
                              for c in artifact.source_classes)
        rules = "\n".join(f"- {r}" for r in (artifact.business_rules or [])) or "- (none captured)"

        # Every platform word in this review comes from the running pipeline. It used to
        # come from here: the prompt said "review this generated Apex", listed fflib
        # layering, `Security.stripInaccessible` and governor limits, and ran unchanged on
        # the Adobe→Hybris pipeline — adversarially reviewing Java against the rules of a
        # platform it was not being built for, and feeding the findings into a real repair
        # round. The Builder was given the target's own vocabulary in 1.48 and 1.56; the
        # Critic, which reviews what the Builder writes, was not. [4.6]
        _src_lang, _tgt_lang, _criteria, _terms, _schema_label = _review_vocabulary()

        grounding = ""
        if retriever is not None:
            _label = _platform_label()
            grounding = retriever.grounding_block(
                f"{artifact.apex_pattern} {_terms}",
                **({"label": f"{_label} reference (retrieved — use these facts, "
                             "don't invent APIs)"} if _label else {}))
        prompt = (
            f"Adversarially review this generated {_tgt_lang} `{artifact.target_name}` "
            f"({artifact.apex_pattern} pattern). Report only real problems, most severe first:\n"
            f"  1. BEHAVIOR — does it preserve what the original {_src_lang} did? "
            "(the business rules below)\n"
            f"{_criteria}\n\n"
            f"== Business rules to preserve ==\n{rules}\n\n"
            f"== Original {_src_lang} ==\n{sources}\n\n"
            f"== Generated {_tgt_lang} ==\n{artifact.main_class}\n\n"
            f"== {_schema_label} ==\n{schema_prompt_block(schema or {})}\n\n"
            + (grounding + "\n\n" if grounding else "")
            + "For every finding include a concrete `suggestion` — the specific change to "
            "make, naming the construct to change and what to change it to. Return verdict "
            "'revise' with ERROR findings for anything that breaks behaviour, security, or "
            "the target platform's own limits; otherwise 'pass'."
        )
        try:
            result = call_structured(
                f"critic_{artifact.target_name}", prompt, CRITIC_SCHEMA,
                config.get("max_tokens", {}).get("generate", 4000),
                offline=offline, effort=config.get("effort", {}).get("generate", "high"),
                model=route_model(config, f"critic_{artifact.target_name}"),
            )
            return _normalise_findings((result.get("parsed") or {}).get("findings", []))
        except Exception:  # a failed review must never abort the run
            return []
