"""
magento_radar.py — Adobe Commerce hazards, framed against SAP Hybris. [2.10]

The Hybris radar asks "what will Salesforce refuse to do?". This asks the same question
one platform pair over, and the answers are different in kind: Salesforce fails at
*limits*, Hybris fails at *expressiveness*. PHP lets Magento do things a statically typed,
single-inheritance, Spring-wired platform simply has no construct for — and the dangerous
ones all convert into something that looks right.

Every hazard here names what Hybris would do instead, because "this is hard" is not
actionable and a migration is a sequence of decisions, not a list of worries.

Detection is regex over source and XML, deliberately. These are *hazards*: their job is to
raise a question a human answers, so a false positive costs a glance and a false negative
costs a silent behaviour change. The rules err toward raising.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.adapters.magento_config import _excluded, read_di, classify_plugins

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _sources(root: Path, pattern: str) -> list:
    return [p for p in root.rglob(pattern) if not _excluded(p, root)]


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _line(text: str, pos: int) -> int:
    return text[:pos].count("\n") + 1


def _finding(rule, severity, file, line, hazard, fix, snippet="", unit=""):
    return {"rule": rule, "severity": severity, "file": file, "line": line,
            "source_class": unit, "hazard": hazard, "fix": fix, "snippet": snippet[:120]}


# ── PHP-level rules ───────────────────────────────────────────────────────────

_PHP_RULES = [
    ("OBJECT_MANAGER", "high",
     re.compile(r"ObjectManager(?:Interface)?\s*[\$\-\>:]|ObjectManager::getInstance"),
     "Direct ObjectManager use. The dependency is invisible in the constructor, so the "
     "class does not declare what it needs and nothing static can see the edge. A "
     "migration builds its dependency graph from constructors; this one is not in it, "
     "and the ported bean will be wired without it.",
     "Inject the dependency through the constructor before migrating. On Hybris this "
     "becomes a Spring constructor argument, which is only derivable if the constructor "
     "states it."),

    ("RAW_SQL", "high",
     re.compile(r"->\s*(?:query|fetchRow|fetchAll|fetchOne|fetchCol)\s*\(\s*[\"']|"
                r"getConnection\s*\(\s*\)\s*->\s*query"),
     "Raw SQL against the Magento schema. The tables it names will not exist after "
     "migration — Hybris owns its own schema and generates it from items.xml — so this "
     "query is not portable at all, only rewritable.",
     "Re-express as a FlexibleSearch query over the migrated item types, or as a service "
     "call. Any SQL that encodes business logic in a WHERE clause needs that logic "
     "extracted first, or it moves platforms invisibly."),

    ("PHP_TRAIT", "medium",
     re.compile(r"^\s*use\s+[A-Z]\w*(?:Trait)?\s*;", re.M),
     "A trait mixes implementation into a class. Java has single inheritance and no "
     "equivalent, so whatever the trait provided has to be re-homed — as a base class if "
     "it is used once, as composition if it is used more than once.",
     "Decide per trait before converting: composition is usually right, and is always "
     "right when two classes use the same trait for different reasons."),

    ("MAGIC_DATA_ACCESS", "medium",
     re.compile(r"->\s*(?:getData|setData)\s*\(\s*['\"]"),
     "`getData('x')` returns mixed. The attribute's type is not in the code — it is in "
     "the EAV schema or the table — so a converter has nothing to infer a Java type "
     "from, and guessing produces a field that compiles and holds the wrong thing.",
     "Type must come from db_schema.xml or the EAV declaration, not from the call site. "
     "Where neither declares it, the attribute belongs in must-review rather than in a "
     "guessed field."),
]


def _php_findings(path: Path, rel: str) -> list:
    text = _read(path)
    if not text:
        return []
    unit = path.stem
    lines = text.splitlines()
    out = []
    for rule, sev, pat, hazard, fix in _PHP_RULES:
        for m in pat.finditer(text):
            ln = _line(text, m.start())
            out.append(_finding(rule, sev, rel, ln, hazard, fix,
                                lines[ln - 1].strip() if ln <= len(lines) else "", unit))
            break                      # one finding per rule per file: it is one decision
    return out


def _n_plus_one(path: Path, rel: str) -> list:
    """A query inside a foreach. The classic, and it survives migration unchanged."""
    text = _read(path)
    if not text:
        return []
    out, lines = [], text.splitlines()
    for m in re.finditer(r"foreach\s*\(", text):
        start = m.end()
        depth, end = 0, len(text)
        for i in range(start, min(len(text), start + 6000)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        body = text[start:end]
        hit = re.search(r"->\s*(?:query|fetchRow|fetchAll|fetchOne|load|getCollection)\s*\(",
                        body)
        if hit:
            ln = _line(text, start + hit.start())
            out.append(_finding(
                "QUERY_IN_LOOP", "critical", rel, ln,
                "A database call inside a foreach. Magento absorbs this on a page with "
                "three items; the same code on Hybris runs one FlexibleSearch per "
                "iteration against a JVM serving the whole catalogue, and the cost lands "
                "on every request rather than on a test.",
                "Collect the keys first, query once, and index the result — the same "
                "shape the Hybris DAO layer already expects.",
                lines[ln - 1].strip() if ln <= len(lines) else "", path.stem))
            break
    return out


def _observer_findings(path: Path, rel: str) -> list:
    """An observer that writes back into the event payload. [G3]"""
    text = _read(path)
    if "ObserverInterface" not in text:
        return []
    m = re.search(r"getEvent\s*\(\s*\)[\s\S]{0,400}?->\s*setData\s*\(", text)
    if not m:
        return []
    ln = _line(text, m.start())
    return [_finding(
        "OBSERVER_MUTATES_PAYLOAD", "high", rel, ln,
        "This observer modifies the object carried by the event. Magento dispatches "
        "observers synchronously and in order, so later observers see the change and the "
        "dispatcher sees it too. Hybris `EventService` publishes asynchronously by "
        "default and guarantees no ordering, so a literal port loses both — the mutation "
        "may land after the code that was supposed to read it, or never.",
        "Move the mutation to the code that raises the event, or make the listener "
        "synchronous explicitly and accept that it now blocks the caller. Whichever is "
        "chosen, it is a decision, not a translation.",
        "", path.stem)]


# ── XML-level rules ───────────────────────────────────────────────────────────

def _xml_findings(path: Path, rel: str) -> list:
    text = _read(path)
    out = []
    name = path.name

    if name == "system.xml" and re.search(r'showInStore="1"', text):
        out.append(_finding(
            "STORE_SCOPED_CONFIG", "medium", rel, 1,
            "Configuration scoped to store view. Magento resolves a value through "
            "website → store → store view, and code reads it without knowing which level "
            "answered. Hybris scopes configuration by BaseSite and BaseStore, which do "
            "not line up with that cascade — some values have no Hybris peer at all. [G7]",
            "Map each scoped field explicitly to BaseSite, BaseStore or a plain property, "
            "and list the ones with no equivalent rather than flattening them to a global "
            "default."))

    if "layout" in str(path.parent) and re.search(r"<(?:move|referenceBlock[^>]*remove=)", text):
        out.append(_finding(
            "LAYOUT_RUNTIME_MOVE", "medium", rel, 1,
            "Layout XML moves or removes blocks declared by other modules, resolved at "
            "runtime by reference. There is no static equivalent: the final page is not "
            "derivable from any one file, and Hybris/Spartacus composes pages from CMS "
            "components instead. [G6]",
            "Reconstruct the *resulting* page structure and rebuild it as CMS component "
            "layout. Porting the instructions rather than the outcome carries a mechanism "
            "the target does not have."))

    if name == "crontab.xml" and "<job" in text:
        out.append(_finding(
            "CLUSTER_CRON", "medium", rel, 1,
            "A Magento cron job runs once across the cluster — whichever node picks it up "
            "takes the lock. A Hybris cronjob has no such default: without explicit node "
            "affinity every node runs it, so a nightly points-expiry job would run four "
            "times on a four-node cluster. [G9]",
            "Set node affinity on the migrated cronjob, or make the work idempotent. "
            "Doing neither converts a job that ran once into one that runs per node."))
    return out


def _eav_findings(path: Path, rel: str) -> list:
    """Attributes created at runtime by a data patch. [G1]"""
    text = _read(path)
    hits = re.findall(r"addAttribute\s*\(\s*[^,]+,\s*['\"](\w+)['\"]", text)
    if not hits:
        return []
    names = sorted(set(hits))
    return [_finding(
        "EAV_DATA_PATCH", "high", rel, _line(text, text.index("addAttribute")),
        f"{len(names)} attribute(s) created at runtime — {', '.join(names[:6])}"
        f"{' and others' if len(names) > 6 else ''}. Magento EAV attributes are database "
        "rows added when the patch runs, not columns in db_schema.xml. A migration that "
        "reads only the declared schema will not know these exist, and the entity it "
        "builds will be missing exactly the fields the customer added. [G1]",
        "These become real, typed attributes in items.xml — which is the right outcome, "
        "and is also a build-time declaration where Magento had a runtime row. Every "
        "attribute must be enumerated before the type is generated; any that exist only "
        "in the customer's database, added through the admin UI, are not in the code at "
        "all and have to be exported from the live system.",
        "", path.stem)]


# ── entry point ───────────────────────────────────────────────────────────────


#: Any array literal with string keys. Which of them is *entity data* is decided below,
#: from the keys themselves rather than from how the array reaches `setData` — the array
#: is routinely built in a variable first, which is exactly the case a match on
#: `setData([...])` misses.
_ARRAY_KEY = re.compile(r"['\"](?P<key>\w+)['\"]\s*=>")


def _array_literals(text: str):
    """`(start, body)` for every bracketed block, brackets balanced.

    A regex that forbids nested brackets cannot see the array that matters: its values
    are `$args['input']['name']`, so the body contains brackets and the pattern never
    matches. The one array in a published module with a real bug was invisible for
    exactly that reason.
    """
    for i, ch in enumerate(text):
        if ch != "[":
            continue
        depth = 0
        for j in range(i, len(text)):
            if text[j] == "[":
                depth += 1
            elif text[j] == "]":
                depth -= 1
                if depth == 0:
                    body = text[i + 1:j]
                    if "=>" in body:
                        yield i + 1, body
                    break

#: How many keys must be real columns before the array is treated as entity data. Two is
#: enough to tell `['name' => …, 'email' => …, 'region' => …]` from a JSON response that
#: happens to share a word, and it is what keeps this rule quiet on everything else.
_ENTITY_ARRAY_MIN = 2


def _field_findings(path: Path, rel: str, declared: set) -> list:
    """A write to a column the schema does not declare. [1.44]

    `setData` takes any key at all. A key that is not a column is accepted, carried
    around, and dropped at the insert — no exception, no warning, and the value never
    arrives. Found in a published module on the first read: a GraphQL resolver writing
    `country_id` and `region` into a table declaring `country` and `state`, so two fields
    of every appointment booked through the API were silently lost.

    An array is only examined once at least two of its keys are real columns. Without
    that the rule fires on every associative array in the codebase — a JSON response of
    `['success' => …, 'value' => …]` looked exactly like entity data on the first attempt,
    while the array that actually had the bug was built in a variable and missed
    entirely.
    """
    if not declared:
        return []
    text = _read(path)
    if "setData" not in text:
        return []

    out, seen = [], set()
    for offset, body in _array_literals(text):
        keys = [(k.group("key"), _line(text, offset + k.start()))
                for k in _ARRAY_KEY.finditer(body)]
        known = [k for k, _ in keys if k in declared]
        if len(known) < _ENTITY_ARRAY_MIN:
            continue
        for field, line in keys:
            if field in declared or field in seen:
                continue
            seen.add(field)
            out.append(_finding(
                "UNKNOWN_ENTITY_FIELD", "high", rel, line,
                f"`{field}` is written alongside {len(known)} real column(s), so this is "
                "entity data — and no table in this module declares a column by that "
                "name. Magento accepts any key: the value is carried through the model "
                "and dropped at the insert, with no exception and no warning, so the "
                "field is simply never stored. Either it is an EAV attribute, which lives "
                "in the database and cannot be seen from the codebase, or it is a write "
                "that goes nowhere and has been going nowhere.",
                "Check it against `db_schema.xml` before migrating. Carried across as-is "
                "the target inherits a field nothing populates; corrected, it may reveal "
                "data that was never captured and has to be backfilled.",
                snippet=field))
    return out


def scan(root: str) -> dict:
    """Every Magento hazard in a codebase, framed against a Hybris target."""
    base = Path(root)
    findings: list = []

    # Every column the module declares, so a write to something else is visible. [1.44]
    declared = set()
    for f in _sources(base, "db_schema.xml"):
        declared |= set(re.findall(r'<column[^>]*\sname="(\w+)"', _read(f)))

    for p in _sources(base, "*.php"):
        rel = str(p.relative_to(base))
        findings += _php_findings(p, rel)
        findings += _n_plus_one(p, rel)
        findings += _observer_findings(p, rel)
        findings += _eav_findings(p, rel)
        findings += _field_findings(p, rel, declared)

    for p in _sources(base, "*.xml"):
        findings += _xml_findings(p, str(p.relative_to(base)))

    # di.xml is read structurally rather than by regex — an `around` plugin is only a
    # hazard once we know it can decline to proceed, and that needs both files.
    for plug in classify_plugins(root, read_di(root)["plugins"]):
        if plug["can_skip_original"] is False:
            continue
        certain = plug["can_skip_original"] is True
        findings.append(_finding(
            "AROUND_PLUGIN", "critical" if certain else "high", plug["file"], 1,
            (f"`{plug['name']}` is an `around` plugin on `{plug['on']}` that "
             + ("returns without calling $proceed on at least one path"
                if certain else "could not be read, so whether it proceeds is unknown")
             + ". Magento allows the original method to be skipped entirely. Hybris "
             "interceptors have no equivalent — they run alongside the operation, they "
             "cannot replace it — so converting this to an interceptor produces code that "
             "always calls through. The behaviour changes, everything still compiles, and "
             "nothing in review looks wrong. [G2]"),
            "Re-home as a decorator bean that wraps the target and owns the decision to "
            "delegate, registered in place of the original via a Spring bean override. "
            "That is the only Hybris construct that can decline to call through.",
            "", plug["type"].rsplit("\\", 1)[-1]))

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), f["file"], f["line"]))
    counts: dict = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    return {"findings": findings,
            "summary": {"total": len(findings), **counts,
                        "files": len({f["file"] for f in findings})}}


def headline(summary: dict) -> str:
    if not summary.get("total"):
        return "No Magento-specific migration hazards found."
    parts = [f"{summary[s]} {s}" for s in ("critical", "high", "medium", "low")
             if summary.get(s)]
    return (f"{summary['total']} migration hazard(s) across {summary['files']} file(s) — "
            + ", ".join(parts))
