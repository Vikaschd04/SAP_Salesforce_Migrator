"""
provenance.py — where did this Apex come from?

The single most common reviewer objection to generated code is *"where did this come
from?"*, and until it can be answered every other assurance is a leap of faith. File-level
mapping ("this class came from those three") is common and nearly useless at review time;
what a reviewer needs is the method in front of them traced to the Java that produced it.

**Why this does not ask the model for line numbers.** The obvious design is a
`provenance: [{apex_lines: [30,41], java_lines: [42,58]}]` field in the generation schema.
It does not work: language models are fluent about structure and unreliable about
arithmetic on text they are not looking at, so those numbers come back plausible and
wrong — and a provenance map that is confidently wrong is worse than none, because it
gets trusted. Symbols are the thing models *are* reliable about, so the mapping is built
by locating symbols in both texts deterministically. The line numbers are then facts,
not opinions.

The other half of the value is the residue: **Apex methods with no Java origin**. Those
are either legitimate scaffolding (a constructor, a bulkification wrapper) or something
the model invented, and a reviewer should see the list either way.
"""

from __future__ import annotations

import re
from pathlib import Path

# A method declaration in Apex or Java. Deliberately conservative — it is better to miss
# an exotic signature than to claim a `for` loop is a method.
_METHOD = re.compile(
    r"^[ \t]*(?:@\w+[^\n]*\n[ \t]*)*"                       # annotations on their own lines
    r"(?:public|private|protected|global)\s+"
    r"(?:static\s+|final\s+|override\s+|virtual\s+|abstract\s+|synchronized\s+)*"
    r"(?:[\w<>\[\],.\s]+?\s+)?"                             # return type (absent on ctors)
    r"(\w+)\s*\([^)]*\)\s*(?:throws\s[\w,.\s]+)?\{",
    re.MULTILINE,
)

# Names that carry no signal — matching on these would pair unrelated code.
_GENERIC = {"get", "set", "run", "execute", "perform", "handle", "process", "toString",
            "equals", "hashCode", "init", "main"}


def _symbols(text: str) -> list[dict]:
    """Every method in a source text, with the line range of its body."""
    out = []
    for m in _METHOD.finditer(text or ""):
        name = m.group(1)
        start = (text[:m.start()].count("\n")) + 1
        # Walk braces from the opening one to find the real end of the body.
        i = text.index("{", m.end() - 1)
        depth, j = 0, i
        while j < len(text):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        end = text[:j].count("\n") + 1
        out.append({"name": name, "line_start": start, "line_end": max(start, end)})
    return out


def _norm(name: str) -> str:
    """Strip the affixes a migration adds, so a renamed method still matches its origin.

    `placeOrder` becoming `createOrders` is the bulkification the characterization work
    already established; `getFoo` becoming `fetchFoo` is ordinary. Normalising both sides
    catches those without pairing genuinely unrelated methods.
    """
    n = name[0].lower() + name[1:] if name else name
    n = re.sub(r"^(do|perform|execute|handle)", "", n)
    n = re.sub(r"(s|es|List|Bulk|All)$", "", n)
    n = re.sub(r"^(get|fetch|find|load|retrieve|select|query)", "get", n)
    n = re.sub(r"^(create|place|make|build|new)", "create", n)
    n = re.sub(r"^(update|modify|change|edit)", "update", n)
    n = re.sub(r"^(delete|remove|cancel|destroy)", "delete", n)
    return n.lower()


def _class_name(text: str) -> str:
    m = re.search(r"\b(?:class|interface|enum)\s+(\w+)", text or "")
    return m.group(1) if m else ""


def map_artifact(artifact) -> dict:
    """Trace each generated method back to the Java that produced it."""
    apex_src = getattr(artifact, "main_class", "") or ""
    # A constructor has no Java origin by definition and listing it as unexplained
    # would be noise in exactly the column that is supposed to mean something.
    ctor = _class_name(apex_src)
    apex = [s for s in _symbols(apex_src) if s["name"] != ctor]
    java_syms: list[dict] = []
    for c in getattr(artifact, "source_classes", []) or []:
        for s in _symbols(c.get("source", "") or ""):
            java_syms.append({**s, "source_class": c.get("class_name", ""),
                              "file": c.get("file", "")})

    by_exact: dict[str, list] = {}
    by_norm: dict[str, list] = {}
    for s in java_syms:
        by_exact.setdefault(s["name"], []).append(s)
        by_norm.setdefault(_norm(s["name"]), []).append(s)

    links, orphans = [], []
    used = set()
    for a in apex:
        hit, basis = None, ""
        cands = by_exact.get(a["name"])
        if cands:
            hit, basis = cands[0], "exact name"
        elif a["name"] not in _GENERIC:
            cands = by_norm.get(_norm(a["name"]))
            if cands:
                hit, basis = cands[0], "normalised name"

        if hit is None:
            orphans.append({"apex": a["name"], "apex_lines": [a["line_start"], a["line_end"]]})
            continue
        used.add((hit["source_class"], hit["name"]))
        links.append({
            "apex": a["name"], "apex_lines": [a["line_start"], a["line_end"]],
            "java": hit["name"], "java_lines": [hit["line_start"], hit["line_end"]],
            "source_class": hit["source_class"], "file": hit.get("file", ""),
            "basis": basis,
            # Exact is a fact; normalised is a strong inference and labelled as such.
            "confidence": "high" if basis == "exact name" else "medium",
        })

    # Java that produced nothing is the more alarming direction: a method that existed in
    # the source and has no counterpart may be logic that was simply not carried over.
    unmapped_java = [{"java": s["name"], "source_class": s["source_class"],
                      "java_lines": [s["line_start"], s["line_end"]]}
                     for s in java_syms if (s["source_class"], s["name"]) not in used]

    return {
        "target": getattr(artifact, "target_name", ""),
        "links": links,
        "apex_without_origin": orphans,
        "java_without_apex": unmapped_java,
        "coverage": round(100 * len(links) / len(apex)) if apex else None,
    }


