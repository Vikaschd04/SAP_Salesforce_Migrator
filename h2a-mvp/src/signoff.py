"""
signoff.py — the audit, as a deliverable.

Every migration ends in an audit. Somebody has to answer *"who approved this, on what
evidence, and what exactly did they approve?"* — usually months later, usually from
memory, usually reconstructed from Slack. Every fact needed to answer it properly already
exists by the end of a run and has never been assembled in one place. This assembles it.

**What makes it worth signing is what it refuses to say.** The temptation in a document
like this is to total everything up and print a number that looks like assurance. So:

- an unsupervised run is reported as *unreviewed*, not approved. `gate=None` approves
  automatically so the CLI and the extension can run unattended, and that is a
  convenience, not a decision. A contract that cannot tell a named reviewer from nobody
  would be signed either way, which is worse than having no contract.
- coverage figures carry the basis that produced them. "94% traced" from exact symbol
  matching and "94% traced" from normalised-name inference are different claims.
- anything unproven is listed under what this does **not** certify, in the same document
  and at the same size — not omitted and not relegated to a footnote.

The result is a document whose value comes from being trustworthy rather than reassuring.
A reader who only skims the headline should come away with the *less* confident reading,
never the more confident one.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

# The three gates, in the order a run reaches them, with what approving each one means.
_GATES = {
    "discovery": ("Discovery", "the repository analysis is right — this is the estate, "
                               "these are its hazards, this is what it will cost"),
    "plan": ("Plan", "the conversion plan is right — this is what gets built, "
                     "what gets skipped, and why"),
    "build": ("Build", "the generated code is fit to take forward"),
}


def _fmt_when(iso: str) -> str:
    try:
        return dt.datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, TypeError):
        return iso or "—"


def build_signoff(bb, *, accounting: dict | None = None, cost: dict | None = None,
                  recipe: str = "", verified: dict | None = None) -> dict:
    """Assemble the contract from what the run already recorded. No model calls."""
    approvals = list(getattr(bb, "approvals", []) or [])
    ledger = bb.completeness_ledger()
    rules = (getattr(bb, "rule_ledger", None) or {}).get("summary") or {}
    chars = (getattr(bb, "characterization", None) or {}).get("summary") or {}
    radar = (getattr(bb, "radar", None) or {}).get("summary") or {}

    from src.provenance import build_provenance
    prov = build_provenance(bb).get("summary") or {}

    counts: dict[str, int] = {}
    for r in ledger:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1

    reviewed = [a for a in approvals if a.get("supervised")]
    human_gates = sorted({a["gate"] for a in reviewed})
    reviewers = sorted({a["actor"] for a in reviewed if a.get("actor")})

    # Deploy verification is the only claim here that a Salesforce org made rather than
    # this tool, which is exactly why it is the one that carries weight.
    v = verified or {}
    org_verified = bool(v.get("verified"))

    caveats = _caveats(counts, rules, chars, prov, radar, approvals, org_verified)

    contract = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "input_dir": bb.input_dir,
        "output_dir": bb.output_dir,
        "recipe": recipe,
        "supervised": bool(reviewed),
        "gates_reviewed_by_a_human": human_gates,
        "gates_auto_approved": sorted({a["gate"] for a in approvals
                                       if not a.get("supervised")}),
        "reviewers": reviewers,
        "approvals": approvals,
        "completeness": counts,
        "rules": rules,
        "characterization": chars,
        "provenance": prov,
        "hazards": radar,
        "org_verified": org_verified,
        "verification": v,
        "cost": cost or {},
        "requests": (accounting or {}).get("requests", 0),
        "caveats": caveats,
    }
    # Over the substance, not the prose: two runs that certify the same facts produce the
    # same id, and a changed fact changes it. Cheap to check, hard to edit around.
    contract["contract_id"] = hashlib.sha256(
        repr([contract[k] for k in ("input_dir", "recipe", "approvals", "completeness",
                                    "rules", "characterization", "provenance",
                                    "org_verified")]).encode("utf-8")
    ).hexdigest()[:16]
    return contract


def _caveats(counts, rules, chars, prov, radar, approvals, org_verified) -> list[str]:
    """Everything this document does not certify. Assembled from the same data as the
    claims, so it cannot drift out of step with them."""
    out = []
    if not any(a.get("supervised") for a in approvals):
        out.append("**No human reviewed any stage of this run.** Every gate was approved "
                   "automatically because the run was unattended. Nothing below has been "
                   "checked by a person.")
    else:
        missing = [g for g in _GATES if g not in {a["gate"] for a in approvals
                                                  if a.get("supervised")}]
        if missing:
            out.append("Auto-approved without a reviewer: "
                       + ", ".join(_GATES[g][0] for g in missing) + ".")

    if counts.get("unaccounted"):
        out.append(f"{counts['unaccounted']} source class(es) are unaccounted for — not "
                   "represented anywhere in the output.")
    if counts.get("overwritten"):
        out.append(f"{counts['overwritten']} source class(es) map to a file that another "
                   "artifact also wrote, so their logic may not be in the output.")
    if counts.get("unreadable"):
        out.append(f"{counts['unreadable']} file(s) could not be read or parsed and must "
                   "be migrated by hand.")

    dropped = rules.get("dropped") or 0
    at_risk = rules.get("at_risk") or 0
    if dropped:
        out.append(f"{dropped} extracted business rule(s) are carried by no generated "
                   "artifact.")
    if at_risk:
        out.append(f"{at_risk} business rule(s) are in artifacts that did not build.")

    total_rules = rules.get("total") or 0
    asserted = rules.get("asserted") or 0
    if total_rules and asserted < total_rules:
        out.append(f"{total_rules - asserted} of {total_rules} business rule(s) have no "
                   "test asserting them. They are implemented, not proven.")

    replayed = chars.get("replayed") or 0
    total_beh = chars.get("total") or 0
    if total_beh and replayed < total_beh:
        out.append(f"{total_beh - replayed} of {total_beh} recorded behaviour(s) could "
                   "not be replayed against the generated Apex.")
    if not total_beh:
        out.append("No recorded behaviours were available, so nothing here is backed by "
                   "golden-master parity against the original implementation.")

    if prov.get("java_without_apex"):
        out.append(f"{prov['java_without_apex']} Java method(s) have no traceable Apex "
                   "counterpart. Some are inlined helpers; some may be lost logic.")
    if prov.get("apex_without_origin"):
        out.append(f"{prov['apex_without_origin']} generated method(s) trace to no Java "
                   "origin — scaffolding, or invented.")

    crit = (radar.get("critical") or 0) + (radar.get("high") or 0)
    if crit:
        out.append(f"{crit} critical/high migration hazard(s) were found in the source. "
                   "Conversion does not resolve them.")

    if not org_verified:
        out.append("**This code was never deployed to a Salesforce org.** It has not been "
                   "compiled by Salesforce, so it is not known to be deployable.")
    return out


def headline(c: dict) -> str:
    if not c.get("supervised"):
        return "Unreviewed — no human approved any stage of this run."
    who = ", ".join(c["reviewers"]) if c["reviewers"] else "an unnamed reviewer"
    gates = len(c["gates_reviewed_by_a_human"])
    tail = "deploy-verified against a Salesforce org" if c["org_verified"] \
        else "not deploy-verified"
    return f"{gates} of 3 gate(s) approved by {who} · {tail}"


def write_signoff_md(output_dir: str, c: dict) -> str:
    out = ["# Migration Sign-Off Contract", "",
           f"**{headline(c)}**", "",
           f"<sub>Contract `{c['contract_id']}` · generated {_fmt_when(c['generated_at'])} · "
           f"recipe `{c.get('recipe') or 'n/a'}`</sub>", "",
           "This records what was migrated, who approved it, and what evidence existed at "
           "the time. It is written to be checked rather than to reassure — the section on "
           "what it does *not* certify is the same size as the rest, and deliberately so.",
           ""]

    if not c.get("supervised"):
        out += ["> 🚨 **This run was unattended.** Every gate was approved automatically "
                "so the run could proceed without a person. That is a convenience, not a "
                "decision, and nothing in this document has been reviewed by anyone.", ""]

    # ── 1. Approvals ──
    out += ["## 1. Approvals", "",
            "| Gate | What approving it means | Decision | By | When |",
            "|---|---|---|---|---|"]
    for a in c["approvals"]:
        title, meaning = _GATES.get(a["gate"], (a["gate"], "—"))
        who = a.get("actor") or ("_no reviewer_" if not a.get("supervised") else "_unnamed_")
        out.append(f"| **{title}** | {meaning} | {a['action']} | {who} | "
                   f"{_fmt_when(a.get('at', ''))} |")
    if not c["approvals"]:
        out.append("| _No review gates were opened_ | — | — | _nobody_ | — |")
    out.append("")
    for a in c["approvals"]:
        if a.get("note"):
            out.append(f"- <sub>**{_GATES.get(a['gate'], (a['gate'],))[0]}** — {a['note']}</sub>")
    out.append("")

    # ── 2. What was migrated ──
    comp = c["completeness"]
    out += ["## 2. What was migrated", "",
            "| Outcome | Count | Meaning |", "|---|---|---|"]
    meanings = {
        "converted": "converted in full",
        "flagged": "converted in full **and** carries a native-product review suggestion",
        "skipped": "no business logic to preserve (each with a recorded reason)",
        "unaccounted": "**not represented in the output — investigate**",
        "overwritten": "**another artifact wrote the same file; logic may be missing**",
        "unreadable": "**could not be read or parsed — migrate by hand**",
    }
    for k in ("converted", "flagged", "skipped", "overwritten", "unaccounted", "unreadable"):
        if comp.get(k):
            out.append(f"| `{k}` | {comp[k]} | {meanings[k]} |")
    out.append("")

    # ── 3. Evidence ──
    out += ["## 3. Evidence", "", "| Claim | Figure | What produced it |", "|---|---|---|"]
    r, ch, pr = c["rules"], c["characterization"], c["provenance"]
    if r.get("total"):
        out.append(f"| Business rules carried | {r.get('implemented', 0) + r.get('asserted', 0)}"
                   f"/{r['total']} | extracted per class by the Comprehender, then matched "
                   "against generated code |")
        out.append(f"| …with a test asserting them | {r.get('asserted', 0)}/{r['total']} | "
                   "generated test source referencing the rule's terms |")
    if ch.get("total"):
        out.append(f"| Recorded behaviours replayed | {ch.get('replayed', 0)}/{ch['total']} | "
                   "mined from the original JUnit suite and replayed against the Apex |")
    if pr.get("methods"):
        # Spelled out rather than "the rest by normalised name", which reads as a
        # reassurance when the linked count is zero.
        exact, linked = pr.get("high", 0), pr.get("linked", 0)
        basis = (f"{exact} by exact name, {linked - exact} by normalised name"
                 if linked else "nothing matched in either direction")
        out.append(f"| Methods traced to origin | {linked}/{pr['methods']} "
                   f"({pr.get('coverage', 0)}%) | symbols located in both texts — "
                   f"{basis} |")
    out.append(f"| Deploy-verified | {'yes' if c['org_verified'] else '**no**'} | "
               + ("validate-only deploy accepted by a Salesforce org |"
                  if c["org_verified"] else "not attempted — no org was connected |"))
    cost = c.get("cost") or {}
    if cost.get("total_usd") is not None:
        from src import pricing
        out.append(f"| Spend | {pricing.fmt(cost['total_usd'])} | "
                   f"{c.get('requests', 0)} model call(s)"
                   + (" — a floor, some models are unpriced |" if not cost.get("priced", True)
                      else " |"))
    out.append("")

    # ── 4. What this does not certify ──
    out += ["## 4. What this does **not** certify", ""]
    if c["caveats"]:
        out += [f"- {x}" for x in c["caveats"]]
    else:
        out.append("- Nothing outstanding was recorded. This is unusual; read sections 2 "
                   "and 3 rather than relying on this line.")
    out += ["",
            "> A migration is proven by evidence, not by assertion. Everything above is "
            "either a fact the tool observed or a claim with its basis named — and the "
            "gaps are listed here at the same size as the claims, because a document that "
            "buried them would be worth exactly as much as the burying.", "",
            "---", "",
            "## Signature", "",
            "| | |", "|---|---|",
            "| **Contract** | `" + c["contract_id"] + "` |",
            f"| **Reviewer(s)** | {', '.join(c['reviewers']) or '_none — unattended run_'} |",
            f"| **Source** | `{c['input_dir']}` |",
            f"| **Output** | `{c['output_dir']}` |",
            "| **Signed** | ______________________  Date: ____________ |", "",
            "<sub>The contract id is a hash over the facts certified above, not over this "
            "document's wording. Re-running the same migration with the same outcome "
            "reproduces it; any certified fact changing does not.</sub>"]

    path = Path(output_dir) / "SIGN_OFF.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return str(path)
