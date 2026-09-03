"""
forecast.py — what this run will cost, before anything is charged.

Nobody approves a migration of a real estate without a number, and "we'll tell you
afterwards" is not an answer anyone accepts. This produces one from the scan alone: no
model calls, no spend, available at the Discovery gate — which is the last moment before
the first billable token.

**It reports a range, and that is the honest part.** A single figure implies a precision
that does not exist: output length varies with how much the model decides to say, repair
loops fire unpredictably, and provider latency is not ours to control. A point estimate
would be wrong in a way that looks authoritative, so the low and high bounds are shown
together and the assumptions are listed alongside them.

The per-call sizes below are measured, not assumed — taken from instrumented runs over
the reference corpus (17 classes, ~30 KB of source). They will drift as prompts change;
they are constants in one place precisely so that drift is visible and fixable.
"""

from __future__ import annotations

from src import pricing

# ── per-pipeline profiles ─────────────────────────────────────────────────────
#
# Every number below was measured on **one** platform pair, and a forecast is only worth
# reading if it says which. Quoting a PHP→Java migration from Java→Apex measurements is a
# figure carrying a confidence nothing supports — and the forecast is what a cost cap gets
# set against, so an over-confident one is not a presentation problem.
#
# `measured` is the load-bearing field. A profile that is False is a *starting point*
# carried over from the pair we have run, and the forecast says so in its own assumptions
# rather than letting the range speak for itself. [4.3]


class Profile:
    """Constants for one platform pair."""

    def __init__(self, *, measured, basis, chars_per_token, mechanical_layers,
                 comprehend_overhead=1400, generate_overhead=3200, critic_overhead=2600,
                 plan_overhead=900, out_low=0.30, out_high=0.65,
                 repair_low=0.10, repair_high=0.35):
        self.measured = measured
        self.basis = basis
        self.chars_per_token = chars_per_token
        self.mechanical_layers = set(mechanical_layers)
        self.comprehend_overhead = comprehend_overhead
        self.generate_overhead = generate_overhead
        self.critic_overhead = critic_overhead
        self.plan_overhead = plan_overhead
        self.out_low, self.out_high = out_low, out_high
        self.repair_low, self.repair_high = repair_low, repair_high


#: The shipped pair's numbers, and the neutral fallback. A *specific* pair's profile is
#: registered with its pipeline (see `pipeline.py`), because per-pair measurements are
#: platform knowledge and this module is not allowed to hold any — the purity ratchet
#: caught exactly that when the table lived here. [4.3]
DEFAULT_PROFILE = Profile(
    measured=True,
    basis="instrumented runs over the reference corpus (17 classes, ~30 KB of source)",
    chars_per_token=4,
    mechanical_layers={"Model", "DAO", "Utility"},
)


def profile_for(pipeline_id: str = "") -> Profile:
    """The running pipeline's own profile, or the default.

    Asked of the pipeline rather than looked up here: which numbers apply to a pair is
    knowledge about that pair, and an assurance module that held a table of them would be
    holding platform knowledge by another name.
    """
    from src import pipeline as _pl
    from src import runctx

    try:
        _pl.ensure_registered()
        pid = pipeline_id or runctx.pipeline_id() or ""
        p = _pl.get(pid) if pid else _pl.default_pipeline()
        return getattr(p, "forecast_profile", None) or DEFAULT_PROFILE
    except Exception:
        return DEFAULT_PROFILE


# Seconds per call, wall clock, including provider latency. Frontier-tier generation is
# markedly slower than cheap-tier classification. Latency is the provider's, not the
# platform pair's, so this is not per-profile.
_SECS_CHEAP = (2.0, 6.0)
_SECS_FRONTIER = (8.0, 25.0)

# Review effort. A mechanical artifact is a glance; one carrying business rules is not.
_REVIEW_MINS_ROUTINE = (1.0, 3.0)
_REVIEW_MINS_INVOLVED = (8.0, 20.0)


def _tier_models(config: dict) -> tuple[str, str]:
    """(cheap, frontier) model ids actually in play for this configuration."""
    agentic = (config or {}).get("agentic") or {}
    routing = agentic.get("routing") or {}
    default = (config or {}).get("model") or "claude-opus-4-8"
    if not routing.get("enabled"):
        return default, default
    models = routing.get("models") or {}
    return models.get("cheap", default), models.get("frontier", default)


def _cost(model: str, tin: int, tout: int, config: dict | None = None) -> float | None:
    return pricing.cost_of(model, prompt_tokens=tin, completion_tokens=tout, config=config)


