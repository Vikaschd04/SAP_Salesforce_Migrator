"""
magento_config.py — Magento's XML wiring, read into the IR. [2.4–2.7]

Magento keeps in XML what Hybris keeps in Spring and items.xml: what is substituted for
what, what listens to what, what runs on a schedule, and what tables exist. None of it
needs a PHP parser, and all of it decides how the PHP is *reached* — which is the part a
migration loses first, exactly as a Hybris lifecycle hook loses its invocation.

Four readers, one rule between them: **what cannot be expressed on the target is flagged,
never faked.** The sharpest case is the `around` plugin. Magento lets it decline to call
`$proceed`, so the original method never runs; Hybris interceptors have no equivalent, and
a converter that maps `around` onto an interceptor produces code that always calls
through. That is a silent behaviour change in the one construct most likely to be carrying
a business decision, so it is recorded as `can_skip_original` and reported.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from src import ir

# Magento's `around` methods are named aroundXxx; that prefix is the whole signal.
_AROUND = re.compile(r"^around[A-Z]")


def _parse(path: Path):
    try:
        return ET.parse(path).getroot()
    except Exception:
        return None


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


#: Directories that belong to the framework or the runtime, not the customer. Matched
#: against the path *relative to the project root* — matching absolute parts would hide a
#: project stored under `/var/www/magento`, which is where most of them actually live.
EXCLUDED_DIRS = {"vendor", "generated", "node_modules", "var", "pub"}


def _excluded(path, root) -> bool:
    try:
        rel_parts = path.relative_to(root).parts
    except ValueError:
        rel_parts = path.parts
    return bool(EXCLUDED_DIRS & set(rel_parts[:-1]))


def _files(root: Path, name: str) -> list:
    """Config files belonging to the customer, not to the framework."""
    return [p for p in root.rglob(name) if not _excluded(p, root)]


def _php_of(cls: str) -> str:
    """`Acme\\Loyalty\\Plugin\\X` → the path fragment its file would end with."""
    return cls.replace("\\", "/") + ".php"


# ── 2.4 · di.xml ──────────────────────────────────────────────────────────────

def read_di(root: str) -> dict:
    """Preferences, plugins and constructor arguments.

    A *preference* is closer to bytecode weaving than to a Spring bean override: it
    substitutes a type globally, for every injection point, including ones in code the
    customer never wrote. It is recorded as a fact about the estate rather than resolved,
    because resolving it means deciding what a third-party module meant.
    """
    base = Path(root)
    preferences, plugins, arguments = [], [], []

    for f in _files(base, "di.xml"):
        node = _parse(f)
        if node is None:
            continue
        rel = _rel(f, base)
        area = f.parent.name if f.parent.name in ("frontend", "adminhtml", "webapi_rest",
                                                  "graphql", "crontab") else "global"

        for pref in node.iter("preference"):
            preferences.append({"for": pref.get("for", ""), "type": pref.get("type", ""),
                                "area": area, "file": rel})

        for typ in node.iter("type"):
            target = typ.get("name", "")
            for plug in typ.findall("plugin"):
                cls = plug.get("type", "")
                plugins.append({
                    "name": plug.get("name", ""), "on": target, "type": cls,
                    "sort_order": int(plug.get("sortOrder") or 0),
                    "disabled": str(plug.get("disabled", "")).lower() == "true",
                    "area": area, "file": rel,
                    # Filled in by `classify_plugins` once the PHP is readable; declared
                    # here so the shape does not change when 2.3 lands.
                    "methods": [], "can_skip_original": None,
                })
            for arg in typ.findall("./arguments/argument"):
                arguments.append({"on": target, "name": arg.get("name", ""),
                                  "kind": arg.get("{http://www.w3.org/2001/XMLSchema-instance}type",
                                                  arg.get("type", "")),
                                  "value": (arg.text or "").strip(), "file": rel})

    return {"preferences": preferences, "plugins": plugins, "arguments": arguments}


def classify_plugins(root: str, plugins: list) -> list:
    """Mark which plugins are `around`, and which can skip the original. [G2]

    Reads only the method names and whether `$proceed` is reachable without being called —
    deliberately shallow, and shallow is enough: the question is not what the plugin does,
    it is whether Hybris can express it at all. It cannot express *any* around plugin that
    declines to proceed, so a conservative answer is the correct one.
    """
    base = Path(root)
    for p in plugins:
        path = next((f for f in _files(base, "*.php") if str(f).endswith(_php_of(p["type"]))),
                    None)
        if path is None:
            p["methods"], p["can_skip_original"] = [], None
            continue
        src = path.read_text(encoding="utf-8", errors="replace")
        methods = re.findall(r"function\s+(\w+)\s*\(", src)
        p["methods"] = methods
        arounds = [m for m in methods if _AROUND.match(m)]
        p["around_methods"] = arounds
        if not arounds:
            p["can_skip_original"] = False
            continue
        # A `return` inside an around method that is not `return $proceed(...)` means the
        # original can be bypassed. Conservative: if we cannot tell, we say we cannot.
        body = src
        returns = re.findall(r"return\s+([^;]*);", body)
        p["can_skip_original"] = any("$proceed" not in r for r in returns)
    return plugins


# ── 2.5 · events.xml ──────────────────────────────────────────────────────────

def read_events(root: str) -> list:
    """Observers, with the event each listens to.

    Magento dispatches these synchronously and hands the observer a payload it may
    modify in place, which later observers on the same event then see. Hybris `EventService`
    is asynchronous by default and does not promise ordering, so both facts travel with
    the observer rather than being rediscovered at generation time.
    """
    base = Path(root)
    out = []
    for f in _files(base, "events.xml"):
        node = _parse(f)
        if node is None:
            continue
        rel = _rel(f, base)
        area = f.parent.name if f.parent.name != "etc" else "global"
        for ev in node.iter("event"):
            for obs in ev.findall("observer"):
                out.append({
                    "event": ev.get("name", ""),
                    "name": obs.get("name", ""),
                    "instance": obs.get("instance", ""),
                    "disabled": str(obs.get("disabled", "")).lower() == "true",
                    "shared": str(obs.get("shared", "")).lower() != "false",
                    "area": area, "file": rel,
                    "synchronous": True,        # always, in Magento
                })
    return out


# ── 2.6 · crontab.xml ─────────────────────────────────────────────────────────

def read_crontab(root: str) -> list:
    """Scheduled jobs as `ir.ScheduledJob`.

    Magento runs a job once across a cluster; Hybris cronjobs need explicit node affinity
    or every node runs it. The group is carried because that is where the difference will
    have to be reconciled. [G9]
    """
    base = Path(root)
    jobs = []
    for f in _files(base, "crontab.xml"):
        node = _parse(f)
        if node is None:
            continue
        rel = _rel(f, base)
        for group in node.iter("group"):
            gid = group.get("id", "default")
            for job in group.findall("job"):
                sched = job.findtext("schedule", "").strip()
                jobs.append(ir.ScheduledJob(
                    name=job.get("name", ""),
                    cron=sched or f"config:{job.findtext('config_path', '').strip()}",
                    implemented_by=f"{job.get('instance', '')}::{job.get('method', 'execute')}",
                    file=f"{rel}#{gid}",
                ))
    return jobs


# ── 2.7 · db_schema.xml ───────────────────────────────────────────────────────

_SCHEMA_TYPES = {
    "int": "Integer", "smallint": "Integer", "bigint": "Long", "tinyint": "Integer",
    "decimal": "BigDecimal", "float": "Double", "double": "Double",
    "varchar": "String", "text": "String", "mediumtext": "String", "longtext": "String",
    "boolean": "Boolean", "date": "Date", "datetime": "DateTime", "timestamp": "DateTime",
    "blob": "Binary", "varbinary": "Binary", "json": "String",
}


def read_db_schema(root: str) -> list:
    """Declared tables as `ir.DataType`.

    This is only the *declared* half of a Magento data model. EAV attributes are rows
    created at runtime by data patches and live in the database, so a table read alone
    understates the model — every entity therefore carries `undeclared_note` saying so,
    rather than presenting a partial schema as a complete one. [G1, 2.8]
    """
    base = Path(root)
    types = []
    for f in _files(base, "db_schema.xml"):
        node = _parse(f)
        if node is None:
            continue
        for table in node.iter("table"):
            attrs = []
            for col in table.findall("column"):
                xsi = col.get("{http://www.w3.org/2001/XMLSchema-instance}type", "")
                attrs.append({
                    "name": col.get("name", ""),
                    "type": _SCHEMA_TYPES.get(xsi, "String"),
                    "raw_type": xsi,
                    "required": str(col.get("nullable", "true")).lower() == "false",
                    "unique": False,
                    "default": col.get("default", ""),
                    "comment": col.get("comment", ""),
                    # The table's own key. Without it, `entity_id` looks exactly like a
                    # foreign key by name and gets reported as a suspected reference to
                    # an `entity` table that does not exist. [1.43]
                    "identity": str(col.get("identity", "")).lower() == "true",
                    "primary": str(col.get("primary", "")).lower() == "true",
                })
            by_name = {a["name"]: a for a in attrs}
            for c in table.findall("constraint"):
                kind = c.get("{http://www.w3.org/2001/XMLSchema-instance}type", "")
                if kind == "primary":
                    for col in c.findall("column"):
                        if col.get("name") in by_name:
                            by_name[col.get("name")]["primary"] = True
                elif kind == "unique":
                    for col in c.findall("column"):
                        if col.get("name") in by_name:
                            by_name[col.get("name")]["unique"] = True
                elif kind == "foreign":
                    # What this column *points at*. Read past until now, so a
                    # `customer_id` integer arrived downstream as an integer and the
                    # target got a number where the source had a relationship. The
                    # declaration is right here in the file — the same oversight as
                    # `partof` in 1.32, one platform over. [1.43]
                    col = c.get("column", "")
                    if col in by_name:
                        by_name[col]["references"] = {
                            "table": c.get("referenceTable", ""),
                            "column": c.get("referenceColumn", ""),
                            "on_delete": c.get("onDelete", ""),
                        }

            types.append(ir.DataType(
                code=table.get("name", ""),
                attributes=attrs,
                deployment=table.get("resource", "default"),
                undeclared_note=(
                    "Declared columns only. Magento EAV attributes are created at runtime "
                    "by data patches and stored in the database, so this table is not the "
                    "whole entity — see the EAV report (item 2.8)."),
            ))
    return types


def read_routes(root: str) -> dict:
    """Front names declared in `etc/*/routes.xml`, by area. [1.53]

    A Magento controller's URL is not in the controller. It is assembled from three
    things: the `frontName` declared here, the directory the class sits in, and the class
    name — `Controller/Index/Create.php` under `frontName="appointment"` answers
    `/appointment/index/create`. The adapter read every other `etc/` file and skipped this
    one, so every controller arrived as a class with an `execute()` method and no hint
    that it was an entry point at all. They were emitted as Spring services: correct Java,
    and a Hybris developer opening one would have no way to know a URL used to reach it.

    Returns `{area: {route_id: front_name}}` — `frontend` and `adminhtml` kept apart,
    because an admin route is reached through a different mechanism on the target and
    merging them would lose exactly the distinction that decides which.
    """
    base = Path(root)
    out: dict = {}
    for path in _files(base, "routes.xml"):
        # `etc/frontend/routes.xml` → frontend; `etc/adminhtml/routes.xml` → adminhtml;
        # `etc/routes.xml` → whichever the router says, defaulting to frontend.
        area = path.parent.name if path.parent.name != "etc" else ""
        tree = _parse(path)
        if tree is None:
            continue
        for router in tree.iter("router"):
            rid = router.get("id", "")
            resolved = area or ("adminhtml" if rid == "admin" else "frontend")
            for route in router.iter("route"):
                front = route.get("frontName") or route.get("id") or ""
                if front:
                    out.setdefault(resolved, {})[route.get("id", front)] = front
    return out


def route_for(rel_path: str, routes: dict) -> dict:
    """The URL a controller answers, from its path. `{}` when it is not a controller.

    Magento's convention *is* the routing table: the directory under `Controller/` is the
    path segment and the class name is the action, with `Index` meaning "no segment" in
    both positions. `Controller/Adminhtml/...` is the admin area and reaches a different
    subsystem on the target, so it is reported separately rather than folded in.
    """
    parts = [p for p in rel_path.replace("\\", "/").split("/") if p]
    if "Controller" not in parts:
        return {}
    tail = parts[parts.index("Controller") + 1:]
    if not tail:
        return {}
    area = "frontend"
    if tail and tail[0] == "Adminhtml":
        area, tail = "adminhtml", tail[1:]
    if not tail:
        return {}

    action = tail[-1].removesuffix(".php")
    segments = [s.lower() for s in tail[:-1]] or ["index"]
    front = next(iter((routes or {}).get(area, {}).values()), "")

    # `Index` is Magento's default at both levels, so `Index/Index.php` is the bare route.
    path_parts = [p for p in segments if p != "index"] + \
                 ([action.lower()] if action.lower() != "index" else [])
    return {"area": area, "front_name": front, "action": action,
            "path": "/".join([front, *path_parts]) if front else "/".join(path_parts)}
