"""
blackboard.py — the shared workspace every agent reads from and writes to.

Instead of threading data through a fixed function-call order, the agents
collaborate through this single mutable object: the schema, the plan, the
artifacts produced so far, a running decisions log (for traceability), and any
open questions an agent couldn't resolve. This is what lets work be *revisited*
(Critic → back to Builder) rather than only pushed one way.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class PlanItem:
    """One decision from the Planner: what a source class/domain becomes."""
    target_name: str
    layer: str
    domain: str
    source_classes: list = field(default_factory=list)   # [{class_name, layer, source}]
    # Where it should land. Code kinds are built here; Native/Skip are recorded
    # as recommendations and produce no Apex.
    target_kind: str = "Apex"          # Apex | Native | Skip
    apex_pattern: str = ""             # Selector | Service | Controller | Utility
    rationale: str = ""
    native_recommendation: str = ""    # e.g. "Salesforce CPQ", "Flow / Approval Process"

    @property
    def is_code(self) -> bool:
        return self.target_kind == "Apex"


@dataclass
class Artifact:
    """One generated Apex target, tracked through its lifecycle."""
    target_name: str
    layer: str
    apex_pattern: str = ""
    main_class: str = ""
    test_class: str = ""
    mapping_notes: str = ""
    sobject_refs: list = field(default_factory=list)
    business_rules: list = field(default_factory=list)
    source_classes: list = field(default_factory=list)
    critic_findings: list = field(default_factory=list)
    # planned -> generated -> reviewed -> accepted | needs_review
    status: str = "planned"

    def to_generated_dict(self) -> dict:
        """Shape the rest of the pipeline (report, parity, write_outputs) expects."""
        return {
            "target_name": self.target_name,
            "layer": self.layer,
            "main_class": self.main_class,
            "test_class": self.test_class,
            "mapping_notes": self.mapping_notes,
            "sobject_refs": self.sobject_refs,
            "business_rules": self.business_rules,
            "source_classes": self.source_classes,
        }


@dataclass
class Blackboard:
    """Shared state for one agentic migration run."""
    input_dir: str
    output_dir: str
    offline: bool = False

    # Repository analysis (filled by the orchestrator's ingest step)
    domains: dict = field(default_factory=dict)
    adjacency: dict = field(default_factory=dict)
    schedule: list = field(default_factory=list)
    all_classes: list = field(default_factory=list)
    item_types: list = field(default_factory=list)
    relations: list = field(default_factory=list)
    enum_types: list = field(default_factory=list)
    schema: dict = field(default_factory=dict)
    source_corpus: str = ""

    # Agent products
    comprehensions: dict = field(default_factory=dict)     # class_name -> understanding
    plan: list = field(default_factory=list)               # [PlanItem]
    artifacts: list = field(default_factory=list)          # [Artifact]

    # Results
    validation_results: dict = field(default_factory=dict)
    reconciliation: dict = field(default_factory=dict)
    verify_result: dict | None = None
    parity: dict = field(default_factory=dict)

    # Traceability
    decisions: list = field(default_factory=list)          # [{t, agent, action, detail}]
    open_questions: list = field(default_factory=list)     # ["...", ...]

    def record(self, agent: str, action: str, detail: str = "") -> None:
        """Append an auditable decision. Every meaningful agent choice lands here."""
        self.decisions.append({"t": round(time.time(), 3), "agent": agent,
                               "action": action, "detail": detail})

    def ask(self, agent: str, question: str) -> None:
        self.open_questions.append(f"[{agent}] {question}")

    def code_plan(self) -> list:
        return [p for p in self.plan if p.is_code]

    def generated_dicts(self) -> list:
        """Artifacts in the dict shape the Phase-0 writer/report/parity consume."""
        return [a.to_generated_dict() for a in self.artifacts]

    def decisions_markdown(self) -> str:
        if not self.decisions:
            return "_(no decisions recorded)_"
        return "\n".join(f"- **{d['agent']}** — {d['action']}"
                         + (f": {d['detail']}" if d["detail"] else "")
                         for d in self.decisions)
