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

    # TRANSACTIONAL was here and has been removed rather than narrowed. It claimed a
    # @Transactional method "will commit its earlier DML and then throw, leaving records
    # half-written" — which is true only when a caller catches the exception. Apex rolls
    # back the entire request on an *uncaught* one, so the claim was wrong for the common
    # shape and its advice (always use a savepoint) was wrong with it. TRANSACTION_SHAPE
    # decides which of the two shapes a method is and says the right thing for each. [1.21c]
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

    out.extend(_money_findings(text, rel, cls, lines))
    out.extend(_flexsearch_findings(text, rel, cls, lines))
    out.extend(_lifecycle_findings(text, rel, cls, lines))

    # The REST surface. Spring resolves any number of endpoints at any path shape; Apex
    # REST allows one method per verb per class and a urlMapping of one trailing
    # wildcard, so a controller can be untranslatable in ways that only surface as a
    # compile error or an endpoint that never matches. [1.25]
    from src.adapters.rest_surface import findings as _rest_findings
    out.extend(_rest_findings(raw, rel, cls))

    # Parsed rather than matched: whether a getter is guarded is a question about the
    # method around it, and every regex answer to that is wrong in one direction. [1.30]
    from src.adapters.java_nullability import findings as _null_findings
    out.extend(_null_findings(raw, rel, cls, lines))

    # Which of the two transaction shapes this is — the generic TRANSACTIONAL rule says
    # "use a savepoint", which is right for one of them and wasteful for the other. [1.21c]
    from src.adapters.java_transactions import findings as _tx_findings
    out.extend(_tx_findings(raw, rel, cls, lines))

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

# ── money and rounding [1.17] ─────────────────────────────────────────────────
#
# The failure this catches is the one no other gate can see. Everything else in the
# engine asks whether the migrated code is *shaped* right — it compiles, it deploys, the
# Critic approves it, the reviewer signs it off. Rounding is different: a discount that
# rounds HALF_UP at two places in Java and lands on Apex's default instead produces code
# that passes every one of those checks and is off by a cent. Per order. Every order.
# Forever. Nobody finds it in review; finance finds it in a reconciliation months later.
#
# So the contract is extracted from the source, where it is stated explicitly, and
# reported as something the migration must carry — rather than left for a model to
# reproduce from memory.

_SCALE_CALL = re.compile(
    r"\.setScale\s*\(\s*(\d+)\s*,\s*(?:RoundingMode\.|BigDecimal\.ROUND_)(\w+)")
_SCALED_DIVIDE = re.compile(
    r"\.divide\s*\([^,()]+,\s*(\d+)\s*,\s*(?:RoundingMode\.|BigDecimal\.ROUND_)(\w+)")

# `double totalPrice` — a name that means money, in a type that cannot hold it exactly.
_FLOAT_MONEY = re.compile(
    r"\b(?:double|float|Double|Float)\s+(\w*(?:price|amount|total|cost|rate|discount"
    r"|tax|subtotal|fee|charge|balance|payment|refund)\w*)\b", re.IGNORECASE)


def _divide_arity(text: str, open_paren: int) -> int:
    """How many top-level arguments the call starting at `open_paren` was given.

    Counted by balancing parentheses rather than by regex, because the divisor is often
    itself a call — `total.divide(BigDecimal.valueOf(qty))` has one argument, not two.
    """
    depth, args, seen = 0, 1, False
    for i in range(open_paren, min(len(text), open_paren + 4000)):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return args if seen else 0
        elif ch == "," and depth == 1:
            args += 1
        elif depth == 1 and not ch.isspace():
            seen = True
    return args


