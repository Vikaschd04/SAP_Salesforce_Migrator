---
name: migration-edge-cases
description: Apply H2A's migration edge-case discipline when adding or reviewing conversion logic, detectors, or adapters. Use when writing a rule, an adapter method, or a prompt that turns source-platform code into target-platform code — Hybris→Salesforce or Adobe Commerce→Hybris.
---

# Migration edge-case discipline

The register lives in `docs/EDGE_CASES.md`. **Read it before adding conversion logic** —
if the thing you are building touches a row in it, that row's status is your acceptance
criterion. This file is the *judgement*, not the list.

## The four rules

**1. A detector that explains beats a rewrite that guesses.**
A flagged hazard with a named fix is actionable. A confidently wrong automatic rewrite is
a liability the customer discovers in production, and it destroys trust in every other
output the run produced. When in doubt: detect, explain, and refuse.

**2. The dangerous failures are the ones that pass every gate.**
Rank work by *damage prevented*, not difficulty. The worst class of bug in this domain
compiles, deploys, passes review, and is wrong — a `BigDecimal.divide` without an explicit
scale, an API name truncated at 40 characters so two attributes merge into one field, a
picklist field emitted without its values. Nothing downstream catches these. That is
exactly why they rank above harder, louder problems.

**3. Never return empty where you mean "not implemented".**
Scaffolded adapters raise `NotImplementedYet` with the owning item number. Missing packs
raise. `require_runnable()` blocks before a file is read. An empty list is
indistinguishable from "nothing applied", and that ambiguity is how a migration silently
skips a third of an estate.

**4. Every outcome is accounted for.**
The completeness ledger has eight outcomes (converted / flagged / skipped / unaccounted /
overwritten / manual / scaffolded / unreadable). A unit that is not converted must land in
one of the others *with a reason*. "Unaccounted" existing at all is a bug.

## When adding a detector

- Write the `Testing/` fixture **first**, and confirm it actually trips the rule. A rule
  with no failing example is a rule nobody has tested. (A past session wrote a "bad Apex"
  fixture that did not trip the loop detector — investigating why exposed a real gap in
  the detector, not the fixture.)
- Then confirm the rule does *not* fire on the near-miss. Loop detection tracks brace
  state per character position precisely because line-level state produced both false
  negatives (single-line loop bodies) and false positives.
- Give the finding a `hazard` (what breaks, in production terms) and a `fix` (what to do).
  A severity with no fix is noise.
- Run the golden harness. If the reference output changes, re-baseline **in the same
  commit** so the diff is reviewed as part of the change.

## Where code goes

The seam is: **source adapter → IR → neutral assurance → target adapter.**

- Reading source (parsing, mining tests, detecting the platform) → `src/adapters/<source>_*.py`
- Writing target (literals, method lookup, emission, prompts, validation) → `src/adapters/<target>_*.py`
- Deciding what something is *worth* (planning, classification, ledgers, reports) → the
  neutral layer

`tests/test_assurance_purity.py` enforces this: **no assurance module may import an adapter
or the pipeline registry**, and platform vocabulary in those modules is a ratchet that can
only shrink. If you need a platform fact in the neutral layer, ask the adapter for it
(`target.code_language`, `target.find_method`) — do not import it.

## The trap to avoid

The neutral layer is easy to re-break by accident: one `from src.adapters import ...` for a
quick fix and the layer is Salesforce-only again, with **nothing failing**, because the
shipped pipeline is Salesforce. That is why the rule is enforced in CI rather than
documented. When a test in that file fails, the fix is almost never to widen the allowlist.

## Beyond the current register

Two things are known to be missing from the engine's own reasoning and are worth raising
whenever they become relevant:

- **No cross-unit semantic check.** Every gate judges one artifact at a time. A migration
  that is individually correct per class and collectively inconsistent (two classes
  disagreeing about the same picklist, or the same External Id) has no detector at all.
- **The oracle is asymmetric.** Salesforce has a real compile/deploy oracle
  (`has_oracle = True`); the Hybris target does not, and a licensed SAP Commerce platform
  may never be available. Any claim of correctness on the Adobe→Hybris path must be
  honest that it rests on static checks and characterization, not on a compiler.
