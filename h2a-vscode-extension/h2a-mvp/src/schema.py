"""
schema.py — SObject schema model derived from Hybris items.xml.

This module is the single source of truth for what custom objects and fields
exist in the target org. It is used to:

  1. Inject the exact object/field catalog into the generation prompt (grounding),
     so the LLM writes SOQL against fields that actually exist.
  2. Validate generated Apex: flag SOQL/field references to objects or fields that
     are NOT in the schema — the #1 cause of deploy failures.

Naming follows Salesforce conventions: itemtype `Order` -> `Order__c`,
attribute `totalAmount` -> `TotalAmount__c`. Every custom object gets the
standard `Name`, `Id`, `CreatedDate`, etc. Standard fields are allowed by the
validator without being declared.
"""

from __future__ import annotations

import re

# Java/Hybris type -> Salesforce field type (kept in sync with metadata_generator).
_TYPE_MAP = {
    "java.lang.String": "Text",
    "java.lang.Integer": "Number",
    "java.lang.Long": "Number",
    "java.lang.Double": "Number",
    "java.math.BigDecimal": "Currency",
    "java.lang.Boolean": "Checkbox",
    "java.util.Date": "DateTime",
    "String": "Text",
    "Integer": "Number",
    "Boolean": "Checkbox",
    "Double": "Number",
}

# Standard fields present on every SObject — always valid, never custom-declared.
_STANDARD_FIELDS = {
    "id", "name", "createddate", "createdbyid", "lastmodifieddate",
    "lastmodifiedbyid", "ownerid", "isdeleted", "systemmodstamp",
}


def _obj_api_name(code: str) -> str:
    return f"{code}__c"


def _field_api_name(qualifier: str) -> str:
    # Salesforce convention capitalises the first letter: totalAmount -> TotalAmount__c.
    return f"{qualifier[:1].upper()}{qualifier[1:]}__c"


def build_schema(item_types: list[dict], relations: list[dict] | None = None,
                 enum_types: list[dict] | None = None) -> dict:
    """
    Build the SObject schema from parsed items.xml item types (and optional
    relations + enum types).

    Returns, per object:
        {
          "Order__c": {
            "code": "Order",
            "fields": { "OrderId__c": "Text", "Status__c": "Picklist", ... },
            "picklists": { "Status__c": ["NEW", "SHIPPED"] },   # enum values
            "required": {"Code__c"},                            # optional="false"
            "unique":   {"Code__c"},                            # unique="true"
            "defaults": {"Status__c": "NEW"},
          },
          ...
        }

    `fields` stays `{name: type_string}` for grounding/validation; the extra keys
    drive richer metadata emission (picklists, required/unique, defaults).
    """
    enum_values = {e["name"]: e.get("values", []) for e in (enum_types or [])}
    schema: dict[str, dict] = {}
    for item in item_types or []:
        code = item.get("name") or item.get("code")
        if not code:
            continue
        obj = _obj_api_name(code)
        fields: dict[str, str] = {}
        picklists: dict[str, list] = {}
        required: set = set()
        unique: set = set()
        defaults: dict[str, str] = {}
        for f in item.get("fields", []) or []:
            qualifier = f.get("name") or f.get("qualifier")
            if not qualifier:
                continue
            api = _field_api_name(qualifier)
            raw_type = (f.get("type") or "").strip()
            # An attribute typed as an enum becomes a Picklist with those values.
            base_type = raw_type.split(".")[-1] if raw_type else ""
            if raw_type in enum_values or base_type in enum_values:
                fields[api] = "Picklist"
                picklists[api] = enum_values.get(raw_type) or enum_values.get(base_type, [])
            else:
                fields[api] = _TYPE_MAP.get(raw_type, "Text")
            mods = f.get("modifiers") or {}
            if str(mods.get("optional", "")).lower() == "false":
                required.add(api)
            if str(mods.get("unique", "")).lower() == "true":
                unique.add(api)
            if f.get("default"):
                defaults[api] = f["default"]
        schema[obj] = {"code": code, "fields": fields, "picklists": picklists,
                       "required": required, "unique": unique, "defaults": defaults}

    # Relations: one->many creates a Lookup on the child pointing to the parent.
    for rel in relations or []:
        if rel.get("source_card") == "one" and rel.get("target_card") == "many":
            child = _obj_api_name(rel["target_type"])
            parent = _obj_api_name(rel["source_type"])
            schema.setdefault(child, {"code": rel["target_type"], "fields": {}})
            schema[child]["fields"][parent] = "Lookup"

    return schema


def schema_prompt_block(schema: dict) -> str:
    """Compact, cache-friendly text catalog of objects and fields for the prompt."""
    if not schema:
        return "(no custom objects were derived from items.xml)"
    lines = []
    for obj, meta in sorted(schema.items()):
        field_list = ", ".join(f"{name} ({t})" for name, t in sorted(meta["fields"].items()))
        lines.append(f"- {obj}: {field_list or '(no custom fields)'}")
    return "\n".join(lines)


