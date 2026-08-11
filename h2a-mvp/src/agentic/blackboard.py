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
    # Policy: every real target is Convert — its logic is ALWAYS built. `Skip` is
    # reserved for provably dead code / framework glue / pure DTOs and must carry a
    # reason. A native-product fit never suppresses conversion; it is recorded as a
    # review suggestion (`native_recommendation`) on a Convert item instead.
    target_kind: str = "Convert"       # Convert | Skip
    apex_pattern: str = ""             # Selector | Service | Controller | Utility | Component
    rationale: str = ""
    native_recommendation: str = ""    # review suggestion only, e.g. "Salesforce CPQ"

    @property
    def is_code(self) -> bool:
        return self.target_kind != "Skip"


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
    # Human-review suggestions carried alongside a fully-converted artifact, e.g.
    # "consider Salesforce CPQ for this pricing logic". Never a reason to skip.
    review_flags: list = field(default_factory=list)
    # Frontend targets: the LWC bundle {js, html, css, meta, test} and, when the
    # component reads data, a generated @AuraEnabled Apex controller {name, main_class, test_class}.
    lwc_bundle: dict = field(default_factory=dict)
    apex_controller: dict = field(default_factory=dict)
    # planned -> generated -> reviewed -> accepted | needs_review
    status: str = "planned"

    @property
    def is_lwc(self) -> bool:
        return self.layer == "Component"

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
            "review_flags": self.review_flags,
            "lwc_bundle": self.lwc_bundle,
            "apex_controller": self.apex_controller,
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
    # Frontend framework glue / type-only files recorded (not converted) so the
    # completeness ledger can account for them with a reason.
    frontend_skipped: list = field(default_factory=list)
    # JUnit tests found in the source. Never migrated — they are the recorded
    # behaviour that characterization testing replays against the generated Apex.
    test_classes: list = field(default_factory=list)
    # Preflight verdict: what this codebase is, and anything alarming in it.
    preflight: dict = field(default_factory=dict)
    # Files we could not read or parse. Recorded rather than dropped: a migration that
    # silently forgets a file is worse than one that admits it could not read it.
    unreadable: list = field(default_factory=list)
    # Hybris business processes (`*-process.xml`). Read but not yet converted — the
    # action classes migrate, the state machine that sequences them does not. Held here
    # so the ledger can say so, which it could not when these files went unread.
    processes: list = field(default_factory=list)
    # Hybris patterns that become hazards on Salesforce (src/radar.py).
    radar: dict = field(default_factory=dict)
    # What the destination Salesforce org already contains (src/orgfit.py).
    orgfit: dict = field(default_factory=dict)
    # Estimated cost/duration, produced before the first billable token.
    forecast: dict = field(default_factory=dict)
    # Late-stage joins, kept on the board so alignment can read them.
    characterization: dict = field(default_factory=dict)
    rule_ledger: dict = field(default_factory=dict)
    # Who approved which gate, when, and what they were looking at. The audit a migration
    # ends in is only worth signing if it records the human, and an unsupervised run has
    # no human to record — which is exactly what these entries have to be able to say.
    approvals: list = field(default_factory=list)

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
    # Optional live listener: called with each decision as it's recorded, so a UI can
    # show the audit trail building in real time. None (CLI/extension) → no-op.
    on_decision: object = None

    def record(self, agent: str, action: str, detail: str = "") -> None:
        """Append an auditable decision. Every meaningful agent choice lands here."""
        entry = {"t": round(time.time(), 3), "agent": agent, "action": action, "detail": detail}
        self.decisions.append(entry)
        if self.on_decision is not None:
            try:
                self.on_decision(entry)
            except Exception:      # a UI hiccup must never break a migration
                pass

    def ask(self, agent: str, question: str) -> None:
        self.open_questions.append(f"[{agent}] {question}")

    def code_plan(self) -> list:
        return [p for p in self.plan if p.is_code]

    def output_path(self, artifact) -> str:
        """Where an artifact lands on disk. The unit a collision is measured in — an
        Apex `Pricing.cls` and an LWC `lwc/Pricing` share a name but not a file."""
        name = getattr(artifact, "target_name", "")
        return f"lwc/{name}" if getattr(artifact, "layer", "") == "Component" else f"{name}.cls"

    def output_collisions(self) -> dict:
        """Artifacts that would write to the same path, keyed by that path.

        The ledger's guarantee is that no input was dropped, and it proved that by
        walking source → artifact. That check passes even when two artifacts share a
        target name, because each source still finds *an* artifact — but only one of
        them survives the write, so the other's logic is not in the output the ledger
        just called complete. Inputs being accounted for is not the same claim as
        outputs being distinct, and only the second one is checkable here.
        """
        by_path: dict[str, list] = {}
        for a in self.artifacts:
            by_path.setdefault(self.output_path(a), []).append(a)
        return {p: arts for p, arts in by_path.items() if len(arts) > 1}

    def completeness_ledger(self) -> list:
        """Account for every ingested source class — the proof that nothing was
        silently dropped. Each row: {source, layer, outcome, target, note} where
        outcome is converted | flagged | skipped | unaccounted | overwritten | manual."""
        by_source = {}
        for a in self.artifacts:
            for c in a.source_classes:
                by_source[c.get("class_name")] = a

        # Which artifacts lost a write race. Every one of them is reported, not just the
        # losers: last-write-wins means the survivor depends on iteration order, so
        # naming a winner here would be a guess presented as a fact.
        collided = {id(a): p for p, arts in self.output_collisions().items() for a in arts}
        skipped = {}
        for p in self.plan:
            if p.target_kind == "Skip":
                for c in p.source_classes:
                    skipped[c.get("class_name")] = p.rationale or "no reason recorded"

        rows = []
        for cls in self.all_classes:
            name = cls.get("class_name")
            layer = cls.get("layer", "")
            if layer == "Model":
                rows.append({"source": name, "layer": layer, "outcome": "converted",
                             "target": "SObject metadata", "note": "data model → custom object"})
                continue
            art = by_source.get(name)
            if art is not None:
                flagged = bool(art.review_flags)
                target = self.output_path(art)
                if id(art) in collided:
                    rows.append({
                        "source": name, "layer": layer, "outcome": "overwritten",
                        "target": target,
                        "note": f"more than one artifact writes `{target}` — only one "
                                "survived, so this class's logic may not be in the output"})
                else:
                    rows.append({"source": name, "layer": layer,
                                 "outcome": "flagged" if flagged else "converted",
                                 "target": target,
                                 "note": "; ".join(art.review_flags) if flagged else ""})
            elif name in skipped:
                rows.append({"source": name, "layer": layer, "outcome": "skipped",
                             "target": "—", "note": skipped[name]})
            else:
                rows.append({"source": name, "layer": layer, "outcome": "unaccounted",
                             "target": "—", "note": "NOT represented in output — investigate"})

        # Files that never reached the parser at all. These are the rows that would
        # otherwise vanish without trace, so they are called out as needing a human.
        for u in self.unreadable:
            rows.append({"source": u.get("class_name", "?"), "layer": "—",
                         "outcome": "unreadable", "target": "—",
                         "note": f"{u.get('unreadable', 'unknown')} ({u.get('file', '')})"
                                 " — migrate this file by hand"})

        # Business processes: read, resolved to their action classes, and reported as
        # awaiting manual migration. Before these files were parsed at all, a process
        # could not appear here even as a loss — the one gap the ledger could not see.
        if self.processes:
            from src.processes import ledger_rows
            converted = {r["source"] for r in rows if r["outcome"] in ("converted", "flagged")}
            rows.extend(ledger_rows(self.processes, converted))

        # Frontend framework glue / type-only files: no business logic to convert.
        for sk in self.frontend_skipped:
            rows.append({"source": sk.get("class_name", "?"), "layer": sk.get("layer", ""),
                         "outcome": "skipped", "target": "—", "note": sk.get("reason", "")})
        return rows

    def generated_dicts(self) -> list:
        """Artifacts in the dict shape the Phase-0 writer/report/parity consume."""
        return [a.to_generated_dict() for a in self.artifacts]

    def decisions_markdown(self) -> str:
        if not self.decisions:
            return "_(no decisions recorded)_"
        return "\n".join(f"- **{d['agent']}** — {d['action']}"
                         + (f": {d['detail']}" if d["detail"] else "")
                         for d in self.decisions)
