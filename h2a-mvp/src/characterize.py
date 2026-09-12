"""
characterize.py — golden-master parity from the customer's own test suite.

The rule ledger can say *"a test plausibly covers this rule"*. It can never say
*"this behaves the same"*, because it compares words, not behaviour. This module is
what closes that gap.

The idea is unglamorous and that is exactly why it works: a customer's existing test
suite is a **recorded log of how their system actually behaved**. `assertEquals(new
BigDecimal("180.00"), svc.applySpendDiscount(new BigDecimal("200.00")))` is not an
opinion — it is a fact about the old system, checked in and CI-verified for years.
Mine those facts, replay them against the generated code, and the claim upgrades from
"the AI thinks it's equivalent" to:

    340 recorded behaviours from your own suite · 332 reproduce · 8 differ — here they are.

**The catch, stated up front.** The migration deliberately reshapes code: a single-record
`placeOrder(customer, entries)` becomes a bulkified `createOrders(List<OrderRequest>)`.
So most behaviours cannot be replayed by calling the same method with the same
arguments. Each one is therefore classified:

    direct   — the signature survived; the replay is generated deterministically, and
               every value in it is a recorded fact. This is the strong evidence.
    adapter  — the shape changed; bridging code is needed to express the old call
               against the new signature. The *expected values* are still recorded
               facts, but the plumbing around them is generated, so it is weaker.
    manual   — mocks, object graphs or framework state we will not pretend to port.

Nothing here guesses an expected value. A behaviour we cannot faithfully replay is
reported as such rather than quietly dropped — an honest `manual` row is worth more
than a green tick that means nothing.

**Where the platforms live.** Reading a test suite is a source skill; writing a replay is
a target skill; deciding what a replay is *worth* is neither. So this module keeps the
third and delegates the other two:

    adapters/java_junit_mining.py     JUnit → recorded facts        (source side)
    adapters/apex_characterization.py recorded facts → Apex tests   (target side)

which is why nothing below names a language.
"""

from __future__ import annotations


# ── who does the platform-specific halves ─────────────────────────────────────

def _source():
    """The running pipeline's source adapter — or the shipped one outside a run."""
    from src import pipeline
    pipeline.ensure_registered()
    return pipeline.active_or_shipped().source


def _target():
    """The running pipeline's target adapter — or the shipped one outside a run."""
    from src import pipeline
    return pipeline.active_or_shipped().target


def behavior_id(test_class: str, test_method: str, n: int) -> str:
    """Stable id so a behaviour can be tracked across runs and reports.

    Neutral on purpose: every source adapter mints ids the same way, so a behaviour keeps
    its id across pipelines and across the reports that cite it.
    """
    import hashlib
    return "B-" + hashlib.md5(f"{test_class}#{test_method}#{n}".encode("utf-8")).hexdigest()[:8]


def mine_behaviors(test_classes: list[dict]) -> list[dict]:
    """Extract every recorded input→output fact from the source's test suite."""
    return _source().mine_behaviours(test_classes)


# ── mapping a recorded behaviour onto the generated code ──────────────────────

def plan_replay(behaviors: list[dict], artifacts: list) -> list[dict]:
    """Decide, per behaviour, whether it can be replayed and how strong that replay is.

    The classification is the honest part of this module. `direct` means every value in
    the generated test is a recorded fact and the call shape survived the migration —
    that is real proof. `adapter` and `manual` are not, and are labelled so.
    """
    target = _target()
    by_source: dict[str, object] = {}
    for a in artifacts or []:
        for c in a.source_classes:
            if c.get("class_name"):
                by_source[c["class_name"]] = a

    planned = []
    for b in behaviors:
        art = by_source.get(b["source_class"])
        row = dict(b, target=None, mode="manual", reason="")

        if art is None:
            row["reason"] = "no generated artifact carries this class"
            planned.append(row)
            continue

        row["target"] = art.target_name
        if getattr(art, "status", "") == "error":
            row["reason"] = "the target failed to generate"
            planned.append(row)
            continue

        found = target.find_method(art.main_class or "", b["target_method"])
        # Expressibility is a fact about the *recording*, not about any target: a value
        # the miner could not reduce to a literal is an object graph or a live reference,
        # and no target can restate it.
        expressible = (all(a.get("value") is not None for a in b["args"])
                       and (b["expects_exception"] or (b["expected"] or {}).get("value") is not None))

        if found and expressible:
            row["mode"], row["static"] = "direct", found["static"]
            row["reason"] = "signature survived the migration; every value is a recorded fact"
        elif found:
            row["mode"] = "adapter"
            row["reason"] = "method exists, but the arguments need bridging code to express"
        else:
            row["mode"] = "adapter"
            row["reason"] = (f"no method named {b['target_method']} in {art.target_name} — "
                             "the migration reshaped this call (e.g. bulkified)")
        planned.append(row)
    return planned