def forecast(classes: list[dict], targets: int, config: dict,
             *, already_done: int = 0, provider: str = "") -> dict:
    """Estimate spend, wall-clock and review effort from the scan alone."""
    prof = profile_for()
    config = config or {}
    n_classes = max(0, len(classes) - already_done)
    n_targets = max(0, targets - already_done)
    domains = max(1, round(n_targets / 2)) if n_targets else 0
    critic_on = bool(((config.get("agentic") or {}).get("critic", True)))

    src_chars = sum(len(c.get("source") or "") for c in classes)
    avg_class = (src_chars // max(1, len(classes))) if classes else 0
    # A target is built from more than one class (an interface plus its Default* impl,
    # plus any facades folded in), so its prompt carries more source than one class.
    avg_target_src = int(avg_class * 1.8)

    max_tokens = config.get("max_tokens") or {}
    out_comprehend = max_tokens.get("comprehend", 800)
    out_generate = max_tokens.get("generate", 8000)

    cheap, frontier = _tier_models(config)

    calls = []
    if n_classes:
        calls.append(("comprehend", cheap, n_classes,
                      (avg_class + prof.comprehend_overhead), out_comprehend, _SECS_CHEAP))
    if domains:
        calls.append(("plan", cheap, domains, prof.plan_overhead + avg_class, 1200, _SECS_CHEAP))
    if n_targets:
        calls.append(("generate", frontier, n_targets,
                      avg_target_src + prof.generate_overhead, out_generate, _SECS_FRONTIER))
        if critic_on:
            calls.append(("critic", frontier, n_targets,
                          avg_target_src + prof.critic_overhead, 1500, _SECS_FRONTIER))

    stages, lo_usd, hi_usd, lo_s, hi_s, tin_tot, unpriced = [], 0.0, 0.0, 0.0, 0.0, 0, set()
    for name, model, n, chars_in, cap_out, (slo, shi) in calls:
        tin = int(n * chars_in / prof.chars_per_token)
        out_lo = int(n * cap_out * prof.out_low)
        out_hi = int(n * cap_out * prof.out_high)
        c_lo, c_hi = _cost(model, tin, out_lo, config), _cost(model, tin, out_hi, config)
        if c_lo is None:
            unpriced.add(model)
        lo_usd += c_lo or 0.0
        hi_usd += c_hi or 0.0
        tin_tot += tin
        lo_s += n * slo
        hi_s += n * shi
        stages.append({"stage": name, "model": model, "calls": n,
                       "tokens_in": tin, "tokens_out_low": out_lo, "tokens_out_high": out_hi,
                       "usd_low": c_lo, "usd_high": c_hi})

    # Repairs are extra generate-shaped calls on some fraction of targets.
    if n_targets:
        rep_lo, rep_hi = int(n_targets * prof.repair_low), int(n_targets * prof.repair_high)
        tin_rep = int(rep_hi * (avg_target_src + prof.generate_overhead) / prof.chars_per_token)
        lo_usd += _cost(frontier, int(tin_rep * rep_lo / max(1, rep_hi)),
                        int(rep_lo * out_generate * prof.out_low), config) or 0.0
        hi_usd += _cost(frontier, tin_rep,
                        int(rep_hi * out_generate * prof.out_high), config) or 0.0
        hi_s += rep_hi * _SECS_FRONTIER[1]

    # Concurrency compresses wall clock but not spend.
    conc = max(1, int(config.get("concurrency") or 8))
    lo_s, hi_s = lo_s / conc, hi_s / conc

    # Scaled to what will actually be produced. A re-run that regenerates a tenth of the
    # estate does not need the whole estate reviewed again, and reporting otherwise would
    # hide the single biggest reason to re-run at all.
    share = (n_classes / len(classes)) if classes else 0
    involved = round(sum(1 for c in classes if c.get("layer") not in prof.mechanical_layers) * share)
    routine = max(0, round(len(classes) * share) - involved)
    rev_lo = (routine * _REVIEW_MINS_ROUTINE[0] + involved * _REVIEW_MINS_INVOLVED[0]) / 60
    rev_hi = (routine * _REVIEW_MINS_ROUTINE[1] + involved * _REVIEW_MINS_INVOLVED[1]) / 60

    free = provider == "mock"

    # The cap is enforced mid-run, which is the worst moment to first learn about it: the
    # money is spent and the estate is half-converted. Comparing the two numbers here puts
    # that on the one screen where raising the cap is still a cheap decision.
    from src.llm import _cost_cap
    cap = 0.0 if free else _cost_cap(config)
    budget = None
    if cap:
        budget = {
            "cap": round(cap, 2),
            # Against the high bound: the cheap comparison would use the low one and
            # would be reassuring far more often than it would be right.
            "will_exceed": round(hi_usd, 2) > cap,
            "may_exceed": round(lo_usd, 2) <= cap < round(hi_usd, 2),
        }

    return {
        "provider": provider,
        "free": free,
        "budget": budget,
        "classes": len(classes), "targets": targets, "reused": already_done,
        "stages": stages,
        "calls": sum(s["calls"] for s in stages),
        "tokens_in": tin_tot,
        "cost": {"low": 0.0 if free else round(lo_usd, 2),
                 "high": 0.0 if free else round(hi_usd, 2),
                 "unpriced": sorted(unpriced)},
        "minutes": {"low": round(lo_s / 60, 1), "high": round(hi_s / 60, 1)},
        "review_hours": {"low": round(rev_lo, 1), "high": round(rev_hi, 1)},
        "assumptions": _assumptions(config, conc, critic_on, already_done, free, prof),
        "basis": {"measured": prof.measured, "detail": prof.basis},
    }


def _assumptions(config, conc, critic_on, reused, free, prof=None) -> list[str]:
    a = []
    prof = prof or profile_for()
    if not prof.measured:
        # First in the list on purpose. Everything after it is conditioned on this, and a
        # caveat that arrives after the number has been read is a caveat nobody read.
        a.append("**These per-call sizes have not been measured for this platform pair.** "
                 f"They are {prof.basis}. Treat the range as an order of magnitude rather "
                 "than a quote, and re-measure after the first real run — the cost cap is "
                 "set against this number.")
    if free:
        a.append("Provider is `mock` — no model calls are made and nothing is charged.")
    routing = ((config.get("agentic") or {}).get("routing") or {})
    if routing.get("enabled"):
        m = routing.get("models") or {}
        a.append(f"Routing on: comprehension and planning on {m.get('cheap')}, "
                 f"generation and review on {m.get('frontier')}.")
    else:
        a.append(f"Routing off: every stage on {config.get('model')}.")
    a.append(f"Concurrency {conc} — this compresses wall-clock, not spend.")
    a.append("Critic review " + ("included" if critic_on else "disabled") + ".")
    if reused:
        a.append(f"{reused} unchanged class(es) reused from the last run and not re-billed.")
    a.append("Output length is the largest unknown; the range spans 30–65% of the "
             "configured token budget.")
    a.append("Review hours assume one reviewer and no rework.")
    return a


def headline(f: dict) -> str:
    if f.get("free"):
        return (f"Mock provider — free. About {f['calls']} simulated call(s), "
                f"{f['minutes']['low']}–{f['minutes']['high']} min.")
    c = f["cost"]
    money = (f"{pricing.fmt(c['low'])}–{pricing.fmt(c['high'])}"
             if (c["low"] or c["high"]) else "cost unknown")
    line = (f"Estimated {money} · {f['minutes']['low']}–{f['minutes']['high']} min of runtime · "
            f"{f['review_hours']['low']}–{f['review_hours']['high']} h of review")
    b = f.get("budget") or {}
    if b.get("will_exceed"):
        line += f" · ⚠ exceeds the {pricing.fmt(b['cap'])} cap — this run will be stopped"
    elif b.get("may_exceed"):
        line += f" · ⚠ may reach the {pricing.fmt(b['cap'])} cap"
    return line


def write_forecast_md(output_dir: str, f: dict) -> str:
    from pathlib import Path
    out = ["# Cost & Duration Forecast", "",
           "Estimated from the scan alone, before any model call. No spend was incurred "
           "producing this.", "", f"**{headline(f)}**", "",
           f"- {f['classes']} class(es) → {f['targets']} target(s)"
           + (f", {f['reused']} reused unchanged" if f.get("reused") else ""),
           f"- about {f['calls']} model call(s), ~{f['tokens_in']:,} input tokens", ""]

    if f["stages"]:
        out += ["| Stage | Model | Calls | Input tokens | Cost |", "|---|---|---|---|---|"]
        for s in f["stages"]:
            money = ("free" if f["free"] else
                     f"{pricing.fmt(s['usd_low'])}–{pricing.fmt(s['usd_high'])}"
                     if s["usd_low"] is not None else "unpriced")
            out.append(f"| {s['stage']} | `{s['model']}` | {s['calls']} | "
                       f"{s['tokens_in']:,} | {money} |")
        out.append("")

    b = f.get("budget") or {}
    if b.get("will_exceed"):
        out += [f"> 🚨 **This run is forecast to cost more than its {pricing.fmt(b['cap'])} "
                "cap and will be stopped part-way.** Raise `cost_cap.usd`, or narrow the "
                "scope at the plan gate. Whatever completes first is kept and reused, so "
                "stopping costs progress rather than money.", ""]
    elif b.get("may_exceed"):
        out += [f"> ⚠️ The high end of this estimate reaches the {pricing.fmt(b['cap'])} "
                "cap. The run may stop before finishing.", ""]

    if f["cost"].get("unpriced"):
        out += [f"> No published rate for {', '.join(f['cost']['unpriced'])} — those stages are "
                "excluded from the total, so treat it as a floor.", ""]

    if not (f.get("basis") or {}).get("measured", True):
        out += ["", "> ⚠️ **Not measured for this platform pair.** "
                + (f.get("basis") or {}).get("detail", "")
                + ". The range below is an order of magnitude, not a quote.", ""]

    out += ["## Assumptions", ""] + [f"- {a}" for a in f["assumptions"]] + [""]
    out += ["---", "",
            "> **This is a range, deliberately.** A single figure would imply a precision that "
            "does not exist — output length varies with how much the model decides to say, "
            "repair loops fire unpredictably, and provider latency is not ours to control. "
            "The bounds are honest; a point estimate would be wrong in a way that looks "
            "authoritative."]

    path = Path(output_dir) / "FORECAST.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return str(path)
