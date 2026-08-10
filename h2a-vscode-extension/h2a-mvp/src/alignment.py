"""
alignment.py — intent · implementation · proof, on one row.

A side-by-side text diff between Java and Apex is close to useless: the languages differ,
the migration deliberately reshapes call signatures, and a reviewer ends up comparing
punctuation instead of meaning. The useful question is not "how did line 42 change" but
*"this rule existed — where does it live now, and what proves it still holds?"*

Everything needed already exists by the end of a run and had never been joined up:

    intent          the business rules the Comprehender extracted, per source class
    implementation  the generated method, from provenance, with real line ranges
    proof           a recorded behaviour replayed against it, or the rule-ledger verdict

**The chain is only as strong as its weakest link, and this says which one that is.**
Rule → source class is recorded fact. Apex method → Java method is provenance, already
graded exact or normalised. But rule → *method* is keyword overlap — the Comprehender
extracts a rule from a class, not from a line — so that link is a heuristic and is
labelled one everywhere it appears. A row that cannot complete the chain says where it
broke instead of guessing the rest; a plausible-looking chain built on a bad match would
be worse than an incomplete one, because it would be believed.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.parity import _keywords

# Below this share of shared distinctive terms, a rule and a method are not related
# enough to claim a link. Matches parity's threshold deliberately — the same evidence
# standard, applied to the same kind of question.
_MATCH_FLOOR = 0.34


def _best_method(rule: str, methods: list[dict]) -> tuple[dict | None, float]:
    """The method whose name and body best account for a rule. Heuristic, by design."""
    want = set(_keywords(rule))
    if not want or not methods:
        return None, 0.0
    best, score = None, 0.0
    for m in methods:
        # Split camelCase so `applySpendDiscount` offers apply / spend / discount.
        name_words = re.sub(r"(?<!^)(?=[A-Z])", " ", m.get("name", "")).lower()
        have = set(_keywords(name_words + " " + (m.get("body", "") or "")))
        if not have:
            continue
        overlap = len(want & have) / len(want)
        if overlap > score:
            best, score = m, overlap
    return (best, score) if score >= _MATCH_FLOOR else (None, score)


def _methods_of(source: str) -> list[dict]:
    """Java methods with their bodies, so a rule can be matched against what code does."""
    from src.provenance import _symbols
    lines = (source or "").splitlines()
    out = []
    for s in _symbols(source or ""):
        body = "\n".join(lines[s["line_start"] - 1: s["line_end"]])
        out.append({**s, "body": body})
    return out


def build_alignment(bb) -> dict:
    """Join intent, implementation and proof into one row per business rule."""
    from src.provenance import map_artifact

    # Which artifact carries each source class, and how its methods map.
    art_of, prov_of = {}, {}
    for a in bb.artifacts:
        prov_of[a.target_name] = map_artifact(a)
        for c in a.source_classes:
            if c.get("class_name"):
                art_of[c["class_name"]] = a

    # Recorded behaviours, keyed by the Java method they exercise.
    behaviours: dict[str, list] = {}
    for b in (getattr(bb, "characterization", None) or {}).get("behaviors", []):
        behaviours.setdefault(b.get("target_method", ""), []).append(b)

    # Rule-ledger verdicts, so a row can fall back to "a test mentions this".
    verdicts = {r["rule"]: r for r in
                (getattr(bb, "rule_ledger", None) or {}).get("rules", [])}

    rows = []
    for cls_name, u in (bb.comprehensions or {}).items():
        if not isinstance(u, dict):
            continue
        art = art_of.get(cls_name)
        src = next((c.get("source", "") for c in (art.source_classes if art else [])
                    if c.get("class_name") == cls_name), "")
        methods = _methods_of(src)

        for rule in (u.get("business_rules") or []):
            rule = (rule or "").strip()
            if not rule:
                continue
            row = {"rule": rule, "source_class": cls_name,
                   "target": art.target_name if art else None,
                   "java_method": None, "java_lines": None,
                   "apex_method": None, "apex_lines": None,
                   "link_confidence": None, "proof": None, "proof_kind": "none",
                   "broken_at": None}

            if art is None:
                row["broken_at"] = "no artifact carries this class"
                rows.append(row)
                continue

            jm, score = _best_method(rule, methods)
            if jm is None:
                row["broken_at"] = ("could not tie this rule to a specific method — it is "
                                    "carried by the class as a whole")
            else:
                row["java_method"] = jm["name"]
                row["java_lines"] = [jm["line_start"], jm["line_end"]]
                row["match_score"] = round(score, 2)

                link = next((l for l in prov_of[art.target_name]["links"]
                             if l["java"] == jm["name"]), None)
                if link:
                    row["apex_method"] = link["apex"]
                    row["apex_lines"] = link["apex_lines"]
                    row["link_confidence"] = link["confidence"]
                else:
                    row["broken_at"] = (f"`{jm['name']}` has no traceable counterpart in "
                                        f"`{art.target_name}`")

            # Proof, strongest first: a replayed behaviour beats a keyword-matched test.
            for b in behaviours.get(row["java_method"] or "", []):
                if b.get("mode") == "direct" or b.get("bridge"):
                    row["proof"] = f"{b['id']} — {b['label']}"
                    row["proof_kind"] = "replayed"
                    break
            if not row["proof"]:
                v = verdicts.get(rule)
                if v and v["status"] == "asserted":
                    row["proof"] = "a generated test references this rule's terms"
                    row["proof_kind"] = "asserted"
                elif v and v["status"] in ("implemented", "at_risk", "dropped"):
                    row["proof_kind"] = v["status"]
            rows.append(row)

    complete = [r for r in rows if r["apex_method"]]
    proven = [r for r in rows if r["proof_kind"] in ("replayed", "asserted")]
    rows.sort(key=lambda r: (bool(r["apex_method"]), r["proof_kind"] != "none",
                             r["source_class"]))
    return {
        "rows": rows,
        "summary": {
            "rules": len(rows), "aligned": len(complete), "proven": len(proven),
            "replayed": sum(1 for r in rows if r["proof_kind"] == "replayed"),
            "broken": len(rows) - len(complete),
        },
    }


def headline(s: dict) -> str:
    t = s.get("rules") or 0
    if not t:
        return ("No business rules to align — run with a real provider (mock comprehension "
                "does not infer rules).")
    return (f"{s['aligned']}/{t} rule(s) traced from intent to implementation · "
            f"{s['proven']} with proof attached ({s.get('replayed', 0)} replayed)")


def write_alignment_md(output_dir: str, al: dict) -> str:
    s = al.get("summary") or {}
    out = ["# Semantic Alignment — intent · implementation · proof", "",
           "Not a text diff. A diff across two languages compares punctuation; this "
           "answers the question a reviewer actually has — *this rule existed, where does "
           "it live now, and what proves it still holds?*", "",
           f"**{headline(s)}**", ""]

    if s.get("broken"):
        out += [f"> {s['broken']} rule(s) could not be traced all the way to a generated "
                "method. Each says where the chain broke rather than guessing the rest.", ""]

    out += ["| Intent | Implementation | Proof |", "|---|---|---|"]
    for r in al.get("rows", []):
        intent = f"{r['rule']}<br><sub>`{r['source_class']}`"
        if r["java_method"]:
            intent += f".{r['java_method']} {r['java_lines'][0]}–{r['java_lines'][1]}"
        intent += "</sub>"

        if r["apex_method"]:
            impl = (f"`{r['target']}.{r['apex_method']}`<br>"
                    f"<sub>lines {r['apex_lines'][0]}–{r['apex_lines'][1]} · "
                    f"{r['link_confidence']} confidence</sub>")
        else:
            impl = f"— <br><sub>{r['broken_at']}</sub>"

        proof = {"replayed": f"✅ replayed<br><sub>{r['proof']}</sub>",
                 "asserted": f"~ {r['proof']}",
                 "implemented": "no test evidence",
                 "at_risk": "target failed to build",
                 "dropped": "**nothing carries this rule**",
                 "none": "—"}[r["proof_kind"]]
        out.append(f"| {intent.replace('|', chr(92) + '|')} | {impl} | {proof} |")

    out += ["", "---", "",
            "> **On the chain.** Rule → source class is recorded fact. Apex method → Java "
            "method is provenance, graded exact or normalised. Rule → *method* is keyword "
            "overlap, because the Comprehender extracts a rule from a class rather than "
            "from a line — that link is the weakest and is labelled wherever it appears. "
            "A plausible chain built on a bad match would be worse than an incomplete one, "
            "because it would be believed."]

    path = Path(output_dir) / "ALIGNMENT.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return str(path)