def is_runnable(r: dict) -> bool:
    """A behaviour we can emit as an executable test — replayed or bridged."""
    return r["mode"] == "direct" or bool(r.get("bridge"))


def generate_apex(planned: list[dict]) -> dict[str, str]:
    """Emit one characterization test class per target artifact.

    Kept under its original name because the orchestrator, the reports and the golden
    manifest all know it; the Apex is now written by the target adapter.
    """
    by_target: dict[str, list[dict]] = {}
    for r in planned:
        if is_runnable(r):
            by_target.setdefault(r["target"], []).append(r)
    return _target().emit_characterization(by_target)


def summarise(planned: list[dict]) -> dict:
    counts = {m: 0 for m in ("direct", "adapter", "manual")}
    for r in planned:
        counts[r["mode"]] = counts.get(r["mode"], 0) + 1
    bridged = sum(1 for r in planned if r.get("bridge"))
    runnable = counts["direct"] + bridged
    total = len(planned)
    return {"total": total, **counts, "bridged": bridged, "runnable": runnable,
            "replayable_pct": round(100.0 * runnable / total) if total else None}


def headline(s: dict) -> str:
    t = s.get("total") or 0
    if not t:
        return ("No tests found in the source — characterization needs the customer's "
                "existing test suite as its source of recorded behaviour.")
    parts = [f"{s['direct']} direct"] if s.get("direct") else []
    if s.get("bridged"):
        parts.append(f"{s['bridged']} bridged")
    unbridged = s.get("adapter", 0) - s.get("bridged", 0)
    tail = []
    if unbridged:
        tail.append(f"{unbridged} unbridged")
    if s.get("manual"):
        tail.append(f"{s['manual']} manual")
    return (f"{s.get('runnable', 0)}/{t} recorded behaviours replay against the generated "
            f"{_target().code_language} ({s.get('replayable_pct', 0)}%"
            + (" — " + ", ".join(parts) if parts else "") + ")"
            + (" · " + ", ".join(tail) if tail else ""))


