"""
hybris_flexsearch.py — what a FlexibleSearch query can and cannot become. [1.23]

FlexibleSearch is SQL. SOQL is not. The overlap is wide enough that a model asked to
"convert this query" will confidently produce SOQL-shaped text for cases SOQL cannot
express — and the result either fails to compile, or compiles against the wrong
relationship and quietly returns different rows.

So the query is parsed here, mechanically, and answered honestly:

    direct   — one type, no subquery, no leading wildcard. The SOQL is *derived*, not
               guessed, and included so a reviewer can check it against the original.
    blocked  — SOQL has no construct for this. Naming the reason is worth more than an
               attempt, because an attempt looks like an answer.

Parsing is deliberately shallow. This decides *translatability*, and a query that trips
any blocking construct is blocked whatever the rest of it says — so there is nothing to
gain from understanding the rest more deeply, and a lot to lose from claiming to.
"""

from __future__ import annotations

import re

# {alias:attribute} — how FlexibleSearch names a column.
_FIELD = re.compile(r"\{(?:(\w+):)?(\w+)\}")
# {Type AS alias} — how it names a table.
_TYPE = re.compile(r"\{(\w+)(?:\s+AS\s+(\w+))?\}", re.IGNORECASE)

# Hybris system attributes with a Salesforce standard-field equivalent. Everything else
# is a custom attribute and gets the usual __c treatment.
_SYSTEM_FIELDS = {
    "pk": "Id",
    "creationtime": "CreatedDate",
    "modifiedtime": "LastModifiedDate",
    "code": "Code__c",          # conventional, but still a custom field
}

_SELECT_RE = re.compile(r"\bSELECT\b(.*?)\bFROM\b", re.IGNORECASE | re.DOTALL)
_FROM_RE = re.compile(r"\bFROM\b(.*?)(?:\bWHERE\b|\bORDER\s+BY\b|\bGROUP\s+BY\b|$)",
                      re.IGNORECASE | re.DOTALL)
_WHERE_RE = re.compile(r"\bWHERE\b(.*?)(?:\bORDER\s+BY\b|\bGROUP\s+BY\b|$)",
                       re.IGNORECASE | re.DOTALL)
_ORDER_RE = re.compile(r"\bORDER\s+BY\b(.*?)$", re.IGNORECASE | re.DOTALL)

# A Java string literal that looks like a FlexibleSearch query.
_QUERY_LITERAL = re.compile(r'"((?:[^"\\]|\\.)*\bFROM\b(?:[^"\\]|\\.)*)"', re.IGNORECASE)


def looks_like_query(text: str) -> bool:
    return bool(re.search(r"\bSELECT\b", text, re.I) and re.search(r"\bFROM\b", text, re.I))


def find_queries(source: str) -> list[tuple[int, str]]:
    """Every FlexibleSearch query literal in a Java file, with its line number.

    Java concatenates long queries across lines, so a literal that has FROM but no SELECT
    is a fragment of one — reported at its own line rather than stitched, because guessing
    how fragments join is how a analyser starts inventing queries.
    """
    out = []
    for m in _QUERY_LITERAL.finditer(source):
        q = m.group(1)
        if looks_like_query(q):
            out.append((source[:m.start()].count("\n") + 1, q))
    return out


def _types_in(from_clause: str) -> list[str]:
    return [m.group(1) for m in _TYPE.finditer(from_clause)]


def _sf_field(attr: str) -> str:
    key = attr.lower()
    if key in _SYSTEM_FIELDS:
        return _SYSTEM_FIELDS[key]
    return f"{attr[:1].upper()}{attr[1:]}__c"


def analyse(query: str) -> dict:
    """Classify one FlexibleSearch query, and derive its SOQL when there is one.

    Returns {verdict, reasons, soql, types}. `verdict` is "direct" or "blocked";
    `reasons` names every construct that blocks it, because fixing one and rediscovering
    the next is a bad way to spend a migration.
    """
    reasons: list[dict] = []

    from_m = _FROM_RE.search(query)
    from_clause = from_m.group(1) if from_m else ""
    types = _types_in(from_clause)

    # C1 — SOQL has no JOIN. Relationship traversal reaches one level down and five up,
    # and only along a relationship that exists; nothing else joins two objects.
    if re.search(r"\bJOIN\b", from_clause, re.I) or len(types) > 1:
        reasons.append({
            "code": "FS_JOIN",
            "detail": f"joins {len(types) or 2} types ({', '.join(types) or 'unknown'}). "
                      "SOQL has no JOIN: it can traverse a relationship that already "
                      "exists (one level down, five up) and nothing else.",
            "fix": "Either traverse the relationship if one exists between these objects, "
                   "or run two queries and join in Apex — bulkified, with the second "
                   "query taking the ids from the first.",
        })

    # C4 — FlexibleSearch nests subqueries freely; SOQL semi-joins go one level and
    # cannot be nested inside each other.
    if "{{" in query or re.search(r"\bIN\s*\(\s*SELECT\b", query, re.I):
        reasons.append({
            "code": "FS_SUBQUERY",
            "detail": "contains a subquery. SOQL semi-joins are one level deep, cannot "
                      "nest, and cannot be combined with OR.",
            "fix": "Run the inner query first and pass its ids into the outer one, "
                   "watching the 2,000-id ceiling on an IN list.",
        })

    # C2 — a leading wildcard cannot use an index.
    if re.search(r"LIKE\s+'%", query, re.I) or re.search(r'LIKE\s+"%', query, re.I):
        reasons.append({
            "code": "FS_LEADING_WILDCARD",
            "detail": "matches with a leading wildcard. SOQL cannot use an index for "
                      "that, so it degrades badly and is rejected outright in some "
                      "contexts.",
            "fix": "Use SOSL for genuine text search — but note SOSL returns a different "
                   "shape and does not honour the same ordering guarantees.",
        })

    if reasons:
        return {"verdict": "blocked", "reasons": reasons, "soql": None, "types": types}

    return {"verdict": "direct", "reasons": [], "soql": _to_soql(query, types), "types": types}


def _to_soql(query: str, types: list[str]) -> str | None:
    """Derive SOQL for the single-type case. Mechanical, never inferred."""
    if len(types) != 1:
        return None
    obj = f"{types[0]}__c"

    sel = _SELECT_RE.search(query)
    fields = [_sf_field(m.group(2)) for m in _FIELD.finditer(sel.group(1))] if sel else []
    select = ", ".join(dict.fromkeys(fields)) or "Id"

    parts = [f"SELECT {select}", f"FROM {obj}"]

    where = _WHERE_RE.search(query)
    if where:
        w = _FIELD.sub(lambda m: _sf_field(m.group(2)), where.group(1).strip())
        w = re.sub(r"\?(\w+)", r":\1", w)          # ?code -> :code (Apex bind)
        parts.append(f"WHERE {w}")

    order = _ORDER_RE.search(query)
    if order:
        o = _FIELD.sub(lambda m: _sf_field(m.group(2)), order.group(1).strip())
        parts.append(f"ORDER BY {o}")

    return " ".join(" ".join(parts).split())
