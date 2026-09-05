"""What a Magento table *means*, beyond what its columns say. [1.43]

Migrating this module by hand produced a better data model than the tool did, and the gap
was not effort — it was that several facts sitting in `db_schema.xml` were never read, and
several more were inferrable and never inferred. This is those decisions, made where the
source supports them and reported where it does not.

The line between the two is the whole design here:

**Evidence** is a declaration in the source. A `<constraint xsi:type="foreign">` naming
`customer_entity` says this integer *is* a customer, and a target that emits it as an
integer has demoted a relationship to a number. That is converted.

**Inference** is a column called `customer_id` with no such constraint — the Appointment
module's, as it happens. The name is a strong hint and a hint is not a declaration:
migrating on it would be guessing at a data model, and a data model guessed wrong is
discovered late and expensively. That is *recommended*, with the evidence that is missing
named, so a person can confirm it in a minute.

Nothing here converts on a hint. Everything here reports one.
"""

from __future__ import annotations

import re

#: Magento platform tables and the Hybris type that holds the same thing. A foreign key
#: into one of these is a relationship the target already has a home for.
PLATFORM_TABLES = {
    "customer_entity": "Customer",
    "customer_group": "UserGroup",
    "store": "BaseStore",
    "store_website": "BaseSite",
    "store_group": "BaseStore",
    "sales_order": "Order",
    "sales_order_item": "AbstractOrderEntry",
    "quote": "Cart",
    "quote_item": "CartEntry",
    "catalog_product_entity": "Product",
    "catalog_category_entity": "Category",
    "directory_country": "Country",
    "directory_country_region": "Region",
    "cms_page": "ContentPage",
}

#: Columns whose *name* suggests a reference. Used only to raise a recommendation — never
#: to convert — because a name is not a declaration.
_ID_SUFFIX = re.compile(r"^(?P<base>\w+?)_id$")

#: The pieces of a postal address. Magento spreads these across a table as free text;
#: Hybris ships an `Address` type that holds them together with a validated country.
_ADDRESS_PARTS = {"address", "street", "line1", "line2", "city", "state", "region",
                  "province", "country", "country_id", "postcode", "zip", "postal_code"}

#: A column whose name says it holds one of a small closed set. Magento stores these as
#: varchar; the values live in PHP constants or in nobody's head.
_CLOSED_SET = re.compile(
    r"^(status|state|type|kind|mode|mode_of_\w+|method|channel|source|priority|"
    r"severity|direction|currency|language|locale)$")

_TEXTY = {"varchar", "text", "mediumtext", "longtext", "char"}


def _attrs(data_type) -> list:
    d = data_type.to_dict() if hasattr(data_type, "to_dict") else dict(data_type or {})
    return [a for a in (d.get("attributes") or d.get("fields") or []) if isinstance(a, dict)]


def _code(data_type) -> str:
    d = data_type.to_dict() if hasattr(data_type, "to_dict") else dict(data_type or {})
    return d.get("code") or d.get("name") or ""


def _hybris_type_for(table: str, declared: dict) -> str:
    """The Hybris type a foreign key's target becomes."""
    if table in PLATFORM_TABLES:
        return PLATFORM_TABLES[table]
    return declared.get(table, "")


