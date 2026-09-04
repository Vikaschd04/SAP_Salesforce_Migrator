"""OCC REST endpoints, and what Apex REST will not do for them. [1.25, E1-E2]

Spring lets one controller carry as many endpoints as it likes, at any path shape, and
resolves them by matching the request against every mapping. Apex REST does none of that.

**One method per verb, per class.** `@HttpGet` may appear once in a `@RestResource` class.
A controller with two `GET` mappings has no faithful translation: it must become two
classes, or one method that reads the URI and dispatches. A model asked to "convert this
controller" will happily emit two `@HttpGet` methods, and the class will not compile.

**`urlMapping` takes one trailing wildcard.** `/services/apexrest/pricing/*` is the whole
grammar. Spring's `/{baseSiteId}/pricing/orders/{code}/breakdown` has three variable
segments and two of them are not at the end, so the path cannot be declared — the segments
have to be parsed out of `RestContext.request.requestURI` by hand. Get this wrong and the
endpoint simply never matches, which looks like a routing problem rather than a porting
one.

**Nothing streams.** The response is built in memory and bounded by the Apex heap: 6 MB in
a synchronous request, 12 MB asynchronous. An OCC endpoint that paged through a large
catalogue by writing as it went has no equivalent shape.

**A caller with no session gets nothing, quietly.** Apex REST requires an authenticated
session. A payment provider posting a callback has none, so the endpoint needs a Site, the
class enabled for that Site's guest user, and CORS entries — and when one of those is
missing the response is a bare 401 or 403 that does not say which. That is a
deployment-time prerequisite, not code, so it belongs on a checklist someone reads before
cutover rather than in a generated class.
"""

from __future__ import annotations

import re

#: Apex REST allows one method per verb per class.
VERB_LIMIT = 1

#: Heap-bounded payload, and no streaming in either direction.
HEAP_SYNC_MB = 6
HEAP_ASYNC_MB = 12

_CLASS_RE = re.compile(r"\bclass\s+(\w+)")
_REST_CONTROLLER = re.compile(r"@(RestController|Controller)\b")

# `@RequestMapping(value = "/x", method = RequestMethod.GET)` and the shorthand forms.
_MAPPING = re.compile(r"@(RequestMapping|GetMapping|PostMapping|PutMapping|"
                      r"DeleteMapping|PatchMapping)\s*(\((?P<args>[^)]*)\))?", re.DOTALL)
_VALUE_ARG = re.compile(r"""(?:value|path)\s*=\s*["']([^"']*)["']""")
_BARE_ARG = re.compile(r"""^\s*["']([^"']*)["']""")
_METHOD_ARG = re.compile(r"RequestMethod\.(\w+)")
_SHORTHAND = {"GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
              "DeleteMapping": "DELETE", "PatchMapping": "PATCH"}

_PATH_VAR = re.compile(r"\{(\w+)\}")
_SIGNATURE = re.compile(r"\b(?:public|protected|private)\s+[\w<>,\[\]\s.]+\s+(\w+)\s*\(")

#: Paths and names that mean "something outside Salesforce will call this without a
#: session". Heuristic, and reported as such — the cost of missing one is a callback that
#: fails in production with a 401 nobody can attribute.
_CALLBACK_HINT = re.compile(
    r"callback|webhook|hook|notify|notification|ipn|psp|payment|pay/|/pay\b|return-url|"
    r"redirect|acknowledge|settle|capture", re.IGNORECASE)


def _base_path(source: str) -> str:
    """The class-level `@RequestMapping`, which prefixes every method mapping."""
    head = source.split("class ", 1)[0]
    for m in _MAPPING.finditer(head):
        args = m.group("args") or ""
        got = _VALUE_ARG.search(args) or _BARE_ARG.search(args)
        if got:
            return got.group(1)
    return ""


