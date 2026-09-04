"""
ir.py — the normalised migration model that source and target adapters meet at.

**This is not a new invention.** The engine has always had an IR; it was simply implicit
and Java-shaped — `ingest()` returns dicts that `generate()` knows how to read, and the
contract between them lived in whoever last edited both. This module names that contract,
so a second source (PHP) and a second target (Java/Spring) can meet the same shapes instead
of the pipeline growing a second undocumented one.

Two design rules, both learned from this codebase rather than chosen in the abstract:

**Every field a platform cannot fill is optional, never faked.** A Magento module has no
`layer` in the Hybris sense and Hybris has no PHP traits. Adapters leave such fields empty
and the assurance layer reports them as unknown — the alternative is a plausible default
that reads as fact.

**Dicts remain the wire format, dataclasses the contract.** `from_dict`/`to_dict` round-trip
so the IR can be introduced *underneath* the existing pipeline without rewriting the eight
modules that pass dicts today. That is what makes v2 adoptable in slices instead of in one
irreversible commit.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields as dc_fields
from typing import Any

IR_VERSION = 1


def _only(cls, data: dict) -> dict:
    """Drop keys a dataclass does not declare, so an older payload still loads."""
    known = {f.name for f in dc_fields(cls)}
    return {k: v for k, v in (data or {}).items() if k in known}


@dataclass
class Parameter:
    name: str = ""
    type: str = ""


@dataclass
class Method:
    """One callable on a source unit. `body` is optional — some parsers give only signatures."""
    name: str = ""
    return_type: str = ""
    parameters: list = field(default_factory=list)   # [Parameter | dict]
    body: str = ""
    visibility: str = ""
    line_start: int = 0
    line_end: int = 0
    #: The docblock or javadoc immediately above the method, verbatim. Kept because on
    #: both platforms it is frequently the only written statement of what the method is
    #: *for* — and on a dynamically typed source it may be the only statement of type.
    doc: str = ""
    is_static: bool = False


@dataclass
class SourceUnit:
    """One unit of source: a Java class, a PHP class, an Angular component.

    `layer` is the platform's own idea of role (Service, DAO, Controller, Component…).
    A source that has no such notion leaves it empty rather than guessing — downstream,
    an empty layer means "unknown", and a wrong one silently mis-plans the migration.
    """
    name: str = ""
    layer: str = ""
    file: str = ""
    source: str = ""
    methods: list = field(default_factory=list)      # [Method | dict]
    fields: list = field(default_factory=list)
    annotations: list = field(default_factory=list)  # Java annotations / PHP attributes
    referenced_types: list = field(default_factory=list)
    encoding: str = ""
    is_test: bool = False
    # Populated only when the file could not be read or parsed. A unit that carries this
    # is reported in the completeness ledger rather than dropped.
    unreadable: str = ""
    # Anything a platform carries that the IR does not model yet, preserved verbatim.
    #
    # Not a shortcut — a rule. A frontend Component arrives with `selector`, `inputs`,
    # `outputs`, `template` and `styles`, none of which mean anything to a Java class, and
    # dropping them on the way through the IR silently broke LWC generation. Modelling
    # every platform's every field would make the IR a union of two schemas; dropping the
    # unmodelled ones is the same silent loss this product exists to prevent. So they ride
    # along, untouched, and surface again on the way out.
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "SourceUnit":
        d = dict(d or {})
        d.setdefault("name", d.get("class_name", ""))
        known = {f.name for f in dc_fields(cls)} | {"class_name"}
        unit = cls(**_only(cls, d))
        unit.extra = {k: v for k, v in d.items() if k not in known}
        return unit

    def to_dict(self) -> dict:
        """Back to the shape the current pipeline passes around.

        `class_name` is emitted alongside `name` because every existing consumer reads
        `class_name`; dropping it would be a rewrite rather than a refactor.
        """
        d = asdict(self)
        d.pop("extra", None)
        d.update(self.extra)
        d["class_name"] = self.name
        return d


@dataclass
class DataType:
    """One entity in the source's data model — a Hybris itemtype, a Magento entity."""
    code: str = ""
    extends: str = ""
    attributes: list = field(default_factory=list)   # [{name, type, required, unique, default}]
    deployment: str = ""
    # Attributes the source declares somewhere we cannot read statically — Magento EAV
    # lives partly in the database. Recorded so the gap is reportable, not invisible.
    undeclared_note: str = ""

    def to_dict(self) -> dict:
        """The wire format, under both spellings.

        The two sources disagreed about this: Hybris put plain `{name, fields}` dicts in
        `DataModel.types` while Adobe put `DataType` objects with `code` and
        `attributes`. Everything downstream reads one or the other, so whichever source
        ran second broke — `'DataType' object has no attribute 'get'`, from the schema
        builder, on the first Adobe run that got that far.

        Emitting both names is the same choice `SourceUnit.to_dict` already makes with
        `class_name`: every existing consumer keeps working, and there is one canonical
        object to read rather than two shapes to guess between. [1.33]
        """
        return {"code": self.code, "name": self.code,
                "attributes": list(self.attributes), "fields": list(self.attributes),
                "extends": self.extends, "deployment": self.deployment,
                "undeclared_note": self.undeclared_note}

    @classmethod
    def from_dict(cls, d: dict) -> "DataType":
        d = dict(d or {})
        return cls(code=d.get("code") or d.get("name") or "",
                   extends=d.get("extends", ""),
                   attributes=list(d.get("attributes") or d.get("fields") or []),
                   deployment=d.get("deployment", ""),
                   undeclared_note=d.get("undeclared_note", ""))