def _money_findings(text: str, rel: str, cls: str, lines: list) -> list:
    """Rounding contracts, unscaled division, and money kept in a float."""
    out = []

    def at(pos):
        return text[:pos].count("\n") + 1

    # 1. The rounding contract, reported once per distinct (scale, mode) per class.
    #    Five identical setScale calls are one decision, not five hazards — but the count
    #    matters, because every one of those sites has to survive the migration.
    contracts: dict = {}
    for pat in (_SCALE_CALL, _SCALED_DIVIDE):
        for m in pat.finditer(text):
            key = (m.group(1), m.group(2).upper())
            contracts.setdefault(key, []).append(at(m.start()))
    for (scale, mode), where in sorted(contracts.items()):
        first = min(where)
        out.append({
            "rule": "ROUNDING_CONTRACT", "severity": "high", "file": rel, "line": first,
            "source_class": cls,
            "hazard": f"This class states an explicit rounding contract — {scale} decimal "
                      f"place(s), {mode} — and applies it in {len(where)} place(s). Apex "
                      "Decimal does not round the same way by default, so if the migrated "
                      "code drops the explicit scale the result is still a valid number, "
                      "still passes review, and is wrong by a fraction of a cent on every "
                      "calculation.",
            "fix": f"Express the same contract in Apex: `value.setScale({scale}, "
                   f"System.RoundingMode.{mode})`, applied at the same boundaries. Then "
                   "assert it — a characterization test with a recorded value is the only "
                   "thing that proves the rounding survived.",
            "snippet": (lines[first - 1].strip()[:120] if first <= len(lines) else ""),
        })

    # 2. Division with no scale. Java throws on a non-terminating result; Apex has no
    #    single-argument divide at all, so a scale gets chosen — the question is by whom.
    for m in re.finditer(r"\.divide\s*\(", text):
        if _divide_arity(text, m.end() - 1) == 1:
            line = at(m.start())
            out.append({
                "rule": "UNSCALED_DIVIDE", "severity": "high", "file": rel, "line": line,
                "source_class": cls,
                "hazard": "divide() with no scale. In Java this throws ArithmeticException "
                          "on a non-terminating result, so the legacy behaviour is either "
                          "'exact or fail'. Apex has no single-argument divide, which means "
                          "the migration must pick a scale — and picking one silently is "
                          "how the drift starts.",
                "fix": "Decide the scale here, in the source's terms, before migrating: "
                       "`divide(divisor, <scale>, System.RoundingMode.<MODE>)`. If the "
                       "legacy code genuinely relied on the exception, that is a business "
                       "rule and belongs in the ledger.",
                "snippet": (lines[line - 1].strip()[:120] if line <= len(lines) else ""),
            })

    # 3. Money in a binary float. Worth reporting even though Apex is *better* here.
    for m in _FLOAT_MONEY.finditer(text):
        line = at(m.start())
        out.append({
            "rule": "FLOAT_MONEY", "severity": "medium", "file": rel, "line": line,
            "source_class": cls,
            "hazard": f"`{m.group(1)}` holds money in a binary float, which cannot represent "
                      "0.10 exactly. Apex Decimal can. That makes the migrated code more "
                      "correct than the original — and therefore in disagreement with it: "
                      "expect characterization replays of this value to differ, and read "
                      "those differences as the legacy error, not a migration defect.",
            "fix": "Migrate to Decimal, and record the expected drift against the recorded "
                   "values so the difference is explained rather than investigated twice.",
            "snippet": (lines[line - 1].strip()[:120] if line <= len(lines) else ""),
        })

    return out



def _flexsearch_findings(text: str, rel: str, cls: str, lines: list) -> list:
    """Queries SOQL cannot express, named rather than attempted. [1.23]

    The existing QUERY_NO_LIMIT rule looks at the *call site*; this reads the query
    itself. A query that no SOQL construct can express is worth flagging loudly, because
    the alternative is a model producing SOQL-shaped text that either fails to compile or
    compiles against the wrong relationship and silently returns different rows.
    """
    from src.adapters.hybris_flexsearch import analyse, find_queries

    out = []
    for line, query in find_queries(text):
        verdict = analyse(query)
        for r in verdict["reasons"]:
            out.append({
                "rule": r["code"],
                "severity": "critical" if r["code"] == "FS_JOIN" else "high",
                "file": rel, "line": line, "source_class": cls,
                "hazard": f"This FlexibleSearch {r['detail']}",
                "fix": r["fix"],
                "snippet": query.strip()[:120],
            })
    return out


