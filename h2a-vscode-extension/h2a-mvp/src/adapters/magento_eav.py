"""
magento_eav.py — attributes that exist as rows, not as columns. [2.8, G1]

The single largest structural difference between the two platforms. A Magento EAV
attribute is a **database row created when a data patch runs**; a Hybris attribute is a
**declaration in items.xml, resolved at build time**. Reading one and writing the other is
not a translation, it is a change of kind — and the part that makes it dangerous is that
the source of truth moves out of the code.

Three populations, and only the first is in the repository at all:

  declared in a patch   `$setup->addAttribute(...)` — read here, precisely, from the AST
  declared by a module  a third-party extension's own patches, present only if that
                        module's source is in scope
  added by a person     created through the admin UI on the live system. **In no file.**
                        Not readable by any static tool, at any level of effort.

So this module reports what it found *and* states plainly that the set is open. A schema
that silently presents the first population as the whole entity is the failure mode: the
migration looks complete, the customer's own custom fields are missing, and nothing in the
output says a word about it.
"""

from __future__ import annotations

from pathlib import Path

from src import ir

#: Magento's EAV backend types → the neutral types the IR carries elsewhere.
_EAV_TYPES = {
    "varchar": "String", "text": "String", "static": "String",
    "int": "Integer", "decimal": "BigDecimal", "datetime": "DateTime",
}

#: `Customer::ENTITY` is the constant; `customer` is the entity it names. Only the
#: entities whose constant is unambiguous are mapped — anything else keeps the raw text,
#: because a wrong entity attaches a customer's field to the wrong object.
_ENTITY_CONSTANTS = {
    "Customer::ENTITY": "customer",
    "Product::ENTITY": "catalog_product",
    "Category::ENTITY": "catalog_category",
    "Address::ENTITY": "customer_address",
    "AbstractAddress::ENTITY": "customer_address",
}


def _txt(node) -> str:
    return node.text.decode("utf-8", "replace") if node is not None else ""


def _walk(node, wanted, out):
    if node.type == wanted:
        out.append(node)
    for c in node.children:
        _walk(c, wanted, out)
    return out


def _literal(node):
    """A PHP literal as a Python value, or None when it is not a literal."""
    if node is None:
        return None
    if node.type in ("string", "encapsed_string"):
        return _txt(node)[1:-1]
    if node.type == "integer":
        return int(_txt(node))
    if node.type == "float":
        return float(_txt(node))
    if node.type == "boolean":
        return _txt(node).lower() == "true"
    if node.type == "null":
        return None
    return None


def _options(array_node) -> dict:
    """The `['type' => 'varchar', ...]` argument, as far as it is literal."""
    out = {}
    if array_node is None or array_node.type != "array_creation_expression":
        return out
    for el in _walk(array_node, "array_element_initializer", []):
        parts = [c for c in el.children if c.is_named]
        if len(parts) != 2:
            continue
        key = _literal(parts[0])
        if not isinstance(key, str):
            continue
        val = _literal(parts[1])
        # A non-literal value (a ::class reference, a variable) is recorded as its source
        # text rather than dropped — `source` pointing at an options class is exactly the
        # thing that tells a reviewer this attribute is a picklist.
        out[key] = val if val is not None or parts[1].type == "null" else _txt(parts[1])
    return out


def _args(call):
    args = next((c for c in call.children if c.type == "arguments"), None)
    if args is None:
        return []
    out = []
    for a in (c for c in args.children if c.type == "argument"):
        inner = next((c for c in a.children if c.is_named), None)
        out.append(inner if inner is not None else a)
    return out


def read_attributes(root: str) -> list:
    """Every EAV attribute declared by a data patch in this codebase.

    Each row: {entity, code, type, required, label, input, source, file, line}.
    """
    from src.adapters.magento_config import _excluded
    from src.adapters.php_reader import _parser

    base = Path(root)
    found = []
    for path in sorted(base.rglob("*.php")):
        if _excluded(path, base):
            continue
        try:
            src = path.read_bytes()
        except OSError:
            continue
        if b"addAttribute" not in src:
            continue
        try:
            tree = _parser().parse(src)
        except Exception:
            continue

        rel = str(path.relative_to(base))
        for call in _walk(tree.root_node, "member_call_expression", []):
            names = [c for c in call.children if c.type == "name"]
            if not names or _txt(names[-1]) != "addAttribute":
                continue
            args = _args(call)
            if len(args) < 2:
                continue

            entity_raw = _txt(args[0])
            code = _literal(args[1])
            if not isinstance(code, str):
                # An attribute code built at runtime cannot be read. Recorded as a gap
                # rather than skipped, because "we saw an addAttribute we could not read"
                # is a materially different statement from "there are none".
                found.append({"entity": _ENTITY_CONSTANTS.get(entity_raw, entity_raw),
                              "code": "", "type": "", "required": False,
                              "unreadable": f"attribute code is not a literal: {entity_raw}",
                              "file": rel, "line": call.start_point[0] + 1})
                continue

            opts = _options(args[2]) if len(args) > 2 else {}
            found.append({
                "entity": _ENTITY_CONSTANTS.get(entity_raw, entity_raw),
                "code": code,
                "type": _EAV_TYPES.get(str(opts.get("type", "")), "String"),
                "raw_type": opts.get("type", ""),
                "required": bool(opts.get("required", False)),
                "label": opts.get("label", ""),
                "input": opts.get("input", ""),
                "source": opts.get("source", ""),
                "unreadable": "",
                "file": rel,
                "line": call.start_point[0] + 1,
            })
    return found


def as_data_types(attributes: list) -> list:
    """Group attributes into one `ir.DataType` per entity they extend.

    These are *extensions of entities Magento already owns* — `customer`,
    `catalog_product` — not new tables. The distinction survives into the IR because on
    Hybris they become attributes added to an existing item type, and treating them as a
    new type would produce a parallel object holding half a customer.
    """
    by_entity: dict = {}
    for a in attributes:
        by_entity.setdefault(a["entity"], []).append(a)

    out = []
    for entity, attrs in sorted(by_entity.items()):
        readable = [a for a in attrs if a["code"]]
        unreadable = [a for a in attrs if not a["code"]]
        note = (
            f"EAV. {len(readable)} attribute(s) are declared by a data patch in this "
            "codebase and were read. The set is open: a third-party module's patches are "
            "only visible if that module's source is in scope, and attributes created "
            "through the admin UI exist as database rows in no file at all — they cannot "
            "be read statically at any level of effort, and must be exported from the "
            "live system before this entity is complete."
        )
        if unreadable:
            note += (f" {len(unreadable)} addAttribute call(s) build their code at "
                     "runtime and could not be read.")
        out.append(ir.DataType(
            code=entity,
            extends=entity,          # it extends an entity Magento already owns
            attributes=[{"name": a["code"], "type": a["type"], "raw_type": a["raw_type"],
                         "required": a["required"], "unique": False, "default": "",
                         "comment": a["label"] or "",
                         "picklist_source": a["source"] or ""}
                        for a in readable],
            deployment="eav",
            undeclared_note=note,
        ))
    return out
