"""
impex.py — Hybris ImpEx → Salesforce data migration (Phase 2).

ImpEx is Hybris's data format (semicolon-delimited, with typed headers). A real
migration is not just code — the *data* has to move too. This translates `.impex`
into a Salesforce-loadable form:

  - one CSV per item type (Product → Product__c), columns mapped to `Field__c`,
  - the `[unique=true]` attribute becomes an **External ID** so loads are
    idempotent upserts (re-runnable, no duplicates),
  - a `DATA_MIGRATION.md` runbook with the exact `sf data upsert` commands,
  - and (when object metadata exists) the External ID field is marked
    `externalId=true` / `unique=true` so the upsert key actually works.

Deterministic and dependency-free — no LLM needed to parse a data format. Simple
one-key references become `Rel__r.Key__c` relationship columns; nested/composite
references are flagged for manual mapping rather than guessed at.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field as dc_field
from pathlib import Path

_MODES = ("INSERT_UPDATE", "INSERT", "UPDATE", "REMOVE")
_HEADER_RE = re.compile(r"^(" + "|".join(_MODES) + r")\s+(\w+)\s*;(.*)$")


def _api_obj(code: str) -> str:
    return f"{code}__c"


def _api_field(qualifier: str) -> str:
    q = qualifier.strip()
    return f"{q[:1].upper()}{q[1:]}__c" if q else q


@dataclass
class ImpexColumn:
    attr: str
    modifiers: dict = dc_field(default_factory=dict)
    is_reference: bool = False
    is_macro: bool = False
    ref_key: str | None = None     # single-key reference target (e.g. code)
    composite: bool = False        # nested/multi-key reference — not auto-mappable
    raw: str = ""

    @property
    def is_unique(self) -> bool:
        return str(self.modifiers.get("unique", "")).lower() == "true"


@dataclass
class ImpexBlock:
    mode: str
    type_code: str
    columns: list          # [ImpexColumn]
    rows: list             # [ {attr: value} ]


@dataclass
class DataObject:
    object_api: str
    type_code: str
    modes: set = dc_field(default_factory=set)
    headers: list = dc_field(default_factory=list)     # CSV column headers (SF field / relationship)
    records: list = dc_field(default_factory=list)     # [ {header: value} ]
    external_id: str | None = None                     # SF field used as upsert key
    external_id_note: str = ""
    manual_relationships: list = dc_field(default_factory=list)   # composite refs, for manual mapping


# ── Parsing ───────────────────────────────────────────────────────────────────

def _parse_column(raw: str) -> ImpexColumn:
    raw = raw.strip()
    modifiers: dict = {}
    core = raw
    m = re.search(r"\[(.*)\]\s*$", raw)
    if m:
        core = raw[:m.start()].strip()
        for part in m.group(1).split(","):
            part = part.strip()
            if not part:
                continue
            if "=" in part:
                k, v = part.split("=", 1)
                modifiers[k.strip()] = v.strip().strip("'\"")
            else:
                modifiers[part] = "true"

    if core.startswith("$"):
        return ImpexColumn(attr=core, modifiers=modifiers, is_macro=True, raw=raw)

    if "(" in core:
        attr = core.split("(")[0].strip()
        inner = core[core.find("(") + 1:core.rfind(")")]
        composite = ("(" in inner) or ("," in inner)
        ref_key = None if composite else inner.strip()
        return ImpexColumn(attr=attr, modifiers=modifiers, is_reference=True,
                           ref_key=ref_key, composite=composite, raw=raw)

    return ImpexColumn(attr=core, modifiers=modifiers, raw=raw)


def parse_impex(text: str) -> list:
    """Parse ImpEx text into a list of ImpexBlock (header + its data rows)."""
    blocks: list = []
    current: ImpexBlock | None = None

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("$") and "=" in stripped and not _HEADER_RE.match(stripped):
            continue  # macro definition — context, not a record

        h = _HEADER_RE.match(stripped)
        if h:
            cols = [_parse_column(c) for c in h.group(3).split(";")]
            current = ImpexBlock(mode=h.group(1), type_code=h.group(2), columns=cols, rows=[])
            blocks.append(current)
            continue

        if current is not None and raw_line.lstrip().startswith(";"):
            values = raw_line.split(";")[1:]      # drop the leading (item-type) column
            row = {}
            for col, val in zip(current.columns, values):
                row[col.attr if not col.is_macro else col.raw] = val.strip()
            current.rows.append(row)

    return blocks


# ── Data plan ─────────────────────────────────────────────────────────────────

def build_data_plan(blocks: list) -> list:
    """Group blocks by item type into DataObjects with CSV headers + records."""
    objects: dict[str, DataObject] = {}

    for blk in blocks:
        obj = objects.setdefault(blk.type_code,
                                 DataObject(object_api=_api_obj(blk.type_code), type_code=blk.type_code))
        obj.modes.add(blk.mode)

        # Column → CSV header mapping (positional; macros/composite refs excluded).
        col_headers: list = []   # aligned with blk.columns; None = drop from CSV
        for col in blk.columns:
            if col.is_macro:
                col_headers.append(None)
            elif col.is_reference and col.composite:
                col_headers.append(None)
                spec = f"{col.attr} → {col.raw}"
                if spec not in obj.manual_relationships:
                    obj.manual_relationships.append(spec)
            elif col.is_reference and col.ref_key:
                header = f"{_api_field(col.attr)[:-3]}__r.{_api_field(col.ref_key)}"
                col_headers.append(header)
            else:
                header = _api_field(col.attr)
                col_headers.append(header)
                if col.is_unique and obj.external_id is None:
                    obj.external_id = header

        for h in col_headers:
            if h and h not in obj.headers:
                obj.headers.append(h)

        for row in blk.rows:
            rec = {}
            for col, header in zip(blk.columns, col_headers):
                if header is None:
                    continue
                key = col.attr
                rec[header] = row.get(key, "")
            obj.records.append(rec)

    plan = list(objects.values())
    for obj in plan:
        if obj.external_id is None and obj.headers:
            obj.external_id_note = ("no [unique=true] attribute found — pick an External ID "
                                    "manually before upserting")
    return plan


# ── Emit ──────────────────────────────────────────────────────────────────────

def write_data_migration(output_dir: str, plan: list) -> list:
    """Write per-object CSVs + DATA_MIGRATION.md. Returns files written."""
    out = Path(output_dir)
    data_dir = out / "data"
    written: list = []
    if any(o.records for o in plan):
        data_dir.mkdir(parents=True, exist_ok=True)

    for obj in plan:
        if not obj.records:
            continue
        csv_path = data_dir / f"{obj.object_api}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=obj.headers)
            w.writeheader()
            for rec in obj.records:
                w.writerow({h: rec.get(h, "") for h in obj.headers})
        written.append(str(csv_path))

    md = _build_runbook(plan)
    md_path = out / "DATA_MIGRATION.md"
    md_path.write_text(md, encoding="utf-8")
    written.append(str(md_path))
    return written


def _build_runbook(plan: list) -> str:
    lines = ["# Data Migration Runbook (ImpEx → Salesforce)", "",
             "Generated from the Hybris `.impex` files. Each item type became a CSV of "
             "records keyed by an **External ID**, so loads are idempotent upserts "
             "(safe to re-run). Load parents before children.", ""]
    loadable = [o for o in plan if o.records]
    if not loadable:
        lines.append("_No ImpEx data rows were found._")
        return "\n".join(lines) + "\n"

    lines += ["## Objects", "", "| Object | Records | External ID | Modes |",
              "|---|---|---|---|"]
    for o in loadable:
        lines.append(f"| `{o.object_api}` | {len(o.records)} | "
                     f"{('`'+o.external_id+'`') if o.external_id else '⚠️ pick one'} | "
                     f"{', '.join(sorted(o.modes))} |")
    lines.append("")

    lines += ["## Load commands", "",
              "```bash", "# Authorise once:  sf org login web"]
    for o in loadable:
        if o.external_id:
            lines.append(f"sf data upsert bulk --sobject {o.object_api} "
                         f"--file data/{o.object_api}.csv --external-id {o.external_id} --wait 10")
        else:
            lines.append(f"# {o.object_api}: set an External ID field, then:")
            lines.append(f"# sf data upsert bulk --sobject {o.object_api} "
                         f"--file data/{o.object_api}.csv --external-id <Field__c> --wait 10")
    lines += ["```", ""]

    manual = [(o.object_api, o.manual_relationships) for o in loadable if o.manual_relationships]
    if manual:
        lines += ["## Relationships to map manually", "",
                  "Composite / nested ImpEx references can't be auto-mapped to a single "
                  "lookup — resolve these after the parents are loaded:", ""]
        for obj_api, refs in manual:
            for r in refs:
                lines.append(f"- `{obj_api}`: {r}")
        lines.append("")

    lines += ["## Notes", "",
              "- Each External ID field must be marked **External ID** and **Unique** on "
              "its object (the migrator sets this automatically when it also generates the "
              "object metadata).",
              "- Simple `Rel__r.Key__c` columns load a lookup by the parent's External ID; "
              "ensure the parent object + that External ID field exist first."]
    return "\n".join(lines) + "\n"


def mark_external_id_fields(output_dir: str, plan: list) -> list:
    """Patch each object's External ID field-meta to add externalId + unique nodes.

    No-op when the object metadata doesn't exist (e.g. standalone `impex` command
    with no code migration) — returns only the files it actually patched.
    """
    base = Path(output_dir) / "force-app" / "main" / "default" / "objects"
    patched: list = []
    for obj in plan:
        if not obj.external_id:
            continue
        fpath = base / obj.object_api / "fields" / f"{obj.external_id}.field-meta.xml"
        if not fpath.exists():
            continue
        xml = fpath.read_text(encoding="utf-8")
        if "<externalId>" not in xml:
            xml = xml.replace("</CustomField>", "    <externalId>true</externalId>\n</CustomField>")
        if "<unique>" not in xml:
            xml = xml.replace("</CustomField>", "    <unique>true</unique>\n</CustomField>")
        fpath.write_text(xml, encoding="utf-8")
        patched.append(str(fpath))
    return patched


# ── Directory driver ──────────────────────────────────────────────────────────

def find_impex_files(input_dir: str) -> list:
    return sorted(str(p) for p in Path(input_dir).rglob("*.impex"))


def translate_impex_dir(input_dir: str, output_dir: str, *, mark_metadata: bool = True) -> dict:
    """Find all `.impex` under input_dir, translate to CSV + runbook. Returns a summary."""
    files = find_impex_files(input_dir)
    blocks: list = []
    for f in files:
        blocks += parse_impex(Path(f).read_text(encoding="utf-8"))
    plan = build_data_plan(blocks)
    written = write_data_migration(output_dir, plan) if plan else []
    patched = mark_external_id_fields(output_dir, plan) if (plan and mark_metadata) else []
    return {
        "impex_files": files,
        "objects": [{"object": o.object_api, "records": len(o.records),
                     "external_id": o.external_id} for o in plan if o.records],
        "files_written": written,
        "metadata_patched": patched,
        "record_total": sum(len(o.records) for o in plan),
    }
