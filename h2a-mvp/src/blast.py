"""
blast.py — what does reworking this break?

A reviewer at the Build gate can regenerate a single artifact, which is the right
affordance and a slightly dangerous one: the classes that depended on the old shape are
not visibly connected to the button being pressed. "Redo OrderService as a Selector" is
one click and can invalidate six other artifacts, their tests, and a schema object three
of them write to.

So before a rework is approved, this says what travels with it. Everything needed already
exists — ingest records `referenced_types` per class, artifacts know their source classes,
their SObject references, their generated tests and the business rules they carry. This is
a graph walk over data already on the board, not new analysis.

**Direct and transitive are reported separately, on purpose.** A direct dependent almost
certainly needs re-reviewing; a transitive one at distance three usually does not, and
collapsing them into a single scary number would train people to ignore it.
"""

from __future__ import annotations

from pathlib import Path


def _class_graph(bb) -> dict[str, set[str]]:
    """class -> the classes that reference it. Reversed, because the question is
    'who depends on me', not 'what do I depend on'."""
    known = {c.get("class_name") for c in bb.all_classes if c.get("class_name")}
    dependents: dict[str, set[str]] = {n: set() for n in known}
    for c in bb.all_classes:
        me = c.get("class_name")
        for ref in (c.get("referenced_types") or []):
            if ref in known and ref != me:
                dependents[ref].add(me)
    return dependents


def blast_radius(bb, target_name: str, *, max_depth: int = 3) -> dict:
    """Everything a rework of `target_name` puts back in question."""
    art = next((a for a in bb.artifacts if a.target_name == target_name), None)
    if art is None:
        return {"target": target_name, "found": False}

    dependents = _class_graph(bb)
    own = {c.get("class_name") for c in art.source_classes if c.get("class_name")}

    # Breadth-first, keeping the distance — a dependent three hops away is not the same
    # claim as one that calls you directly.
    depth_of: dict[str, int] = {}
    frontier, d = set(own), 0
    while frontier and d < max_depth:
        d += 1
        nxt: set[str] = set()
        for name in frontier:
            for dep in dependents.get(name, set()):
                if dep not in own and dep not in depth_of:
                    depth_of[dep] = d
                    nxt.add(dep)
        frontier = nxt

    # Which other artifacts carry those classes.
    art_of: dict[str, object] = {}
    for a in bb.artifacts:
        for c in a.source_classes:
            if c.get("class_name"):
                art_of[c["class_name"]] = a

    affected: dict[str, dict] = {}
    for cls, dist in depth_of.items():
        a = art_of.get(cls)
        if a is None or a.target_name == target_name:
            continue
        cur = affected.setdefault(a.target_name, {
            "target": a.target_name, "layer": a.layer, "distance": dist,
            "via": [], "rules": len(a.business_rules or []),
            "test_class": f"{a.target_name}Test" if (a.test_class or "").strip() else None,
        })
        cur["distance"] = min(cur["distance"], dist)
        cur["via"].append(cls)

    direct = [a for a in affected.values() if a["distance"] == 1]
    indirect = [a for a in affected.values() if a["distance"] > 1]
    for group in (direct, indirect):
        group.sort(key=lambda a: (-a["rules"], a["target"]))

    # Schema this artifact writes to — shared objects are how a rework reaches code that
    # never references it directly.
    schema = sorted({s for s in (art.sobject_refs or []) if s})
    shared = sorted({s for s in schema
                     for a in bb.artifacts if a.target_name != target_name
                     and s in (a.sobject_refs or [])})

    tests = [a["test_class"] for a in direct + indirect if a["test_class"]]
    if (art.test_class or "").strip():
        tests.insert(0, f"{target_name}Test")

    # Recorded behaviours that exercise this artifact stop being evidence for it the
    # moment it is regenerated.
    behaviours = [b for b in (getattr(bb, "characterization", None) or {}).get("behaviors", [])
                  if b.get("target") == target_name]

    return {
        "target": target_name, "found": True,
        "direct": direct, "indirect": indirect,
        "schema": schema, "shared_schema": shared,
        "tests_to_rerun": tests,
        "rules_at_risk": len(art.business_rules or []) + sum(a["rules"] for a in direct),
        "behaviours_invalidated": len(behaviours),
        "summary": {"direct": len(direct), "indirect": len(indirect),
                    "tests": len(tests), "shared_objects": len(shared)},
    }


def headline(b: dict) -> str:
    if not b.get("found"):
        return f"No artifact named {b.get('target')}."
    s = b["summary"]
    if not (s["direct"] or s["indirect"]):
        return "Nothing else depends on this — reworking it is self-contained."
    bits = [f"{s['direct']} directly dependent artifact(s)"]
    if s["indirect"]:
        bits.append(f"{s['indirect']} further out")
    if s["tests"]:
        bits.append(f"{s['tests']} test(s) to re-run")
    if s["shared_objects"]:
        bits.append(f"{s['shared_objects']} shared object(s)")
    return "Reworking this touches " + ", ".join(bits) + "."


def build_all(bb) -> dict:
    """Blast radius for every artifact, so the gate can show it without a round trip."""
    return {a.target_name: blast_radius(bb, a.target_name) for a in bb.artifacts}