@dataclass
class DataModel:
    types: list = field(default_factory=list)        # [DataType | dict]
    relations: list = field(default_factory=list)
    enums: list = field(default_factory=list)


@dataclass
class ScheduledJob:
    """A cronjob / crontab entry."""
    name: str = ""
    cron: str = ""
    implemented_by: str = ""
    file: str = ""


@dataclass
class ProcessStep:
    id: str = ""
    ref: str = ""                                    # bean id / class ref
    implemented_by: str = ""
    transitions: list = field(default_factory=list)  # [{name, to}]
    kind: str = "action"                             # action | wait | split | join


@dataclass
class ProcessDef:
    """A workflow state machine — a Hybris business process, a Magento state flow."""
    name: str = ""
    file: str = ""
    start: str = ""
    on_error: str = ""
    steps: list = field(default_factory=list)        # [ProcessStep | dict]
    end_states: list = field(default_factory=list)
    unreadable: str = ""


@dataclass
class RecordedBehaviour:
    """What the source's own tests say the old system did — characterization input."""
    id: str = ""
    label: str = ""
    target_unit: str = ""
    target_method: str = ""
    setup: str = ""
    expected: dict = field(default_factory=dict)
    source_file: str = ""


@dataclass
class Hazard:
    """A source pattern that becomes a problem on the target platform."""
    id: str = ""
    rule: str = ""
    severity: str = ""
    file: str = ""
    line: int = 0
    source_unit: str = ""
    detail: str = ""
    fix: str = ""


