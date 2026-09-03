"""
php_types.py — resolving PHP types from declarations, and refusing to invent the rest. [2.12]

PHP will let a property be untyped, a parameter be untyped, and a method return `mixed`.
Java will not. Every one of those gaps has to be filled before a Hybris item type or a
service signature can be generated, and there are exactly two ways to fill it: find a
declaration somewhere, or guess.

Guessing is the failure this module exists to prevent, and it is a quiet one. A guessed
`String` compiles. The migration reports success, the field deploys, and the mismatch
surfaces the first time a real value flows through it — by which point the guess is
indistinguishable from a requirement.

So the rule is: **a type is resolved only from a declaration.** Four count, in descending
authority, and each resolution records which one answered so a reviewer can weigh it:

    declared   `float $subtotal` — the language itself said so
    docblock   `@param float $subtotal` — the author said so, in the place PHP made them
               say it when the signature could not
    schema     a db_schema.xml column or an EAV attribute of the same name
    —          nothing said so. The type stays empty and the unit goes to must-review.

Usage is deliberately *not* a source. `$x = $this->price * 2` strongly suggests a number,
and "strongly suggests" is the thing that gets a migration into trouble.
"""

from __future__ import annotations

import re

#: PHP scalar and common class types → the neutral IR types used elsewhere.
_PHP_TO_IR = {
    "int": "Integer", "integer": "Integer", "float": "Double", "double": "Double",
    "string": "String", "bool": "Boolean", "boolean": "Boolean",
    "array": "List", "iterable": "List",
    "DateTime": "DateTime", "DateTimeInterface": "DateTime",
    "DateTimeImmutable": "DateTime",
}

#: Types that carry no information. `mixed` is PHP for "we did not say".
_EMPTY = {"", "mixed", "null", "static", "self"}

#: `void` is a declaration, not a gap: the author said the method returns nothing. Counting
#: it as unresolved sent every `execute(): void` in the codebase to must-review, which is
#: how a review queue stops being read.
_VOID = {"void", "never"}

#: Declared, and with no single Java equivalent. Distinct from "nobody said" because the
#: reviewer's job is different: this one is a *modelling* decision, not a missing fact.
_UNMAPPABLE = {"callable", "closure", "object", "resource", "iterable"}

_DOC_PARAM = re.compile(r"@param\s+([\w\\|\[\]?]+)\s+\$(\w+)")
_DOC_RETURN = re.compile(r"@return\s+([\w\\|\[\]?]+)")
_DOC_VAR = re.compile(r"@var\s+([\w\\|\[\]?]+)")


def to_ir_type(php: str) -> str:
    """A PHP type as the neutral IR spells it, or "" when it says nothing.

    A nullable `?float` is still a float — nullability is a separate fact, and losing the
    type to keep the question mark would be the wrong trade.
    """
    t = (php or "").strip().lstrip("?").lstrip("\\")
    if "|" in t:
        # A union that is just `T|null` is T. A genuine union is not expressible as one
        # Java type, so it resolves to nothing and goes to review.
        parts = [p for p in t.split("|") if p.strip().lower() not in ("null", "")]
        t = parts[0] if len(parts) == 1 else ""
    if t.endswith("[]"):
        return "List"
    if t.lower() in _VOID:
        return "void"
    if t.lower() in _EMPTY or t.lower() in _UNMAPPABLE:
        return ""
    return _PHP_TO_IR.get(t, _PHP_TO_IR.get(t.lower(), t.split("\\")[-1] or ""))


def _from_doc(doc: str, kind: str, name: str = "") -> str:
    if not doc:
        return ""
    if kind == "param":
        for t, n in _DOC_PARAM.findall(doc):
            if n == name:
                return t
        return ""
    if kind == "return":
        m = _DOC_RETURN.search(doc)
        return m.group(1) if m else ""
    m = _DOC_VAR.search(doc)
    return m.group(1) if m else ""


def resolve(units: list, data_types: list | None = None) -> dict:
    """Fill in every type that a declaration supports; report the rest.

    Mutates nothing: returns `{resolutions, unresolved}` where a resolution records what
    was decided and on whose authority, and `unresolved` is what no declaration covered.
    """
    schema: dict = {}
    for dt in data_types or []:
        for a in getattr(dt, "attributes", None) or []:
            # A column and an attribute of the same name in different entities are the
            # same guess if they disagree, so a conflict resolves to nothing.
            name = a.get("name", "")
            t = a.get("type", "")
            if name in schema and schema[name] != t:
                schema[name] = ""
            elif name:
                schema[name] = t

    resolutions, unresolved = [], []

    def decide(where: str, declared: str, doc: str, kind: str, name: str):
        ir_declared = to_ir_type(declared)
        if ir_declared:
            return {"where": where, "name": name, "type": ir_declared, "via": "declared"}
        from_doc = to_ir_type(_from_doc(doc, kind, name))
        if from_doc:
            return {"where": where, "name": name, "type": from_doc, "via": "docblock"}
        from_schema = schema.get(name, "")
        if from_schema:
            return {"where": where, "name": name, "type": from_schema, "via": "schema"}

        # Declared, but with no single Java equivalent. A different question for the
        # reviewer than an absent declaration: one is a modelling decision, the other is
        # a missing fact, and telling them apart is most of what makes a queue usable.
        stated = (declared or _from_doc(doc, kind, name) or "").strip().lstrip("?\\")
        if stated.lower() in _UNMAPPABLE:
            return {"where": where, "name": name, "type": "", "via": "",
                    "reason": f"declared `{stated}`, which has no single Java equivalent"}
        return {"where": where, "name": name, "type": "", "via": "",
                "reason": "no declaration in the signature, the docblock or the schema"}

    for u in units or []:
        unit = getattr(u, "name", "") or ""
        for f in getattr(u, "fields", None) or []:
            r = decide(f"{unit}.${f.get('name', '')}", f.get("type", ""),
                       "", "var", f.get("name", ""))
            (resolutions if r["type"] else unresolved).append(r)

        for m in getattr(u, "methods", None) or []:
            doc = getattr(m, "doc", "") or ""
            for p in getattr(m, "parameters", None) or []:
                r = decide(f"{unit}::{m.name}(${p.get('name', '')})", p.get("type", ""),
                           doc, "param", p.get("name", ""))
                (resolutions if r["type"] else unresolved).append(r)

            # A constructor returns nothing and saying so is not a gap.
            if m.name in ("__construct", "__destruct"):
                continue
            r = decide(f"{unit}::{m.name}()", getattr(m, "return_type", ""), doc,
                       "return", "")
            (resolutions if r["type"] else unresolved).append(r)

    return {"resolutions": resolutions, "unresolved": unresolved}


def unresolved_by_unit(result: dict) -> dict:
    """`{unit: [where, ...]}` — what triage needs to route a unit to must-review."""
    out: dict = {}
    for r in result.get("unresolved", []):
        unit = re.split(r"[.:]", r["where"], maxsplit=1)[0]
        out.setdefault(unit, []).append(r["where"])
    return out