def endpoints(source: str) -> list[dict]:
    """Every REST endpoint this controller declares.

    Each row: `{method, verb, path, full_path, path_vars, line}`.
    """
    if not _REST_CONTROLLER.search(source or ""):
        return []

    base = _base_path(source)
    lines = (source or "").splitlines()
    out: list[dict] = []

    # Walk the class body only, so the class-level mapping is not read as an endpoint.
    body_at = source.index("class ") if "class " in source else 0
    for m in _MAPPING.finditer(source, body_at):
        args = m.group("args") or ""
        kind = m.group(1)
        got = _VALUE_ARG.search(args) or _BARE_ARG.search(args)
        path = got.group(1) if got else ""
        verb_m = _METHOD_ARG.search(args)
        verb = _SHORTHAND.get(kind) or (verb_m.group(1) if verb_m else "GET")

        # The method this annotation decorates is the next signature after it.
        sig = _SIGNATURE.search(source, m.end())
        name = sig.group(1) if sig else "(unnamed)"
        line = source[:m.start()].count("\n") + 1
        full = (base + path) or "/"
        out.append({"method": name, "verb": verb.upper(), "path": path, "full_path": full,
                    "path_vars": _PATH_VAR.findall(full), "line": line,
                    "snippet": lines[line - 1].strip()[:120] if line <= len(lines) else ""})
    return out


def _wildcard_ok(full_path: str) -> bool:
    """True when `urlMapping` can express this path.

    The grammar is a literal prefix plus at most one trailing `*`, so a variable segment
    is only expressible if it is the last one.
    """
    vars_ = _PATH_VAR.findall(full_path)
    if not vars_:
        return True
    if len(vars_) > 1:
        return False
    return full_path.rstrip("/").endswith("{%s}" % vars_[0])



def _mapping_hint(full_path: str) -> tuple[str, str]:
    """The `urlMapping` to use, and any caveat about how it was arrived at.

    `full_path.split("{")[0]` is not good enough: OCC paths routinely *begin* with
    `/{baseSiteId}`, which leaves no literal prefix at all and would produce `'//*'`.
    A leading variable segment has to be dropped rather than mapped, so the literal
    prefix is the leading run of fixed segments — and when there is none, the first fixed
    segment after the variables is the honest choice.
    """
    segments = [s for s in full_path.split("/") if s]
    fixed_lead = []
    for s in segments:
        if _PATH_VAR.fullmatch(s):
            break
        fixed_lead.append(s)

    if fixed_lead:
        return "/" + "/".join(fixed_lead) + "/*", ""

    dropped = [s for s in segments if _PATH_VAR.fullmatch(s)]
    rest = [s for s in segments if not _PATH_VAR.fullmatch(s)]
    note = (f" The path starts with `{dropped[0]}`, so there is no literal prefix to map. "
            "That segment cannot be part of the mapping and has to be dropped from the "
            "URL entirely")
    if dropped and "site" in dropped[0].lower():
        note += (" — a Hybris base-site id has no place in an Apex REST path. The site is "
                 "whichever Site the request arrived through, or an explicit header; it is "
                 "not a path segment any more, and every caller's URL changes.")
    else:
        note += ", and recovered from the body or a header instead."
    return ("/" + (rest[0] if rest else "endpoint") + "/*"), note