@dataclass
class SourceModel:
    """Everything a source adapter produces — the left-hand side of the contract."""
    ir_version: int = IR_VERSION
    platform: str = ""                               # "hybris" | "adobe-commerce"
    root: str = ""
    units: list = field(default_factory=list)        # [SourceUnit]
    tests: list = field(default_factory=list)        # [SourceUnit] — held aside, never migrated
    unreadable: list = field(default_factory=list)   # [SourceUnit] with `unreadable` set
    skipped: list = field(default_factory=list)      # framework glue, with a reason
    data_model: DataModel = field(default_factory=DataModel)
    jobs: list = field(default_factory=list)         # [ScheduledJob]
    processes: list = field(default_factory=list)    # [ProcessDef]
    behaviours: list = field(default_factory=list)   # [RecordedBehaviour]
    hazards: list = field(default_factory=list)      # [Hazard]
    dependency_order: list = field(default_factory=list)
    # Top-level keys the IR does not model yet — same rule as `SourceUnit.extra`.
    extra: dict = field(default_factory=dict)

    # ── adoption seam ────────────────────────────────────────────────────────
    # The existing pipeline speaks `ingest()`'s dict. These two functions let the IR sit
    # underneath it without a rewrite: adapters build a SourceModel, and anything not yet
    # migrated to the IR reads the same dict it always did.

    @classmethod
    def from_ingest(cls, res: dict, *, platform: str = "", root: str = "") -> "SourceModel":
        res = res or {}
        return cls(
            platform=platform, root=root,
            units=[SourceUnit.from_dict(c) for c in res.get("classes", [])],
            tests=[SourceUnit.from_dict(c) for c in res.get("test_classes", [])],
            unreadable=[SourceUnit.from_dict(c) for c in res.get("unreadable", [])],
            skipped=list(res.get("frontend_skipped", [])),
            data_model=DataModel(types=list(res.get("item_types", [])),
                                 relations=list(res.get("relations", [])),
                                 enums=list(res.get("enum_types", []))),
            dependency_order=list(res.get("dependency_order", [])),
            extra={k: v for k, v in res.items() if k not in {
                "classes", "test_classes", "unreadable", "frontend_skipped",
                "item_types", "relations", "enum_types", "dependency_order"}},
        )

    def to_ingest(self) -> dict:
        """The exact dict shape the current pipeline consumes, so v1 and v2 agree."""
        return {
            "classes": [u.to_dict() for u in self.units],
            "test_classes": [u.to_dict() for u in self.tests],
            "unreadable": [u.to_dict() for u in self.unreadable],
            # Dicts, like every other key here: this method's whole job is the wire
            # format, and a source that put objects in `skipped` reached the completeness
            # ledger — which is platform-neutral and reads dicts — as an AttributeError.
            # [1.33]
            "frontend_skipped": [s.to_dict() if hasattr(s, "to_dict") else s
                                 for s in self.skipped],
            # Dicts, under both spellings — see `DataType.to_dict`. Passing the objects
            # through made every downstream reader source-dependent. [1.33]
            "item_types": [d.to_dict() if hasattr(d, "to_dict") else d
                           for d in self.data_model.types],
            "relations": list(self.data_model.relations),
            "enum_types": list(self.data_model.enums),
            "dependency_order": list(self.dependency_order),
            **self.extra,
        }


@dataclass
class TargetArtifact:
    """One thing a target adapter produces — an Apex class, a Java service, an LWC bundle."""
    name: str = ""
    kind: str = ""                                   # class | test | component | metadata | flow
    path: str = ""                                   # relative to the output package root
    body: str = ""
    source_units: list = field(default_factory=list) # names of the units it came from
    notes: list = field(default_factory=list)


def validate(model: SourceModel) -> list[str]:
    """Problems that would produce a confidently wrong migration if left unsaid.

    Returns complaints rather than raising: a partially-readable estate is still worth
    migrating, and the completeness ledger is where the gaps belong. The one thing this
    must not do is let a malformed model through in silence.
    """
    problems = []
    if model.ir_version != IR_VERSION:
        problems.append(f"IR version {model.ir_version} != {IR_VERSION}")
    if not model.platform:
        problems.append("source model does not name its platform")
    seen = set()
    for u in model.units:
        if not u.name:
            problems.append(f"a unit has no name ({u.file or 'unknown file'})")
        elif u.name in seen:
            # Two units of the same name collide downstream: one silently wins the write.
            problems.append(f"duplicate unit name: {u.name}")
        else:
            seen.add(u.name)
    return problems
