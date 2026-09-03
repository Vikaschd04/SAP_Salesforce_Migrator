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


#: Names too common to carry evidence. A `getX` on both sides is not a traceable link.
_GENERIC = {"get", "set", "run", "execute", "perform", "handle", "process", "toString",
            "equals", "hashCode", "init", "main"}


def _source_symbols(text: str) -> list[dict]:
    """Methods in the *source*, located by the source platform's own reader. [2.11]

    Split from `_target_symbols` because they used to be one function serving two
    platforms, and that only worked while both were C-family. A PHP source read with a
    Java-shaped regex returns one method in six: it does not fail, it under-reports — in
    the module whose entire output is how much of the source can be accounted for.
    """
    from src import pipeline, runctx
    pipeline.ensure_registered()
    pid = runctx.pipeline_id()
    src = (pipeline.get(pid) if pid else pipeline.default_pipeline()).source
    return src.symbols(text)


def _target_symbols(text: str) -> list[dict]:
    """Methods in the *generated* code, located by the target platform's own reader."""
    from src import pipeline
    target = pipeline.current_target()
    if target is None:
        pipeline.ensure_registered()
        target = pipeline.default_pipeline().target
    return target.symbols(text)


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
    apex = [s for s in _target_symbols(apex_src) if s["name"] != ctor]
    java_syms: list[dict] = []
    for c in getattr(artifact, "source_classes", []) or []:
        for s in _source_symbols(c.get("source", "") or ""):
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
            orphans.append({"target": a["name"], "target_lines": [a["line_start"], a["line_end"]]})
            continue
        used.add((hit["source_class"], hit["name"]))
        links.append({
            "target": a["name"], "target_lines": [a["line_start"], a["line_end"]],
            "source": hit["name"], "source_lines": [hit["line_start"], hit["line_end"]],
            "source_class": hit["source_class"], "file": hit.get("file", ""),
            "basis": basis,
            # Exact is a fact; normalised is a strong inference and labelled as such.
            "confidence": "high" if basis == "exact name" else "medium",
        })

    # Java that produced nothing is the more alarming direction: a method that existed in
    # the source and has no counterpart may be logic that was simply not carried over.
    unmapped_java = [{"source": s["name"], "source_class": s["source_class"],
                      "source_lines": [s["line_start"], s["line_end"]]}
                     for s in java_syms if (s["source_class"], s["name"]) not in used]

    return {
        "target": getattr(artifact, "target_name", ""),
        "links": links,
        "target_without_origin": orphans,
        "source_without_target": unmapped_java,
        "coverage": round(100 * len(links) / len(apex)) if apex else None,
    }


def build_provenance(bb) -> dict:
    maps = [map_artifact(a) for a in bb.artifacts
            if getattr(a, "main_class", "") and not getattr(a, "is_lwc", False)]
    maps = [m for m in maps if m["links"] or m["target_without_origin"]]
    linked = sum(len(m["links"]) for m in maps)
    orphan = sum(len(m["target_without_origin"]) for m in maps)
    lost = sum(len(m["source_without_target"]) for m in maps)
    total = linked + orphan
    return {
        "artifacts": maps,
        "summary": {
            "artifacts": len(maps), "linked": linked, "target_without_origin": orphan,
            "source_without_target": lost, "methods": total,
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
    if s.get("target_without_origin"):
        tail.append(f"{s['target_without_origin']} with no origin")
    if s.get("source_without_target"):
        tail.append(f"{s['source_without_target']} Java method(s) with no Apex counterpart")
    return line + (" · " + ", ".join(tail) if tail else "")


def write_provenance_md(output_dir: str, prov: dict) -> str:
    s = prov.get("summary") or {}
    out = ["# Provenance — where each generated method came from", "",
           "Answers the first question any reviewer asks. Built by locating methods in both "
           "texts, so the line numbers are facts rather than a model's recollection.", "",
           f"**{headline(s)}**", ""]

    if s.get("source_without_target"):
        out += [f"> ⚠️ **{s['source_without_target']} Java method(s) have no Apex counterpart.** "
                "Some will be private helpers that were inlined, and some will be logic that "
                "did not make it. This is the list to check first.", ""]

    for m in prov.get("artifacts", []):
        out += [f"## `{m['target']}`"
                + (f" — {m['coverage']}% traced" if m["coverage"] is not None else ""), ""]
        if m["links"]:
            out += ["| Generated | Lines | ← | From | Lines | Basis |", "|---|---|---|---|---|---|"]
            for l in m["links"]:
                out.append(f"| `{l['target']}` | {l['target_lines'][0]}–{l['target_lines'][1]} | ← | "
                           f"`{l['source_class']}.{l['source']}` | {l['source_lines'][0]}–{l['source_lines'][1]} | "
                           f"{l['basis']} |")
            out.append("")
        if m["target_without_origin"]:
            out += ["**Generated with no traceable origin** — scaffolding, or invented:", ""]
            out += [f"- `{o['target']}` (lines {o['target_lines'][0]}–{o['target_lines'][1]})"
                    for o in m["target_without_origin"]]
            out.append("")
        if m["source_without_target"]:
            out += ["**Java with no Apex counterpart** — check these were meant to disappear:", ""]
            out += [f"- `{u['source_class']}.{u['source']}` (lines {u['source_lines'][0]}–{u['source_lines'][1]})"
                    for u in m["source_without_target"]]
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
