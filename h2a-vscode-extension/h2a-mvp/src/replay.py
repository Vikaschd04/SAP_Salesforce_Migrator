"""
replay.py — prove why the AI did that, months later.

Every call already goes through one gateway and is keyed by a hash of (stage, model,
prompt). That was built as a cost optimisation; it is also, unchanged, an audit trail.
In a regulated enterprise "show me why this Apex was written this way in March" is a
procurement question, and the honest answer is not a re-run — a re-run may legitimately
differ — but a replay from the identical key, which cannot.

**The prompts themselves are deliberately not stored here.** They contain the customer's
source code, and copying that into a second place on disk is a liability rather than a
feature. The hash identifies the call; the response cache already holds the answer. What
this adds is the index: which stage, which model, which key, and whether the answer came
from cache or from the provider.
"""

from __future__ import annotations

from pathlib import Path


def build_replay(call_log: list[dict], *, recipe: str = "") -> dict:
    calls = list(call_log or [])
    by_stage: dict[str, dict] = {}
    for c in calls:
        family = c["stage"].split("_")[0]
        s = by_stage.setdefault(family, {"stage": family, "calls": 0, "cached": 0,
                                         "models": set(), "chars": 0})
        s["calls"] += 1
        s["cached"] += 1 if c["cached"] else 0
        s["models"].add(c["model"])
        s["chars"] += c.get("prompt_chars", 0)
    stages = [{**s, "models": sorted(s["models"])} for s in by_stage.values()]
    stages.sort(key=lambda s: -s["calls"])

    cached = sum(1 for c in calls if c["cached"])
    return {
        "recipe": recipe,
        "calls": calls,
        "stages": stages,
        "summary": {
            "total": len(calls), "cached": cached, "live": len(calls) - cached,
            "models": sorted({c["model"] for c in calls}),
            "replayable": len(calls),          # every call carries a key
        },
    }


def headline(s: dict) -> str:
    t = s.get("total") or 0
    if not t:
        return "No model calls were made — nothing to replay."
    return (f"{t} model call(s) recorded and replayable · {s['cached']} served from cache, "
            f"{s['live']} live")


def write_replay_md(output_dir: str, r: dict) -> str:
    s = r.get("summary") or {}
    out = ["# Decision Record — every model call in this run", "",
           "Each call is identified by a hash of its stage, model and prompt. Replaying a "
           "key returns the identical response, which a re-run cannot promise.", "",
           f"**{headline(s)}**", ""]
    if r.get("recipe"):
        out += [f"Run recipe (config + provider + model fingerprint): `{r['recipe']}`", ""]

    if r["stages"]:
        out += ["| Stage | Calls | From cache | Models | Prompt chars |", "|---|---|---|---|---|"]
        out += [f"| {st['stage']} | {st['calls']} | {st['cached']} | "
                f"{', '.join(f'`{m}`' for m in st['models'])} | {st['chars']:,} |"
                for st in r["stages"]]
        out.append("")

    out += ["## Calls, in order", "",
            "| # | Stage | Model | Cache key | Source |", "|---|---|---|---|---|"]
    out += [f"| {c['seq']} | {c['stage']} | `{c['model']}` | `{c['cache_key'][:16]}…` | "
            f"{'cache' if c['cached'] else 'provider'} |" for c in r["calls"]]

    out += ["", "---", "",
            "> **The prompts are not stored here, deliberately.** They contain your source "
            "code, and copying it into a second place on disk would be a liability rather "
            "than a feature. The hash identifies the call and the response cache already "
            "holds the answer — together those are enough to reproduce any decision exactly."]

    path = Path(output_dir) / "DECISION_RECORD.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return str(path)
