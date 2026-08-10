"""
orgfit.py — will this package actually deploy into *their* org?

Every competitor reads the source. Almost none read the destination, and that is where
the classic day-one failure comes from: a migration invents `Order__c` in an org that has
had an `Order__c` since 2019, or builds a pricing engine into an org that already has CPQ
installed. Both are found at deploy time, after the money is spent.

This reads the target org before generation and reconciles it against the plan:

    collision   the org already has an object of that name — deploying will clash, or
                worse, quietly merge into someone else's data model
    reusable    a standard object already covers this (Order, Product2, Account) and
                inventing a parallel custom object is a decision, not a default
    package     an installed package already owns this domain — CPQ present makes the
                Planner's "consider CPQ" flag a much stronger recommendation
    headroom    custom-object and field counts against the org's limits

It uses the `sf` CLI the Verify step already depends on, rather than a browser OAuth
flow: anyone who can deploy has already authorised a CLI org, so this needs no new
credentials, no new consent screen, and nothing stored. With no CLI and no authorised org
it reports that plainly and the migration proceeds unchanged — an advisory that blocks a
run when it cannot reach an org would be worse than no advisory.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

# Standard objects that a custom equivalent usually should not duplicate. The mapping is
# from the Hybris type a migration tends to produce to the Salesforce object that already
# exists for it.
_STANDARD = {
    "ORDER": ("Order", "Salesforce has a standard Order object with pricing, contracts and "
                       "order products already modelled."),
    "ORDERENTRY": ("OrderItem", "Standard OrderItem is the line-item object for Order."),
    "PRODUCT": ("Product2", "Standard Product2 carries pricing via PricebookEntry."),
    "CUSTOMER": ("Account", "Customers are usually Accounts (B2B) or Person Accounts (B2C)."),
    "USER": ("User", "Standard User already exists and cannot be replaced."),
    "ADDRESS": ("Address", "Standard address fields exist on Account and Contact."),
    "CART": ("Order", "A cart is commonly a draft Order rather than a new object."),
    "PRICE": ("PricebookEntry", "Pricing belongs on PricebookEntry against a Pricebook2."),
}

# An installed package that already owns a domain changes the recommendation from
# "consider this" to "you already own this".
_PACKAGES = {
    "sbaa": "Salesforce CPQ (Advanced Approvals)",
    "SBQQ": "Salesforce CPQ",
    "blng": "Salesforce Billing",
    "vlocity": "Vlocity / Industries",
}


def sf_available() -> bool:
    return shutil.which("sf") is not None


def _sf_json(args: list[str], timeout: int = 60) -> dict | None:
    """Run an `sf` command that returns JSON. None on any failure — this is advisory."""
    try:
        p = subprocess.run(["sf", *args, "--json"], capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0 or not p.stdout.strip():
            return None
        return json.loads(p.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


def read_org(target_org: str = "") -> dict | None:
    """What the destination org already contains. None when there is no org to read."""
    if not sf_available():
        return None
    org_args = ["--target-org", target_org] if target_org else []

    info = _sf_json(["org", "display", *org_args])
    if not info or info.get("status") != 0:
        return None
    result = info.get("result") or {}

    listing = _sf_json(["sobject", "list", "--sobject", "all", *org_args])
    names = [n for n in ((listing or {}).get("result") or []) if isinstance(n, str)]

    limits = _sf_json(["limits", "api", "display", *org_args]) or {}
    lim = {row.get("name"): row for row in (limits.get("result") or [])
           if isinstance(row, dict)}

    return {
        "username": result.get("username", ""),
        "instance_url": result.get("instanceUrl", ""),
        "api_version": result.get("apiVersion", ""),
        "is_scratch": bool(result.get("isScratch")),
        "objects": names,
        "custom_objects": [n for n in names if n.endswith("__c")],
        "namespaces": sorted({n.split("__")[0] for n in names
                              if n.count("__") >= 2}),
        "limits": {k: {"max": v.get("max"), "remaining": v.get("remaining")}
                   for k, v in lim.items()},
    }


def assess(planned_schema: dict, org: dict | None, plan_items=None) -> dict:
    """Reconcile what we intend to create against what the org already has."""
    if org is None:
        return {"connected": False,
                "reason": ("no Salesforce CLI on PATH" if not sf_available()
                           else "no authorised org — run `sf org login web`"),
                "findings": [], "org": None,
                "summary": {"total": 0, "collision": 0, "reusable": 0, "package": 0,
                            "headroom": 0}}

    existing = {n.lower() for n in org.get("objects", [])}
    findings = []

    for obj in sorted(planned_schema or {}):
        api = obj if obj.endswith("__c") else f"{obj}__c"
        base = obj.replace("__c", "").upper()

        if api.lower() in existing:
            findings.append({
                "kind": "collision", "severity": "critical", "object": api,
                "detail": f"The org already has `{api}`. Deploying will either fail or merge "
                          "into an existing object that other code and data depend on.",
                "fix": "Rename the generated object, or map onto the existing one deliberately "
                       "after checking its fields.",
            })
            continue

        std = _STANDARD.get(base)
        if std and std[0].lower() in existing:
            findings.append({
                "kind": "reusable", "severity": "high", "object": api,
                "detail": f"`{std[0]}` already exists in this org. {std[1]}",
                "fix": f"Map this onto `{std[0]}` rather than creating `{api}`, or record why a "
                       "parallel custom object is wanted.",
            })

    for ns, name in _PACKAGES.items():
        if ns in org.get("namespaces", []):
            findings.append({
                "kind": "package", "severity": "high", "object": name,
                "detail": f"{name} is installed in this org, so it already owns the domain the "
                          "Planner flagged for review.",
                "fix": f"Configure {name} instead of deploying hand-written Apex for it — the "
                       "converted code is still there as a reference for the rules it encodes.",
            })

    lim = org.get("limits", {}) or {}
    for key, label in (("CustomObjects", "custom object"), ("CustomFields", "custom field")):
        row = lim.get(key)
        if not row or row.get("remaining") is None:
            continue
        need = len(planned_schema or {}) if key == "CustomObjects" else sum(
            len((v or {}).get("fields", {})) for v in (planned_schema or {}).values())
        if need > (row["remaining"] or 0):
            findings.append({
                "kind": "headroom", "severity": "critical", "object": label,
                "detail": f"This migration needs about {need} {label}(s); the org has "
                          f"{row['remaining']} of {row['max']} left.",
                "fix": "Raise the limit with Salesforce, or reduce scope before deploying.",
            })

    order = {"critical": 0, "high": 1, "medium": 2}
    findings.sort(key=lambda f: (order.get(f["severity"], 9), f["object"]))
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["kind"]] = counts.get(f["kind"], 0) + 1

    return {
        "connected": True, "reason": "",
        "org": {k: org.get(k) for k in ("username", "instance_url", "api_version",
                                        "is_scratch", "namespaces")},
        "existing_custom_objects": len(org.get("custom_objects", [])),
        "findings": findings,
        "summary": {"total": len(findings),
                    **{k: counts.get(k, 0) for k in ("collision", "reusable", "package", "headroom")}},
    }


def headline(fit: dict) -> str:
    if not fit.get("connected"):
        return f"Target org not inspected — {fit.get('reason', 'unavailable')}."
    s = fit.get("summary") or {}
    if not s.get("total"):
        return f"Target org looks clear — nothing in {fit['org']['username']} conflicts with this plan."
    bits = [f"{s[k]} {k}" for k in ("collision", "reusable", "package", "headroom") if s.get(k)]
    return f"{s['total']} target-org issue(s) — " + ", ".join(bits)


def write_orgfit_md(output_dir: str, fit: dict) -> str:
    out = ["# Target Org Fit", "",
           "Read from the destination org before generating, so a deploy failure is found "
           "now rather than on day one.", "",
           f"**{headline(fit)}**", ""]

    if not fit.get("connected"):
        out += ["No org was inspected, so this migration was planned against the source alone. "
                "Connect one with `sf org login web` and re-run to reconcile against what the "
                "org already contains.", ""]
    else:
        o = fit["org"]
        out += [f"- Org: `{o['username']}`" + (" (scratch)" if o.get("is_scratch") else ""),
                f"- API version: {o.get('api_version') or 'unknown'}",
                f"- Existing custom objects: {fit.get('existing_custom_objects', 0)}",
                f"- Installed namespaces: {', '.join(o.get('namespaces') or []) or 'none'}", ""]
        for f in fit.get("findings", []):
            out += [f"### {f['kind']} · `{f['object']}`", "",
                    f["detail"], "", f"**Fix:** {f['fix']}", ""]

    out += ["---", "",
            "> Reading the destination is what separates \"here is a package\" from \"here is a "
            "package that will deploy into *your* org\". A name collision found here costs a "
            "rename; found at deploy time it costs the deploy."]

    path = Path(output_dir) / "ORG_FIT.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return str(path)