def _lifecycle_findings(text: str, rel: str, cls: str, lines: list) -> list:
    """Code the platform invoked, which the target will not. [1.21]

    The existing INTERCEPTOR rule fires on the Spring wiring that registers a hook. This
    fires on the hook itself, because the two are found at different times by different
    people: the wiring is a configuration file nobody reads, and the class is where the
    business rules actually live.
    """
    from src.adapters.hybris_lifecycle import detect

    hook = detect(text)
    if not hook:
        return []
    line = hook["line"]
    if hook["events"]:
        fix = (f"A trigger scaffold is emitted for this ({hook['type']}LifecycleTrigger on "
               f"{hook['type']}__c, {hook['events']}) with the re-entry guard in place. "
               "Wire the converted class into its handler, and keep queries out of the "
               "per-record loop — the platform handed this one record, a trigger receives "
               "up to 200.")
    else:
        fix = ("Apex has no equivalent hook — there is no after-read trigger — so no "
               "scaffold is emitted. This logic needs a different home entirely: move it "
               "to the point of use, or accept that it cannot be automatic.")
    return [{
        "rule": "LIFECYCLE_HOOK", "severity": "critical", "file": rel, "line": line,
        "source_class": cls,
        "hazard": f"This is a {hook['hook']}: the Hybris persistence layer ran it "
                  f"automatically — it {hook['note']} — without anything in the codebase "
                  "calling it. Converted to Apex it becomes an ordinary class, and an "
                  "ordinary class runs only when something calls it. Every rule in here "
                  "stops being enforced, while the code still exists and still reads "
                  "correctly.",
        "fix": fix,
        "snippet": (lines[line - 1].strip()[:120] if line <= len(lines) else ""),
    }]


def _project_findings(root: Path, files: list[Path]) -> list[dict]:
    out = []
    for p in files:
        rel = str(p.relative_to(root))
        suffix = p.suffix.lower()

        if suffix == ".xml":
            text = _strip_xml(read_text_or_empty(p))

            # A localized attribute holds one value per locale in a single attribute.
            # Salesforce has no equivalent field, so a straight conversion keeps the
            # default locale and drops the rest — for an EU retailer, most of their
            # content, with nothing in the output showing it went missing. [1.19]
            if p.name.endswith("items.xml"):
                raw = read_text_or_empty(p)
                attrs = (re.findall(r'qualifier="(\w+)"[^>]*type="localized:', raw)
                         + re.findall(r'type="localized:[^"]*"[^>]*qualifier="(\w+)"', raw))
                if attrs:
                    names = sorted(set(attrs))
                    out.append({
                        "rule": "LOCALIZED_ATTRIBUTE", "severity": "high", "file": rel,
                        "line": 1, "source_class": p.stem,
                        "hazard": f"{len(names)} localized attribute(s) — "
                                  f"{', '.join(names[:6])}"
                                  f"{' and others' if len(names) > 6 else ''}. Each holds a "
                                  "separate value per locale. A Salesforce custom field "
                                  "holds one value, so the migration carries the default "
                                  "locale and every other translation is dropped without "
                                  "appearing anywhere as a loss.",
                        "fix": "Decide per attribute, because the two right answers "
                               "differ: UI labels belong in Translation Workbench, while "
                               "translated *content* needs a child object keyed by "
                               "locale. Neither is automatic, and doing nothing ships an "
                               "English-only org.",
                        "snippet": "",
                    })
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



