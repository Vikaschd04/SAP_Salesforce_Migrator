"""
radar.py — Hybris patterns that become hazards on Salesforce.

Generic Apex linting is commoditised and runs after the fact, on code that has already
been generated. This runs *before*, on the customer's own Java, and reports the things
that are perfectly reasonable in Hybris and dangerous in Apex. That asymmetry is the
whole point: a FlexibleSearch inside a loop is ordinary Hybris and a governor-limit
breach the moment it becomes SOQL.

It is deliberately deterministic — no model calls, no org, no credentials — so it runs on
a locked-down laptop and costs nothing. It is also the material a reviewer needs *at the
Discovery gate*, before approving a plan, rather than discovering the same hazards in
generated code three stages later.

**On false positives.** A radar that cries wolf is one people switch off in a week, so
every rule here is anchored to something structural rather than to a hopeful substring.
"In a loop" is decided by tracking brace depth, not by looking for a nearby `for`.
Comments and string literals are stripped first, so a rule name mentioned in a Javadoc
never fires. Where a rule cannot be certain it says so in its own wording.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.textio import read_text_or_empty

# Severity is about consequence on Salesforce, not about how odd the Java looks.
#   critical — will fail at runtime under realistic volume
#   high     — silently changes behaviour, or has no equivalent at all
#   medium   — works, but will need a deliberate design decision
#   info     — worth knowing during review
_ORDER = {"critical": 0, "high": 1, "medium": 2, "info": 3}


def _strip_xml(text: str) -> str:
    """XML comments only.

    The Java stripper also removes string literals, and in XML every meaningful value
    lives inside quotes — `scope="session"`, `class="...InterceptorMapping"`. Running it
    over Spring config erased exactly the text the rules look for, so both XML rules
    silently found nothing.
    """
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith("<!--", i):
            j = text.find("-->", i + 4)
            block = text[i:j] if j > 0 else text[i:]
            out.append("\n" * block.count("\n"))
            i = n if j < 0 else j + 3
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _strip(text: str) -> str:
    """Remove comments and string literals, preserving line numbering.

    Without this, a Javadoc that says "do not run FlexibleSearch in a loop" would be
    reported as running FlexibleSearch in a loop — which is exactly the sort of thing
    that teaches people to ignore the tool.
    """
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif c == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            block = text[i:j] if j > 0 else text[i:]
            out.append("\n" * block.count("\n"))       # keep the lines
            i = n if j < 0 else j + 2
        elif c in "\"'":
            quote, j = c, i + 1
            while j < n and text[j] != quote:
                j += 2 if text[j] == "\\" else 1
            out.append('""')
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _loop_lines(text: str) -> set[int]:
    """1-indexed lines that execute inside a `for`/`while` body.

    Brace-depth tracking rather than proximity: a method containing a loop earlier on
    does not make everything after it loop-borne, and a nested helper called from inside
    a loop is not itself in one.
    """
    lines = text.splitlines()
    inside: set[int] = set()
    depth, loop_depths, pending, brace_seen = 0, [], False, True

    for idx, raw in enumerate(lines, start=1):
        if loop_depths:
            inside.add(idx)
        # `for (...) svc.call();` has no braces at all — the body is on the header line.
        header = re.search(r"\b(for|while)\s*\(", raw)
        if header and not re.search(r"\bdo\s*\{", raw):
            after = raw[header.end():]
            if "{" not in after and after.rstrip().endswith(";"):
                inside.add(idx)
            else:
                pending = True

        for ch in raw:
            if ch == "{":
                depth += 1
                if pending:
                    loop_depths.append(depth)
                    pending = False
            elif ch == "}":
                if loop_depths and loop_depths[-1] == depth:
                    loop_depths.pop()
                depth = max(0, depth - 1)
    return inside


# ── rules ─────────────────────────────────────────────────────────────────────
# (id, severity, what to look for, whether it must be inside a loop, hazard, fix)

_QUERY = re.compile(r"\b(flexibleSearchService\s*\.\s*(search|searchUnique)|new\s+FlexibleSearchQuery)\b")
_DML = re.compile(r"\bmodelService\s*\.\s*(save|saveAll|remove|removeAll)\s*\(")
_DAO_CALL = re.compile(r"\b\w*(Dao|Service)\s*\.\s*(find|get|load|search)\w*\s*\(")

_LINE_RULES = [
    ("SOQL_IN_LOOP", "critical", _QUERY, True,
     "A FlexibleSearch inside a loop becomes SOQL inside a loop, which breaches the "
     "100-query governor limit as soon as the collection is realistic.",
     "Hoist the query out of the loop and bulkify: query once for every key, build a Map, "
     "then iterate the Map."),
    ("DML_IN_LOOP", "critical", _DML, True,
     "modelService.save() inside a loop becomes DML inside a loop — 150 statements and "
     "then a LimitException, part-way through, with earlier records already committed.",
     "Collect the records into a List and perform a single insert/update after the loop."),
    ("DAO_CALL_IN_LOOP", "high", _DAO_CALL, True,
     "A DAO call inside a loop almost always hides a query. Even if it is cached in "
     "Hybris, the Apex translation will not be.",
     "Move the lookup out of the loop, or pass the collection down and let the selector "
     "query once."),

    ("TRANSACTIONAL", "high", re.compile(r"@Transactional\b"), False,
     "Apex has no @Transactional. A method that relied on a Spring rollback will commit "
     "its earlier DML and then throw, leaving records half-written with nothing to undo it.",
     "Wrap the unit of work in a Database.Savepoint and roll back explicitly, or restructure "
     "so the whole change is a single DML call."),
    ("THREADING", "high", re.compile(r"\b(new\s+Thread\b|ExecutorService|CompletableFuture|@Async)\b"), False,
     "Apex has no threads. Nothing here has an equivalent, and the closest constructs "
     "(Queueable, Batch) are asynchronous with their own limits and no shared memory.",
     "Re-express as Queueable Apex chained explicitly, or as a Batch job."),
    ("STATIC_MUTABLE_STATE", "medium",
     re.compile(r"^\s*(?:private|protected|public)?\s*static\s+(?!final\b)[\w<>\[\],.]+\s+\w+\s*(=|;)", re.M), False,
     "Static state persists for the life of a Hybris JVM. An Apex static lives for one "
     "transaction and is then gone, so anything used as a cache silently stops caching.",
     "Make it final, or move the state to a Custom Setting / Platform Cache."),
]


def _class_of(text: str, fallback: str) -> str:
    m = re.search(r"\b(?:class|interface|enum)\s+(\w+)", text)
    return m.group(1) if m else fallback


def _java_findings(path: Path, rel: str) -> list[dict]:
    raw = read_text_or_empty(path)
    if not raw:
        return []
    text = _strip(raw)
    lines = text.splitlines()
    loops = _loop_lines(text)
    cls = _class_of(text, path.stem)
    out = []
    # Unbounded queries are handled separately: the useful signal is a query with
    # nothing bounding it *nearby*, and one finding per query would bury the file in
    # rows for a DAO that is doing its job.
    for m in re.finditer(r"new\s+FlexibleSearchQuery\(", text):
        line = text[:m.start()].count("\n") + 1
        window = "\n".join(lines[line - 1: line + 12])
        if re.search(r"\bsetCount\s*\(|\bsetNeedTotal\s*\(|\bLIMIT\b", window, re.I):
            continue
        out.append({
            "rule": "QUERY_NO_LIMIT", "severity": "medium", "file": rel, "line": line,
            "source_class": cls,
            "hazard": "This FlexibleSearch has nothing bounding it. As SOQL that means no LIMIT, "
                      "against a 50,000-row query cap and a 6 MB heap — a table that grows past "
                      "either fails in production rather than in a test with three records.",
            "fix": "Bound the query, or move the work to Batch Apex where the limits are "
                   "per-chunk. If the result is genuinely one row by unique key, this is safe "
                   "and can be dismissed.",
            "snippet": lines[line - 1].strip()[:120] if line <= len(lines) else "",
        })

    for rule, sev, pat, needs_loop, hazard, fix in _LINE_RULES:
        for m in pat.finditer(text):
            line = text[:m.start()].count("\n") + 1
            if needs_loop and line not in loops:
                continue
            out.append({
                "rule": rule, "severity": sev, "file": rel, "line": line,
                "source_class": cls, "hazard": hazard, "fix": fix,
                "snippet": (lines[line - 1].strip()[:120] if line <= len(lines) else ""),
            })
    return out


# ── whole-project rules ───────────────────────────────────────────────────────

def _project_findings(root: Path, files: list[Path]) -> list[dict]:
    out = []
    for p in files:
        rel = str(p.relative_to(root))
        suffix = p.suffix.lower()

        if suffix == ".xml":
            text = _strip_xml(read_text_or_empty(p))
            for m in re.finditer(r"InterceptorMapping|ValidateInterceptor|PrepareInterceptor"
                                 r"|LoadInterceptor|InitDefaultsInterceptor|RemoveInterceptor", text):
                out.append({
                    "rule": "INTERCEPTOR", "severity": "high", "file": rel,
                    "line": text[:m.start()].count("\n") + 1, "source_class": p.stem,
                    "hazard": "A Hybris interceptor runs on every save from any code path. Its Apex "
                              "equivalent is a trigger, where execution order between triggers is not "
                              "guaranteed and recursion is a real failure mode.",
                    "fix": "Move the logic into a single trigger handler per object with an explicit "
                           "recursion guard, rather than one trigger per rule.",
                    "snippet": "",
                })
                break                                   # one per file is enough
            for m in re.finditer(r'scope\s*=\s*"(session|request)"', text):
                out.append({
                    "rule": "SESSION_SCOPED_BEAN", "severity": "high", "file": rel,
                    "line": text[:m.start()].count("\n") + 1, "source_class": p.stem,
                    "hazard": "Apex is stateless. A session-scoped bean holds data between requests; "
                              "the equivalent Apex class is constructed and discarded per transaction, "
                              "so whatever it was holding is silently lost.",
                    "fix": "Persist the state (a record, a Custom Setting, or Platform Cache) or pass "
                           "it explicitly through the call chain.",
                    "snippet": "",
                })

        elif suffix == ".impex":
            text = read_text_or_empty(p)
            rows = sum(1 for ln in text.splitlines()
                       if ln.strip().startswith(";") or re.match(r"^\s*[A-Z_]+\s*;", ln))
            if rows > 200:
                out.append({
                    "rule": "IMPEX_VOLUME", "severity": "medium", "file": rel, "line": 1,
                    "source_class": p.stem,
                    "hazard": f"About {rows} data rows. A straight DML load will breach the 10,000-row "
                              "limit per transaction well before this completes.",
                    "fix": "Load through the Bulk API or Data Loader rather than as Apex DML.",
                    "snippet": "",
                })

        elif suffix == ".java":
            text = _strip(read_text_or_empty(p))
            m = re.search(r"\bextends\s+AbstractJobPerformable\b", text)
            if m:
                out.append({
                    "rule": "CRONJOB_CONCURRENCY", "severity": "medium", "file": rel,
                    "line": text[:m.start()].count("\n") + 1, "source_class": p.stem,
                    "hazard": "Scheduled Apex allows 100 scheduled jobs and 5 concurrent batch jobs per "
                              "org. A Hybris cronjob that assumes it can run whenever it likes, or "
                              "overlap with itself, will queue or fail instead.",
                    "fix": "Convert to Schedulable + Batch Apex, and make the job re-entrant so an "
                           "overlapping run is harmless.",
                    "snippet": "",
                })
    return out


_SKIP_DIRS = {".git", "node_modules", "target", "build", "dist", "__pycache__",
              ".venv", "venv", ".idea", ".vscode", "__MACOSX"}


def scan(input_dir: str) -> dict:
    """Every Hybris-specific hazard in a codebase. Deterministic; no model calls."""
    root = Path(input_dir)
    if not root.exists():
        return _empty()

    files, findings = [], []
    for p in root.rglob("*"):
        if any(part in _SKIP_DIRS for part in p.parts) or not p.is_file():
            continue
        files.append(p)

    for p in files:
        if p.suffix.lower() == ".java":
            findings += _java_findings(p, str(p.relative_to(root)))
    findings += _project_findings(root, files)

    # Worst first: a reviewer with ten minutes should spend them on the critical rows.
    findings.sort(key=lambda f: (_ORDER.get(f["severity"], 9), f["file"], f["line"]))
    for i, f in enumerate(findings, 1):
        f["id"] = f"H-{i:03d}"

    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    by_rule: dict[str, int] = {}
    for f in findings:
        by_rule[f["rule"]] = by_rule.get(f["rule"], 0) + 1

    return {
        "findings": findings,
        "summary": {"total": len(findings), **{k: counts.get(k, 0)
                                               for k in ("critical", "high", "medium", "info")},
                    "files_affected": len({f["file"] for f in findings}),
                    "by_rule": by_rule},
    }


def _empty() -> dict:
    return {"findings": [], "summary": {"total": 0, "critical": 0, "high": 0, "medium": 0,
                                        "info": 0, "files_affected": 0, "by_rule": {}}}


def headline(summary: dict) -> str:
    t = summary.get("total") or 0
    if not t:
        return "No Hybris-specific migration hazards detected."
    parts = [f"{summary[k]} {k}" for k in ("critical", "high", "medium") if summary.get(k)]
    return (f"{t} migration hazard(s) across {summary['files_affected']} file(s)"
            + (" — " + ", ".join(parts) if parts else ""))


_RULE_TITLES = {
    "SOQL_IN_LOOP": "FlexibleSearch inside a loop",
    "DML_IN_LOOP": "Save inside a loop",
    "DAO_CALL_IN_LOOP": "DAO call inside a loop",
    "QUERY_NO_LIMIT": "Unbounded query",
    "TRANSACTIONAL": "@Transactional boundary",
    "THREADING": "Threads or async execution",
    "STATIC_MUTABLE_STATE": "Mutable static state",
    "INTERCEPTOR": "Interceptor chain",
    "SESSION_SCOPED_BEAN": "Session-scoped bean",
    "IMPEX_VOLUME": "Large ImpEx load",
    "CRONJOB_CONCURRENCY": "Cronjob concurrency",
}


def rule_title(rule: str) -> str:
    return _RULE_TITLES.get(rule, rule.replace("_", " ").title())


def write_radar_md(output_dir: str, radar: dict) -> str:
    """ANTI_PATTERNS.md — what to fix, and whether to fix it before or after migrating."""
    s = radar.get("summary") or {}
    out = ["# Migration Hazard Report", "",
           "Patterns that are ordinary in SAP Commerce and dangerous once they are Apex. "
           "Found by static analysis of your source — no AI, no org, nothing sent anywhere.", "",
           f"**{headline(s)}**", ""]

    if s.get("critical"):
        out += [f"> ⚠️ **{s['critical']} critical finding(s).** These fail at realistic volume "
                "rather than in a test with three records. Fix them in the Hybris source before "
                "migrating, or accept that the generated Apex inherits the same shape.", ""]

    if s.get("by_rule"):
        out += ["| Hazard | Count |", "|---|---|"]
        out += [f"| {rule_title(r)} | {n} |"
                for r, n in sorted(s["by_rule"].items(), key=lambda kv: -kv[1])]
        out.append("")

    for sev in ("critical", "high", "medium", "info"):
        group = [f for f in radar.get("findings", []) if f["severity"] == sev]
        if not group:
            continue
        out += [f"## {sev} ({len(group)})", ""]
        for f in group:
            out += [f"### `{f['id']}` {rule_title(f['rule'])} — `{f['file']}`:{f['line']}", ""]
            if f.get("snippet"):
                out += ["```java", f["snippet"], "```", ""]
            out += [f"**On Salesforce:** {f['hazard']}", "",
                    f"**Fix:** {f['fix']}", ""]

    out += ["---", "",
            "> These are found in the **source**, before anything is generated. Fixing a "
            "FlexibleSearch-in-loop in the Java is cheaper than fixing the SOQL-in-loop it "
            "becomes, and it is the only point at which the fix is still one change rather "
            "than two."]

    path = Path(output_dir) / "ANTI_PATTERNS.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return str(path)
