"""
triage.py — which of these four hundred classes actually need a human.

The quiet killer of human-in-the-loop review is volume. Nobody reads four hundred
generated classes carefully; they read the first thirty properly, skim the next fifty,
and bulk-approve the rest — which means the review that was supposed to be the safety
net becomes a rubber stamp somewhere around file sixty. Ranking is what keeps it honest:
if the twelve that matter are at the top, the reviewer's real attention lands on them.

Everything this needs already exists by the time the Build gate opens. The radar knows
which source files carry hazards, the Critic knows what it objected to, the Comprehender
scored complexity, and the rule ledger knows how much business logic each artifact
carries. This weighs them together.

**The score is a sorting device, not a measurement.** There is no ground truth for "how
risky is this class", and any weighted sum is a judgement dressed as arithmetic. So the
number is never shown on its own — every item carries the plain-English reasons that
produced it, and a reviewer who disagrees can see exactly why it was ranked there. The
band, not the score, is what the UI leads with.
"""

from __future__ import annotations

from pathlib import Path

# Weights are deliberately coarse. Pretending to two decimal places would imply a
# precision that does not exist; what matters is that a failed build outranks a style
# nit, and that anything touching money outranks a DTO.
_W_FAILED = 100          # it did not build — nothing else about it matters yet
_W_CRITICAL_HAZARD = 30  # will breach a governor limit at realistic volume
_W_HIGH_HAZARD = 14
_W_MEDIUM_HAZARD = 4
_W_CRITIC_ERROR = 25
_W_CRITIC_WARN = 6
_W_REVIEW_FLAG = 12      # a native-product suggestion needs a human decision
_W_RULE = 3              # each business rule carried
_W_COMPLEX_HIGH = 10
_W_COMPLEX_MED = 3

# Layers whose output is mechanical. A selector or a DTO that built cleanly and carries
# no rules is genuinely routine, and saying so is what buys attention for the rest.
_MECHANICAL = {"Model", "DAO", "Utility"}

MUST_REVIEW = 40         # at or above: a human must look before this ships
ELEVATED = 12            # at or above: worth a look


def _sev(findings, *names) -> int:
    return sum(1 for f in findings or []
               if str(f.get("severity", "")).lower() in names)


def build_triage(bb) -> dict:
    """Rank every artifact by how much it needs a person. Deterministic; no model calls."""
    radar = getattr(bb, "radar", None) or {}
    # Which source files carry which hazards, so an artifact inherits the risk of the
    # code it was built from.
    hazards_by_file: dict[str, list] = {}
    hazards_by_class: dict[str, list] = {}
    for f in radar.get("findings", []):
        hazards_by_file.setdefault(Path(f["file"]).name, []).append(f)
        if f.get("source_class"):
            hazards_by_class.setdefault(f["source_class"], []).append(f)

    items = []
    for a in bb.artifacts:
        score, reasons = 0, []

        if getattr(a, "status", "") == "error":
            score += _W_FAILED
            reasons.append("did not build — needs manual migration")

        # Hazards found in this artifact's own source files.
        # Matched on file first, class name second. Either alone is fragile: an
        # artifact's sources have not always carried `file`, and a radar finding in an
        # XML file has no Java class to name.
        own, seen_ids = [], set()
        for c in a.source_classes:
            for h in (hazards_by_file.get(Path(c.get("file", "")).name, [])
                      + hazards_by_class.get(c.get("class_name", ""), [])):
                if h["id"] not in seen_ids:
                    seen_ids.add(h["id"])
                    own.append(h)
        crit = sum(1 for h in own if h["severity"] == "critical")
        high = sum(1 for h in own if h["severity"] == "high")
        med = sum(1 for h in own if h["severity"] == "medium")
        if crit:
            score += _W_CRITICAL_HAZARD * crit
            reasons.append(f"{crit} critical migration hazard(s) in its source "
                           f"({', '.join(sorted({h['rule'] for h in own if h['severity'] == 'critical'}))})")
        if high:
            score += _W_HIGH_HAZARD * high
            reasons.append(f"{high} high-severity hazard(s) in its source")
        if med:
            score += _W_MEDIUM_HAZARD * med

        errs = _sev(a.critic_findings, "error", "critical")
        warns = _sev(a.critic_findings, "warning", "warn", "medium")
        if errs:
            score += _W_CRITIC_ERROR * errs
            reasons.append(f"the Critic raised {errs} unresolved error(s)")
        if warns:
            score += _W_CRITIC_WARN * warns

        if a.review_flags:
            score += _W_REVIEW_FLAG * len(a.review_flags)
            reasons.append("flagged for review: " + "; ".join(a.review_flags)[:120])

        rules = len(a.business_rules or [])
        if rules:
            score += _W_RULE * rules
            reasons.append(f"carries {rules} business rule(s)")

        # Complexity comes from the Comprehender's read of the source.
        complexity = ""
        for c in a.source_classes:
            u = (bb.comprehensions or {}).get(c.get("class_name")) or {}
            cx = str(u.get("complexity", "")).lower()
            if cx == "high":
                complexity = "High"
                break
            if cx == "medium":
                complexity = "Medium"
        if complexity == "High":
            score += _W_COMPLEX_HIGH
            reasons.append("the source was assessed as high complexity")
        elif complexity == "Medium":
            score += _W_COMPLEX_MED

        # Some conditions are must-review on their own merits, not because a weighted
        # sum happens to clear a threshold. Tuning a weight until it crosses the line
        # would express the same policy far less clearly, and would silently stop
        # holding the moment any other weight changed.
        forced = (getattr(a, "status", "") == "error"      # it does not build
                  or crit > 0                              # breaches a limit at volume
                  or errs > 0)                             # the Critic still objects
        mechanical = (a.layer in _MECHANICAL and not reasons)
        band = ("must" if (forced or score >= MUST_REVIEW)
                else "review" if score >= ELEVATED
                else "routine")
        if mechanical and band == "routine":
            reasons.append("mechanical layer, built clean, carries no business rules")

        items.append({
            "target": a.target_name, "layer": a.layer, "score": score, "band": band,
            "reasons": reasons,
            "hazards": {"critical": crit, "high": high, "medium": med},
            "critic": {"errors": errs, "warnings": warns},
            "rules": rules, "complexity": complexity or "—",
            "sources": [c.get("class_name") for c in a.source_classes],
        })

    items.sort(key=lambda i: (-i["score"], i["target"]))
    counts = {b: sum(1 for i in items if i["band"] == b) for b in ("must", "review", "routine")}
    return {
        "items": items,
        "summary": {"total": len(items), **counts,
                    "needs_you": counts["must"] + counts["review"]},
    }