# ── Field-reference validation ────────────────────────────────────────────────

_SOQL_RE = re.compile(r"\[\s*SELECT\s+(.*?)\s+FROM\s+([A-Za-z0-9_]+__c)", re.IGNORECASE | re.DOTALL)
_FIELD_ACCESS_RE = re.compile(r"\b[A-Za-z_]\w*\.([A-Za-z_]\w*__c)\b")

# Object *positions* only — avoids matching field tokens inside SELECT clauses.
# The generic patterns are anchored to '<' / '>' so a comma-separated SELECT
# field list (e.g. "Code__c, DealerCode__c, TotalAmount__c") is never mistaken
# for a type argument.
_OBJ_POSITION_RES = [
    re.compile(r"\bFROM\s+([A-Za-z]\w*__c)\b", re.IGNORECASE),   # SOQL FROM
    re.compile(r"\bnew\s+([A-Za-z]\w*__c)\s*[\(\[]"),            # new X__c( / new X__c[]
    re.compile(r"<\s*([A-Za-z]\w*__c)\b"),                       # List<X__c
    re.compile(r",\s*([A-Za-z]\w*__c)\s*>"),                     # Map<Id, X__c>
    re.compile(r"\b([A-Za-z]\w*__c)\s+[A-Za-z_]\w*\s*[;=]"),     # X__c var; / X__c var =
]


def validate_field_references(apex_code: str, schema: dict) -> list[dict]:
    """
    Flag references to custom objects/fields that are not in the schema.

    Conservative by design: only *custom* identifiers (ending in `__c`) are
    checked, standard fields are always allowed. Object references are detected
    only in genuine object positions (FROM / new / generic type / declaration),
    never from field tokens in a SELECT list.
    """
    if not schema:
        return []

    issues: list[dict] = []
    known_objects = set(schema.keys())
    # field api name (lowercased) -> set of objects that declare it
    field_to_objs: dict[str, set] = {}
    for obj, meta in schema.items():
        for fname in meta["fields"]:
            field_to_objs.setdefault(fname.lower(), set()).add(obj)

    code_no_comments = re.sub(r"//.*|/\*.*?\*/", "", apex_code, flags=re.DOTALL)

    # 1. Unknown custom objects in object positions.
    referenced_objects = set()
    for rx in _OBJ_POSITION_RES:
        for m in rx.finditer(code_no_comments):
            referenced_objects.add(m.group(1))
    for token in referenced_objects:
        if token not in known_objects:
            issues.append({
                "rule": "unknown_sobject",
                "message": f"References custom object '{token}' which is not defined in items.xml schema.",
                "severity": "WARNING",
                "object": token,          # structured hooks for schema reconciliation
                "field": None,
            })

    # 2. SELECT field lists must reference fields that exist on the FROM object.
    for m in _SOQL_RE.finditer(code_no_comments):
        field_clause, obj = m.group(1), m.group(2)
        if obj not in schema:
            continue  # already flagged as unknown object
        declared = {f.lower() for f in schema[obj]["fields"]}
        for raw in field_clause.split(","):
            field = raw.strip().split(".")[-1].strip()
            fl = field.lower()
            if not field.endswith("__c"):
                continue  # standard/relationship field — allow
            if fl not in declared:
                issues.append({
                    "rule": "unknown_field",
                    "message": f"SOQL selects '{field}' from {obj}, but that field is not in the schema.",
                    "severity": "WARNING",
                    "object": obj,
                    "field": field,
                })

    # 3. Dotted custom field access X.Y__c where Y__c exists on no object at all.
    for m in _FIELD_ACCESS_RE.finditer(code_no_comments):
        field = m.group(1)
        if field.lower() in _STANDARD_FIELDS:
            continue
        if field.lower() not in field_to_objs:
            issues.append({
                "rule": "unknown_field",
                "message": f"References custom field '{field}' which exists on no object in the schema.",
                "severity": "WARNING",
                "object": None,       # object not determinable from a dotted access
                "field": field,
            })

    # Final de-dup across all field issues.
    seen = set()
    return [i for i in issues if not (i["message"] in seen or seen.add(i["message"]))]


# ── Schema reconciliation (auto-resolve warnings) ─────────────────────────────

def _base_token(api_name: str) -> str:
    """'DealerCode__c' -> 'dealercode' — the underlying business name, lowered."""
    core = api_name[:-3] if api_name.endswith("__c") else api_name
    return core.lower()


