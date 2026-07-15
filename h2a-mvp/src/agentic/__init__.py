"""
Agentic core (Phase 1) for the Hybris → Apex migrator.

Replaces the fixed linear pipeline with a small team of agents coordinated over a
shared Blackboard:

    Orchestrator  — routes work to the right agent, loops until verified.
    Blackboard    — shared state (schema, plan, artifacts, decisions, questions).
    PlannerAgent  — decides the migration strategy (incl. native-vs-custom).
    BuilderAgent  — generates + validates + repairs one target.
    CriticAgent   — adversarial review gate before an artifact is accepted.
    VerifierAgent — deploy + self-heal against a real org (reuses deploy_and_heal).

Every agent degrades gracefully: with the `mock` provider (or `offline`) the
Planner and Critic fall back to deterministic behavior, so the whole thing runs
keyless and is fully testable. This module reuses the Phase-0 stage functions
(comprehend/generate/validate/repair/reconcile/verify) rather than reimplementing
them — the agentic layer is coordination + judgment, not new codegen.

Opt-in: the linear `repo-migrate` path is untouched. Use `agent-migrate` (or
`agentic.enabled: true`) to run this.
"""

from src.agentic.orchestrator import run_agentic_migration

__all__ = ["run_agentic_migration"]