def build_provenance(bb) -> dict:
    maps = [map_artifact(a) for a in bb.artifacts
            if getattr(a, "main_class", "") and not getattr(a, "is_lwc", False)]
    maps = [m for m in maps if m["links"] or m["apex_without_origin"]]
    linked = sum(len(m["links"]) for m in maps)
    orphan = sum(len(m["apex_without_origin"]) for m in maps)
    lost = sum(len(m["java_without_apex"]) for m in maps)
    total = linked + orphan
    return {
        "artifacts": maps,
        "summary": {
            "artifacts": len(maps), "linked": linked, "apex_without_origin": orphan,
            "java_without_apex": lost, "methods": total,
            "coverage": round(100 * linked / total) if total else None,
            "high": sum(1 for m in maps for l in m["links"] if l["confidence"] == "high"),
        },
    }


def headline(s: dict) -> str:
    t = s.get("methods") or 0
    if not t:
        return "No generated methods to trace."
    line = f"{s['linked']}/{t} generated method(s) traced to their Java origin ({s.get('coverage', 0)}%)"
    tail = []
    if s.get("apex_without_origin"):
        tail.append(f"{s['apex_without_origin']} with no origin")
    if s.get("java_without_apex"):
        tail.append(f"{s['java_without_apex']} Java method(s) with no Apex counterpart")
    return line + (" · " + ", ".join(tail) if tail else "")


def write_provenance_md(output_dir: str, prov: dict) -> str:
    s = prov.get("summary") or {}
    out = ["# Provenance — where each generated method came from", "",
           "Answers the first question any reviewer asks. Built by locating methods in both "
           "texts, so the line numbers are facts rather than a model's recollection.", "",
           f"**{headline(s)}**", ""]

    if s.get("java_without_apex"):
        out += [f"> ⚠️ **{s['java_without_apex']} Java method(s) have no Apex counterpart.** "
                "Some will be private helpers that were inlined, and some will be logic that "
                "did not make it. This is the list to check first.", ""]

    for m in prov.get("artifacts", []):
        out += [f"## `{m['target']}`"
                + (f" — {m['coverage']}% traced" if m["coverage"] is not None else ""), ""]
        if m["links"]:
            out += ["| Generated | Lines | ← | From | Lines | Basis |", "|---|---|---|---|---|---|"]
            for l in m["links"]:
                out.append(f"| `{l['apex']}` | {l['apex_lines'][0]}–{l['apex_lines'][1]} | ← | "
                           f"`{l['source_class']}.{l['java']}` | {l['java_lines'][0]}–{l['java_lines'][1]} | "
                           f"{l['basis']} |")
            out.append("")
        if m["apex_without_origin"]:
            out += ["**Generated with no traceable origin** — scaffolding, or invented:", ""]
            out += [f"- `{o['apex']}` (lines {o['apex_lines'][0]}–{o['apex_lines'][1]})"
                    for o in m["apex_without_origin"]]
            out.append("")
        if m["java_without_apex"]:
            out += ["**Java with no Apex counterpart** — check these were meant to disappear:", ""]
            out += [f"- `{u['source_class']}.{u['java']}` (lines {u['java_lines'][0]}–{u['java_lines'][1]})"
                    for u in m["java_without_apex"]]
            out.append("")

    out += ["---", "",
            "> **On confidence.** `exact name` is a fact: the method kept its name. "
            "`normalised name` is a strong inference — the migration renamed it (a "
            "single-record `placeOrder` becoming a bulk `createOrders`, say) and the "
            "normalised forms agree. Nothing here is guessed from line numbers, which is "
            "the one thing a model would get confidently wrong."]

    path = Path(output_dir) / "PROVENANCE.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return str(path)