def _frontend_findings(path: Path, rel: str) -> list[dict]:
    """Angular constructs LWC cannot carry across. [1.24]

    The storefront was outside the radar entirely — it scanned `.java` and nothing else —
    so a component that polls, or renders money through a `currency` pipe, produced a
    clean report and a component that silently never updates. These land in
    ANTI_PATTERNS.md beside the backend hazards because that is the file a reviewer
    actually opens.
    """
    from src.adapters import angular_gaps

    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    # Angular keeps the template beside the component under the same stem. An inline
    # `template:` string is already in the source, so it is scanned either way.
    html = path.with_name(path.name[:-3] + ".html")
    try:
        template = html.read_text(encoding="utf-8", errors="ignore") if html.exists() else ""
    except OSError:
        template = ""
    template_rel = rel[:-3] + ".html" if template else ""
    return angular_gaps.findings(source, template, rel,
                                 path.stem.replace(".component", ""), template_rel)


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
        elif p.name.endswith(".component.ts"):
            findings += _frontend_findings(p, str(p.relative_to(root)))
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
    "FS_JOIN": "Query joins types",
    "FS_SUBQUERY": "Query has a subquery",
    "FS_LEADING_WILDCARD": "Leading-wildcard match",
    "TRANSACTION_SHAPE": "Transaction rollback shape",
    "THREADING": "Threads or async execution",
    "STATIC_MUTABLE_STATE": "Mutable static state",
    "INTERCEPTOR": "Interceptor chain",
    "LIFECYCLE_HOOK": "Platform-invoked hook",
    "UNGUARDED_NULL": "Unguarded getter result",
    "SESSION_SCOPED_BEAN": "Session-scoped bean",
    "LOCALIZED_ATTRIBUTE": "Localized attribute",
    "IMPEX_VOLUME": "Large ImpEx load",
    "CRONJOB_CONCURRENCY": "Cronjob concurrency",
    # Frontend. [1.24]
    "NG_RXJS": "RxJS operator with no LWC equivalent",
    "NG_PIPE": "Template pipe with no LWC equivalent",
    "NG_SLOT": "Content projection by selector",
    "NG_CMS": "Component chosen at runtime",
    "NG_BINDING": "Two-way binding",
    "NG_CONTROL_FLOW": "Named template branch",
    "NG_LIFECYCLE": "Lifecycle hook called by hand",
    # Integration surface. [1.25]
    "REST_VERB_COLLISION": "Two endpoints share an HTTP verb",
    "REST_PATH_TEMPLATE": "Path template no urlMapping can express",
    "REST_GUEST_ACCESS": "Endpoint called without a session",
    "REST_PAYLOAD_CAP": "Response bounded by heap, not streamed",
    # Adobe Commerce. Kept in one table because rule ids are unique across sources and a
    # second lookup would be a second place for a title to go missing. [1.39]
    "OBJECT_MANAGER": "Dependency taken from the ObjectManager",
    "AROUND_PLUGIN": "Plugin that can skip the original",
    "OBSERVER_MUTATES_PAYLOAD": "Observer mutates the event payload",
    "EAV_DATA_PATCH": "Attributes declared only in the database",
    "STORE_SCOPED_CONFIG": "Store-scoped configuration",
    "MAGIC_DATA_ACCESS": "Untyped magic data access",
    "CLUSTER_CRON": "Cron that assumes a single runner",
    "N_PLUS_ONE": "Query inside a loop",
    "COLLECTION_NO_LIMIT": "Unbounded collection load",
}


def rule_title(rule: str) -> str:
    return _RULE_TITLES.get(rule, rule.replace("_", " ").title())



def _platforms() -> tuple:
    """`(source label, source language, target label, target language)` for this run.

    Every sentence in the hazard report named SAP Commerce and Apex, whichever migration
    produced it — so an Adobe Commerce estate was told its Magento habits were "ordinary
    in SAP Commerce and dangerous once they are Apex", about PHP becoming Java. A report
    that names the wrong platform is the clearest signal a reader has that the tool does
    not know what it just did. [1.39]
    """
    try:
        from src import pipeline, runctx
        pipeline.ensure_registered()
        pid = runctx.pipeline_id()
        p = pipeline.get(pid) if pid else pipeline.default_pipeline()
        return (p.source.label.split(" (")[0], getattr(p.source, "code_language", "code"),
                p.target.label.split(" (")[0], getattr(p.target, "code_language", "code"))
    except Exception:
        return "the source platform", "code", "the target platform", "code"


def write_radar_md(output_dir: str, radar: dict) -> str:
    """ANTI_PATTERNS.md — what to fix, and whether to fix it before or after migrating."""
    s = radar.get("summary") or {}
    src_label, src_lang, tgt_label, tgt_lang = _platforms()
    out = ["# Migration Hazard Report", "",
           f"Patterns that are ordinary in {src_label} and dangerous once they are "
           f"{tgt_lang}. Found by static analysis of your source — no AI, no org, nothing "
           "sent anywhere.", "",
           f"**{headline(s)}**", ""]

    if s.get("critical"):
        out += [f"> ⚠️ **{s['critical']} critical finding(s).** These fail at realistic volume "
                f"rather than in a test with three records. Fix them in the {src_label} "
                f"source before migrating, or accept that the generated {tgt_lang} inherits "
                "the same shape.", ""]

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
                out += [f"```{src_lang.lower()}", f["snippet"], "```", ""]
            out += [f"**On {tgt_label}:** {f['hazard']}", "",
                    f"**Fix:** {f['fix']}", ""]

    out += ["---", "",
            "> These are found in the **source**, before anything is generated. Fixing one "
            f"in the {src_lang} is cheaper than fixing what it becomes in {tgt_lang}, and "
            "it is the only point at which the fix is still one change rather than two."]

    path = Path(output_dir) / "ANTI_PATTERNS.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return str(path)
