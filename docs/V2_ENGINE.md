# The v2 engine — how to use it, and how we know it is safe

**Branch:** `v2` · **Default:** v1, everywhere · **Status:** seam built, adapters thin

v2 is the same engine with a named seam down the middle, so a second migration path can be
plugged in beside the shipped one. It is **not** a rewrite, and today it does not change a
single byte of what a migration produces.

## Choosing a version

```bash
# v1 — the shipped engine. This is what you get if you say nothing.
python -m src.main agent-migrate --input <src> --output <out>

# v2 — the same work, routed through the pipeline adapters
python -m src.main agent-migrate --input <src> --output <out> --engine-version v2
H2A_ENGINE_VERSION=v2 python -m src.main agent-migrate ...
```

Or set `engine_version: v2` in `config.yaml`. Precedence is
**`--engine-version` → `H2A_ENGINE_VERSION` → `config.yaml` → v1**, and anything
unrecognised falls back to v1 — a typo must never fail open into an unproven engine.

A v2 run announces itself, so you are never guessing which path you took:

```
  Engine: v2  |  pipeline: SAP Hybris → Salesforce
```

## How we know v1 is untouched

Not by assertion — by three tests that run on every commit:

| Test | What it proves |
|---|---|
| `test_reference_migration_is_unchanged` | Every generated file and report still matches the recorded baseline of 128 files. |
| `test_two_identical_runs_agree` | The pipeline is deterministic — two identical runs produce identical output. |
| `test_v2_engine_matches_v1_exactly` | **Running the reference migration through v2 produces byte-identical output to v1.** |

That third one is the whole argument. The adapters delegate to the same functions v1 calls,
so routing through them must change nothing. The day it does, it is a bug — and the test
fails before anyone ships it.

```bash
pytest tests/test_golden.py      # the three above (~35s)
pytest -m "not slow"             # everything else, for tight loops
```

### Re-baselining, deliberately

When a change to output *is* intended:

```bash
H2A_GOLDEN_UPDATE=1 pytest tests/test_golden.py
```

This rewrites `tests/golden/manifest.json`. **The diff to that file belongs in the commit**
and should be explained there — it is the record of what changed about the product, and it
is the one file where "just regenerate it" is the wrong instinct.

## What v2 adds

| Module | Role |
|---|---|
| `src/ir.py` | The normalised migration model. Not new — the engine always had one, implicit and Java-shaped. This names it. |
| `src/pipeline.py` | The registry: which migrations exist, which one a run is, and the version switch. |
| `src/adapters/hybris_source.py` | SAP Hybris as a *source*. |
| `src/adapters/salesforce_target.py` | Salesforce as a *target*. Declares `has_oracle = True` — it can be compiled by an authority that is not us. |

Adapters own **dispatch, never logic**. Every one delegates to the same stage function v1
calls. An adapter that reimplemented a stage would be a second copy to keep correct, and
there would then be two answers to "what does this product do".

## Two things found while building this

**The recipe hash was non-deterministic.** It hashed a schema containing sets via `str()`,
whose element order varies per process. Two identical runs produced different recipes — and
because target fingerprints derive from the recipe, **incremental reuse never survived a
process restart**. Every re-run silently re-billed the entire estate. Fixed in
`incremental.py::_canonical`; `test_two_identical_runs_agree` is what caught it and what
keeps it caught.

> This is a **v1 bug**, fixed on this branch. It is worth cherry-picking to `main`
> independently of the v2 work — it costs real money on every re-run.

**The IR was silently dropping frontend fields.** A Component unit carries `selector`,
`template`, `styles`, `inputs`, `outputs` — none of which mean anything to a Java class.
Modelling every platform's every field would make the IR a union of two schemas; dropping
the unmodelled ones is exactly the silent loss this product exists to prevent. So
`SourceUnit.extra` carries them through untouched. Caught before wiring, by checking the
round trip rather than assuming it.

## What is deliberately not done yet

The seam exists; most of the pipeline still runs behind it unchanged. Under v2 today only
**ingest and preflight** route through the adapter — comprehension, planning, generation,
validation and verification still call their modules directly. That is intentional: each
stage moves behind the seam in its own commit, with the golden harness proving each move
changed nothing.

Next, in order: the target adapter takes over `plan`/`emit`; the knowledge pack becomes
per-pipeline; `characterize` splits into mine/plan/emit. Then the Adobe Commerce source
adapter has somewhere to plug in.

## Merging back

`main` stays on v1 until v2 has run real migrations and the efficiency budgets in
[ROADMAP_MULTI_PLATFORM.md](ROADMAP_MULTI_PLATFORM.md) are met. Until then this branch is
strictly additive: `main` is the fallback, and it works.