# Java type keyword -> Salesforce field type, for inferring an auto-added field's
# real type from the source (better than defaulting everything to Text).
_JAVA_TYPE_TO_SF = {
    "string": "Text", "boolean": "Checkbox", "bigdecimal": "Currency",
    "double": "Number", "float": "Number", "integer": "Number", "int": "Number",
    "long": "Number", "short": "Number", "date": "DateTime", "localdate": "Date",
    "localdatetime": "DateTime", "timestamp": "DateTime",
}
_TYPE_KEYWORDS = "|".join(sorted(_JAVA_TYPE_TO_SF, key=len, reverse=True))


def infer_field_type(api_name: str, source_corpus: str) -> str:
    """
    Infer the Salesforce type of an auto-added field from its Java declaration or
    getter in the source (e.g. `BigDecimal dealerCode` -> Currency,
    `boolean isActive` / `getActive()` -> Checkbox). Defaults to Text.
    """
    core = api_name[:-3] if api_name.endswith("__c") else api_name
    if not core:
        return "Text"
    field_lc = core[:1].lower() + core[1:]        # dealerCode
    getter = f"get{core[:1].upper()}{core[1:]}"    # getDealerCode
    patterns = [
        rf"\b({_TYPE_KEYWORDS})\s+{re.escape(getter)}\s*\(",   # <Type> getDealerCode(
        rf"\b({_TYPE_KEYWORDS})\s+{re.escape(field_lc)}\b",    # <Type> dealerCode
    ]
    for pat in patterns:
        m = re.search(pat, source_corpus, re.IGNORECASE)
        if m:
            return _JAVA_TYPE_TO_SF.get(m.group(1).lower(), "Text")
    return "Text"


def _evidenced_in_source(api_name: str, source_corpus: str) -> bool:
    """
    True if the field/object's underlying name appears in the Hybris source —
    i.e. it's a real business concept the items.xml simply didn't declare, not a
    model hallucination. Matches getters/setters/qualifiers (getDealerCode,
    dealerCode, DEALER_CODE-less) by anchoring only the right word boundary.
    """
    base = _base_token(api_name)
    if len(base) < 3:
        return False
    return re.search(re.escape(base) + r"\b", source_corpus.lower()) is not None


def reconcile_schema(schema: dict, validation_results: dict, source_corpus: str) -> tuple[dict, dict]:
    """
    Resolve unknown-field / unknown-object warnings using source evidence.

    Two valid resolutions for an "unknown X__c" warning:
      1. the model referenced something real that items.xml never declared
         → **add it to the schema** (it becomes real SObject/field metadata);
      2. the model hallucinated it
         → **leave it flagged** for the repair loop / human review.

    We decide with evidence: if the underlying name occurs in the Hybris source,
    it's (1); otherwise (2). Mutates and returns an augmented copy of `schema`.

    Returns (augmented_schema, info) with:
      info = {"added_fields":[{object,field,type,reason}],
              "added_objects":[{object,reason}],
              "flagged":[{object,field,rule,reason}]}
    """
    import copy
    schema = copy.deepcopy(schema)
    info = {"added_fields": [], "added_objects": [], "flagged": []}
    handled: set = set()

    for issues in validation_results.values():
        for issue in issues:
            if issue.get("rule") not in ("unknown_field", "unknown_sobject"):
                continue
            obj, field = issue.get("object"), issue.get("field")
            key = (issue["rule"], obj, field)
            if key in handled:
                continue
            handled.add(key)

            # Unknown object in an object position.
            if issue["rule"] == "unknown_sobject" and obj:
                if obj in schema:
                    continue
                if _evidenced_in_source(obj, source_corpus):
                    schema[obj] = {"code": obj[:-3], "fields": {}}
                    info["added_objects"].append(
                        {"object": obj, "reason": "referenced in Hybris source; not declared in items.xml"})
                else:
                    info["flagged"].append(
                        {"object": obj, "field": None, "rule": "unknown_sobject",
                         "reason": "no source evidence — likely a hallucinated object"})
                continue

            # Unknown field on a known object.
            if issue["rule"] == "unknown_field" and field:
                if obj and obj in schema:
                    if field in schema[obj]["fields"]:
                        continue
                    if _evidenced_in_source(field, source_corpus):
                        ftype = infer_field_type(field, source_corpus)
                        schema[obj]["fields"][field] = ftype
                        info["added_fields"].append(
                            {"object": obj, "field": field, "type": ftype,
                             "reason": f"used in Hybris source; not declared in items.xml (type inferred as {ftype})"})
                    else:
                        info["flagged"].append(
                            {"object": obj, "field": field, "rule": "unknown_field",
                             "reason": "no source evidence — likely a hallucinated field"})
                else:
                    # dotted access with no determinable object — cannot safely add
                    info["flagged"].append(
                        {"object": None, "field": field, "rule": "unknown_field",
                         "reason": "object not determinable from a dotted access; left for review"})

    return schema, info