def write_characterization_md(output_dir: str, planned: list[dict], emitted: dict[str, str]) -> str:
    from pathlib import Path

    lang = _target().code_language
    s = summarise(planned)
    out = ["# Characterization Report — replaying your own tests", "",
           "Your existing test suite is a recorded log of how the legacy system actually",
           f"behaved. This replays those recorded facts against the generated {lang}.", "",
           f"**{headline(s)}**", "",
           "| Mode | Count | What it means | How much to trust it |",
           "|---|---|---|---|",
           f"| `direct` | {s['direct']} | The signature survived; the replay calls the same method "
           "with the same recorded values | **Strong** — a failure is a real behavioural difference |",
           f"| `adapter` | {s['adapter']} | The migration reshaped the call (e.g. single-record → "
           "bulk), so bridging code is needed | Medium — expected values are still recorded facts, "
           "but the plumbing around them is not |",
           f"| `manual` | {s['manual']} | Mocks, object graphs or framework state we will not "
           "pretend to port | None — these need a human |", ""]

    if emitted:
        out += [f"## Generated test classes ({len(emitted)})", "",
                "Deployed with the rest of the project; run them in a scratch org to get the "
                "reproduce/differ verdict.", ""]
        out += [f"- `{name}.cls` — {sum(1 for r in planned if r['mode'] == 'direct' and r['target'] + 'CharacterizationTest' == name)} recorded behaviour(s)"
                for name in sorted(emitted)]
        out.append("")

    for mode, blurb in (("direct", "replayed automatically"),
                        ("adapter", "need bridging code before they can run"),
                        ("manual", "cannot be replayed automatically")):
        group = [r for r in planned if r["mode"] == mode]
        if not group:
            continue
        out += [f"## {mode} — {len(group)} behaviour(s) {blurb}", "",
                "| Id | Recorded behaviour | Legacy call | Now | Note |", "|---|---|---|---|---|"]
        for r in group:
            args = ", ".join(a["source"] for a in r["args"]).replace("|", "\\|")
            exp = r["expects_exception"] or (r["expected"] or {}).get("source", "—")
            legacy = f"`{r['source_class']}.{r['target_method']}({args})` → `{exp}`".replace("|", "\\|")
            out.append(f"| `{r['id']}` | {r['label']} | {legacy} | "
                       f"`{r['target'] or '—'}` | {r['reason']} |")
        out.append("")

    out += ["---", "",
            "> **Why this matters.** Every other check in this migration asks whether the new code ",
            "> *looks* right. This asks whether it *behaves* the same, against evidence your team ",
            "> wrote and trusted for years. A `direct` failure is not a style opinion — it is proof ",
            "> that something changed."]

    path = Path(output_dir) / "CHARACTERIZATION.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return str(path)


# ── bridging a reshaped call ──────────────────────────────────────────────────

def build_adapters(planned: list[dict], *, offline: bool = False, model: str | None = None,
                   apex_of: dict[str, str] | None = None) -> list[dict]:
    """Ask the model to bridge reshaped calls — arrange and act only.

    The expected value is never sent for the model to echo back and never accepted from
    it. That is what keeps a bridged test evidence rather than a second opinion.

    The prompt and the schema belong to the target; the cost accounting, the retries and
    the refusal to accept a bridge that writes its own assertion belong here, so every
    target inherits them rather than re-implementing them.
    """
    from src.llm import call_structured

    target = _target()
    code_of = apex_of or {}
    by_target: dict[str, list[dict]] = {}
    for r in planned:
        if r["mode"] != "adapter" or not r.get("target"):
            continue
        # No point bridging a call whose recorded *answer* we cannot state as a literal —
        # there would be nothing to assert against, and asserting nothing is worse than
        # admitting the gap. Those stay for a human.
        if not r["expects_exception"] and (r["expected"] or {}).get("value") is None:
            r["reason"] = "the recorded return value is an object graph, not a value we can assert"
            continue
        by_target.setdefault(r["target"], []).append(r)
    if not by_target:
        return planned

    for name, rows in by_target.items():
        req = target.bridge_request(name, code_of.get(name, ""), rows)
        try:
            res = call_structured(
                f"characterize_{name}", req["prompt"], req["schema"], req.get("max_tokens", 4000),
                offline=offline, model=model, system_prompt=req["system"],
            )
            parsed = res.get("parsed")
            raw = (parsed or {}).get("bridges") if isinstance(parsed, dict) else None
            # A provider can return anything — the mock stub returns placeholder shapes
            # that are nothing like this schema. Only dict rows with an id are usable.
            bridges = {b["id"]: b for b in (raw or [])
                       if isinstance(b, dict) and b.get("id")}
        except Exception as e:
            for r in rows:
                r["reason"] = f"{r['reason']} (bridging unavailable: {e})"
            continue

        forbidden = req.get("forbidden") or ()
        for r in rows:
            b = bridges.get(r["id"])
            if not b or not b.get("feasible"):
                r["reason"] = (b or {}).get("note") or r["reason"]
                continue
            setup, expr = (b.get("setup") or "").strip(), (b.get("result_expr") or "").strip()
            if not setup or not expr:
                continue
            if any(f in setup or f in expr for f in forbidden):
                r["reason"] = "bridge rejected — it tried to write its own assertion"
                continue
            r["bridge"] = {"setup": setup, "result_expr": expr, "note": b.get("note", "")}
            r["reason"] = b.get("note") or "bridged onto the reshaped signature"
    return planned