def findings(source: str, rel: str, cls: str) -> list[dict]:
    """Radar findings for one controller. [1.25]"""
    eps = endpoints(source)
    if not eps:
        return []
    out: list[dict] = []

    by_verb: dict[str, list] = {}
    for e in eps:
        by_verb.setdefault(e["verb"], []).append(e)

    for verb, group in sorted(by_verb.items()):
        if len(group) <= VERB_LIMIT:
            continue
        names = ", ".join(f"`{e['method']}()`" for e in group)
        out.append({
            "rule": "REST_VERB_COLLISION", "severity": "high", "file": rel,
            "line": group[0]["line"], "source_class": cls, "snippet": group[0]["snippet"],
            "hazard": (f"`{cls}` declares {len(group)} `{verb}` endpoints ({names}). An Apex "
                       f"`@RestResource` class may declare one `@Http{verb.title()}` method, "
                       "so this class has no one-to-one translation. Emitted as written it "
                       "does not compile, and the failure names the duplicate annotation "
                       "rather than the design problem behind it."),
            "fix": (f"Split into one `@RestResource` class per endpoint — the usual answer, "
                    "and it keeps the URLs independent — or keep one class and dispatch "
                    "inside the single method on `RestContext.request.requestURI`. Do not "
                    "let the two endpoints collapse into one; they return different "
                    "things."),
        })

    for e in eps:
        if not _wildcard_ok(e["full_path"]):
            out.append({
                "rule": "REST_PATH_TEMPLATE", "severity": "high", "file": rel,
                "line": e["line"], "source_class": cls, "snippet": e["snippet"],
                "hazard": (f"`{e['full_path']}` has variable segments "
                           f"({', '.join('`{%s}`' % v for v in e['path_vars'])}) that are not "
                           "all at the end. An Apex `urlMapping` is a literal prefix plus at "
                           "most one trailing `*`, so this path cannot be declared. The "
                           "endpoint does not fail loudly — it never matches, which reads as "
                           "a routing problem rather than a porting one."),
                "fix": (f"Declare `urlMapping='{_mapping_hint(e['full_path'])[0]}'` and parse "
                        "the segments yourself from "
                        "`RestContext.request.requestURI.split('/')`. Validate each one: the "
                        "framework no longer guarantees a segment is present or well-formed, "
                        "which is exactly what `@PathVariable` was doing."
                        + _mapping_hint(e["full_path"])[1]),
            })

        if e["verb"] in ("POST", "PUT", "PATCH") and _CALLBACK_HINT.search(e["full_path"] + cls):
            out.append({
                "rule": "REST_GUEST_ACCESS", "severity": "high", "file": rel,
                "line": e["line"], "source_class": cls, "snippet": e["snippet"],
                "hazard": (f"`{e['full_path']}` looks like a callback an outside system posts "
                           "to. Apex REST requires an authenticated session, and a payment "
                           "provider has none. Without a Site, a guest user granted access to "
                           "the class, and the caller's origin allowed, the request is "
                           "refused with a bare 401 or 403 that does not say which of the "
                           "three is missing — so it is usually diagnosed as the provider's "
                           "fault."),
                "fix": ("Before cutover: create the Site, enable this Apex class for its "
                        "guest user profile, add the provider's origin to CORS, and give the "
                        "guest user only the object permissions this endpoint needs. Verify "
                        "by calling it with no session — a signed-in test proves nothing "
                        "here. Authenticate the caller in the body (signature or shared "
                        "secret), because the endpoint itself is now open."),
            })

    out.append({
        "rule": "REST_PAYLOAD_CAP", "severity": "medium", "file": rel,
        "line": eps[0]["line"], "source_class": cls, "snippet": eps[0]["snippet"],
        "hazard": (f"`{cls}` exposes {len(eps)} endpoint(s). Apex REST builds the whole "
                   f"response in memory — there is no streaming — so it is bounded by the "
                   f"heap: {HEAP_SYNC_MB} MB synchronous, {HEAP_ASYNC_MB} MB asynchronous. "
                   "An OCC endpoint that returned a large collection stayed within its "
                   "budget by writing as it went, and that shape is not available."),
        "fix": ("Page every collection response explicitly, with the page size in the "
                "contract rather than left to the caller, and hold the callers to it. If a "
                "single response genuinely cannot fit, it is a Bulk API export or a file "
                "in object storage, not a REST endpoint."),
    })
    return out


def grounding_for(sources: list) -> str:
    """The endpoint shape, for the Builder's prompt. [1.25]

    Decidable from the source, so decided here: how many endpoints share a verb, and
    whether the path can be declared at all. Left to the model, a controller with two GETs
    becomes a class with two `@HttpGet` methods that does not compile.
    """
    rows = []
    for src in (sources or []):
        eps = endpoints(src or "")
        if not eps:
            continue
        cls = _CLASS_RE.search(src or "")
        rows.append((cls.group(1) if cls else "controller", eps))
    if not rows:
        return ""

    out = ["## REST endpoints — already decided", ""]
    for cls, eps in rows:
        by_verb: dict[str, list] = {}
        for e in eps:
            by_verb.setdefault(e["verb"], []).append(e)
        for verb, group in sorted(by_verb.items()):
            if len(group) > VERB_LIMIT:
                names = ", ".join(f"`{e['method']}()`" for e in group)
                out.append(f"- `{cls}` has {len(group)} `{verb}` endpoints ({names}). A "
                           f"`@RestResource` class may declare **one** `@Http{verb.title()}` "
                           "method. Emit one class per endpoint — do not put two in one "
                           "class, and do not merge them into a single method.")
        for e in eps:
            if not _wildcard_ok(e["full_path"]):
                mapping, note = _mapping_hint(e["full_path"])
                out.append(f"- `{e['full_path']}` cannot be a `urlMapping`: the grammar is a "
                           f"literal prefix plus one trailing `*`. Use "
                           f"`urlMapping='{mapping}'` and read the segments from "
                           "`RestContext.request.requestURI`; there is no `@PathVariable`."
                           + note)
    out.append(f"- Responses are built in memory and bounded by the heap "
               f"({HEAP_SYNC_MB} MB synchronous). Page collections; do not assume streaming.")
    return "\n".join(out)