def headline(summary: dict) -> str:
    t = summary.get("total") or 0
    if not t:
        return "Nothing to review."
    need = summary.get("needs_you", 0)
    if not need:
        return f"All {t} artifact(s) look routine — nothing is flagged for close review."
    return (f"{need} of {t} artifact(s) need your attention "
            f"({summary.get('must', 0)} must-review) · {summary.get('routine', 0)} routine")


_BAND_TEXT = {
    "must": ("Must review", "Something here is broken, hazardous, or carries a decision "
                            "only a human can make."),
    "review": ("Worth a look", "Elevated risk — business rules, complexity, or Critic "
                               "warnings, but nothing blocking."),
    "routine": ("Routine", "Built clean, carries no business rules, mechanical layer. "
                           "Safe to approve in bulk."),
}


def write_triage_md(output_dir: str, triage: dict) -> str:
    """TRIAGE.md — where to spend the review hour you actually have."""
    s = triage.get("summary") or {}
    out = ["# Review Triage", "",
           "Nobody reviews four hundred classes carefully. This ranks them so the attention "
           "you do have lands on the ones that need it.", "",
           f"**{headline(s)}**", "",
           "| Band | Count | Meaning |", "|---|---|---|"]
    for band in ("must", "review", "routine"):
        title, meaning = _BAND_TEXT[band]
        out.append(f"| **{title}** | {s.get(band, 0)} | {meaning} |")
    out.append("")

    for band in ("must", "review", "routine"):
        group = [i for i in triage.get("items", []) if i["band"] == band]
        if not group:
            continue
        title = _BAND_TEXT[band][0]
        out += [f"## {title} ({len(group)})", ""]
        if band == "routine":
            out += ["Listed for completeness — these are the ones to bulk-approve.", "",
                    "| Artifact | Layer | Sources |", "|---|---|---|"]
            out += [f"| `{i['target']}` | {i['layer']} | {', '.join(i['sources'][:3])} |"
                    for i in group]
            out.append("")
            continue
        for i in group:
            out += [f"### `{i['target']}` · {i['layer']}", ""]
            for r in i["reasons"]:
                out.append(f"- {r}")
            out += ["", f"<sub>rank score {i['score']} · from "
                        f"{', '.join(i['sources'][:4]) or '—'}</sub>", ""]

    out += ["---", "",
            "> **The score is a sorting device, not a measurement.** There is no ground "
            "truth for how risky a class is, and any weighted sum is a judgement dressed "
            "as arithmetic — so every item above lists the reasons that produced its rank, "
            "and the band is what to act on. If you disagree with a placement, the reasons "
            "tell you exactly why it landed there."]

    path = Path(output_dir) / "TRIAGE.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return str(path)