def decide(data_model) -> list[dict]:
    """Every modelling call this source supports, and every one it only hints at.

    Each row: `{kind, table, column, becomes, confidence, why, action}`. `confidence` is
    `declared` or `inferred`, and only `declared` is ever acted on automatically.
    """
    types = list(getattr(data_model, "types", None) or [])
    declared = {}
    for t in types:
        code = _code(t)
        if code:
            declared[code] = "".join(p.capitalize() for p in re.split(r"[_\-]", code) if p)

    out: list[dict] = []
    for t in types:
        table = _code(t)
        attrs = _attrs(t)
        names = {a.get("name", "") for a in attrs}

        for a in attrs:
            name = a.get("name", "")
            ref = a.get("references") or {}

            if ref.get("table"):
                becomes = _hybris_type_for(ref["table"], declared)
                if becomes:
                    out.append({
                        "kind": "reference", "table": table, "column": name,
                        "becomes": becomes, "confidence": "declared",
                        "why": (f"`{name}` has a declared foreign key to "
                                f"`{ref['table']}`, so it is a relationship and not a "
                                f"number. On the target that is a `{becomes}` reference, "
                                "which the platform can join, validate and cascade — "
                                "none of which an integer column can do."),
                        "action": "converted",
                    })
                    continue
                out.append({
                    "kind": "reference_unmapped", "table": table, "column": name,
                    "becomes": "", "confidence": "declared",
                    "why": (f"`{name}` references `{ref['table']}`, which is neither a "
                            "table this module declares nor a platform table with a known "
                            "counterpart. It is a real relationship to something outside "
                            "this migration's reach."),
                    "action": "reported",
                })
                continue

            m = _ID_SUFFIX.match(name)
            # A table's own key is not a reference to anything. `entity_id` matches the
            # `*_id` shape exactly and pointing that out would be noise in every row.
            own_key = a.get("identity") or a.get("primary") or name in ("entity_id", "id")
            if m and not own_key and a.get("raw_type") in ("int", "bigint", "smallint"):
                base = m.group("base")
                guess = _hybris_type_for(f"{base}_entity", declared) or \
                    _hybris_type_for(base, declared) or declared.get(base, "")
                out.append({
                    "kind": "reference_suspected", "table": table, "column": name,
                    "becomes": guess, "confidence": "inferred",
                    "why": (f"`{name}` is an integer whose name says it points at "
                            f"{'`' + guess + '`' if guess else 'another entity'}, and no "
                            "foreign key declares it. A name is a hint and a hint is not "
                            "a declaration — migrating on it would guess at a data model, "
                            "and a data model guessed wrong is found late. Add the "
                            "constraint in the source, or confirm the target type here."),
                    "action": "reported",
                })

            if (_CLOSED_SET.match(name) and a.get("raw_type") in _TEXTY):
                out.append({
                    "kind": "enum_candidate", "table": table, "column": name,
                    "becomes": "", "confidence": "inferred",
                    "why": (f"`{name}` is free text holding what is almost certainly a "
                            "closed set. Magento enforces the set in PHP, so the database "
                            "accepts a typo and the row is then invisible to every filter "
                            "on that column. Declared as an enum on the target, the "
                            "platform rejects it — but the *values* are not in the "
                            "codebase, so they have to come from the live data."),
                    "action": "reported",
                })

        parts = names & _ADDRESS_PARTS
        if len(parts) >= 3:
            out.append({
                "kind": "address_cluster", "table": table,
                "column": ", ".join(sorted(parts)), "becomes": "Address",
                "confidence": "inferred",
                "why": (f"`{table}` spreads a postal address across {len(parts)} free-text "
                        "columns. The target ships an `Address` type holding the same "
                        "fields with a validated country reference, so the data becomes "
                        "joinable instead of typed twice. Merging columns changes the "
                        "shape of every row, which is a migration decision rather than a "
                        "translation — so it is proposed, not applied."),
                "action": "reported",
            })

        surrogate = [a for a in attrs if a.get("name") in ("entity_id", "id")]
        business = [a for a in attrs if a.get("unique") and a.get("name") not in
                    ("entity_id", "id")]
        if surrogate and not business:
            out.append({
                "kind": "no_business_key", "table": table, "column": "", "becomes": "",
                "confidence": "declared",
                "why": (f"`{table}` is identified only by an auto-increment column. That "
                        "is enough for the database and not enough for anything else: "
                        "there is no value a customer can quote, no key an integration "
                        "can use, and no way to make a data load idempotent — a re-run "
                        "inserts everything again. Add a business key before migrating "
                        "data."),
                "action": "reported",
            })

    return out


def converted(rows: list) -> dict:
    """`{(table, column): hybris type}` for the decisions that are acted on."""
    return {(r["table"], r["column"]): r["becomes"]
            for r in rows or [] if r.get("action") == "converted" and r.get("becomes")}


def grounding_for(rows: list) -> str:
    """What the Builder should know about this data model. [1.43]"""
    rows = [r for r in rows or [] if r.get("action") == "reported"]
    if not rows:
        return ""
    out = ["## The data model — decisions the source does not settle", "",
           "Each of these is a modelling call a person owes. Do not resolve one by "
           "guessing in generated code; where a value or a type is unknown, say so in the "
           "code rather than inventing one.", ""]
    for r in rows[:12]:
        where = f"`{r['table']}`" + (f".`{r['column']}`" if r["column"] else "")
        out.append(f"- **{r['kind'].replace('_', ' ')}** — {where}. {r['why']}")
    return "\n".join(out)
