# Speaker Script — Executive Accelerator Deck (10 slides · 10–12 minutes)

**Companion to:** `DEMO_DECK.pptx` · **Version:** 0.7.0
**Total talk time:** 10–12 minutes. Each slide has a time budget — stick to them and you land on time with 1–2 minutes to spare for questions.

This is the talk track — what to *say* over each slide, in plain, human language. Each slide has:
**⏱ budget**, **SAY** (speak it or paraphrase — the bold first sentence is the must-say line),
**POINT TO** (what to gesture at), and **THEN** (the bridge to the next slide).

> **If you're running long:** slides 4 (Architecture) and 7 (Deliverable) are the safest to
> compress to one sentence each — just read their green "In plain words" strip and move on.

---

## Before slide 1 (10 seconds)

**SAY:** "I have about ten minutes, so I'll move quickly. I'm going to show you an accelerator
we've built that takes a SAP Hybris system and moves it to Salesforce — using AI to do the heavy
lifting, and then proving the result actually works. Questions at the end, or stop me if
something's unclear."

---

## Slide 1 — Cover ⏱ 45s

**SAY:** "**Migrating a complete Hybris estate to Salesforce is a multi-month program — nobody
should pretend otherwise. What this accelerator does is remove the biggest bottleneck in that
program: the manual code-move.** AI does the rewriting, and — the part that makes this different —
the tool then *proves* its own output runs, before any of your experts spend a minute on it.
That's the whole story: migrated by AI, proven to run."

**POINT TO:** the flow strip — Hybris → AI Agent Team → Salesforce.
**THEN:** "Thirty seconds on why the manual way hurts."

## Slide 2 — The Problem ⏱ 60s

**SAY:** "Three reasons manual migration fails. **It's slow** — hundreds of Java classes, a custom
data model, live data, scheduled jobs; that's quarters, often years. **It needs rare people** —
engineers senior in *both* platforms, one of the most expensive skill sets in the market. **And
the dangerous one: business logic gets quietly lost.** A rule like 'never accept a zero-value
order' just disappears in a rewrite — and nobody notices until it breaks in production."

**POINT TO:** the three red cards, landing on "Silent logic loss."
**THEN:** "Here's what the accelerator does about it."

## Slide 3 — The Accelerator ⏱ 75s

**SAY:** "**You point it at the old code, and it hands back a working Salesforce project.** On the
left, what goes in: the Java business logic, the data model, the actual data, the scheduled jobs.
On the right, what comes out: Salesforce code written to Salesforce's own enterprise patterns, a
test for every class, the data and schedules migrated — and a confidence report that tells your
reviewers exactly what to trust and what to double-check. The green strip at the bottom is the
honest framing: the full migration is still a program — but the code-move stops being the
bottleneck. The accelerator does the grind; your experts review a scored draft instead of
rewriting from scratch. That's the effort reduction."

**POINT TO:** IN box → the black AI circle → OUT box → the green strip.
**THEN:** "One slide on how it's put together."

## Slide 4 — Architecture ⏱ 75s

**SAY:** "Four layers, top to bottom. **Interfaces** — a VS Code extension for people, a command
line for automation; same engine. **Orchestration** — two driving modes: a smart agent team, or a
simpler assembly line for cheaper runs. **One shared toolbox** of proven functions underneath —
parsing, schema, generation, verification — so every improvement lands in both modes
automatically. And at the bottom, **the AI brain is swappable**: production-grade Claude, cheaper
models for iteration, or a free offline mode where nothing leaves the machine — which is also how
you evaluate this with zero exposure."

**POINT TO:** each layer top-to-bottom; tap the green "Mock — free, offline" node last.
**THEN:** "Now the heart of it — the agent team."

## Slide 5 — The AI Agent Team ⏱ 90s — *the key slide*

**SAY:** "**This isn't one AI call and hope — it's four specialists that check each other, like a
real team.** They work around a shared whiteboard — the plan, every generated file, every
decision, every open question lives there, and it's exported as a readable document after every
run. **The Planner** sets strategy: what becomes Salesforce code, what should be a ready-made
Salesforce product instead, what's not worth migrating. Look at its quote — 'pricing rules?
That's CPQ — don't hand-build it.' That's an architect's judgement call, made by the AI. **The
Builder** writes the code and tests, grounded in *your* real data model. **The Critic** is the
skeptical reviewer — its quote is real: it caught a zero-total business rule that had been
silently dropped, and blocked the class. **And the Verifier** deploys to a real Salesforce org
and fixes real errors until it's green. Not 'looks right' — it actually ran."

**POINT TO:** the whiteboard bar, then each card's quote in turn.
**THEN:** "Under the hood, the run itself is ten stages."

## Slide 6 — The Pipeline ⏱ 60s

**SAY:** "I won't read ten boxes — the pattern is what matters: **the black AI badge appears on
only four of the ten stages.** Understanding the code, writing it, fixing it, and final
verification — the judgement work. Everything else — parsing files, building the data catalog,
packaging the output — is ordinary, tested, deterministic software: fast, free, and the same
result every time. We use AI only where it earns its keep, which also keeps the cost down."

**POINT TO:** the four AI badges, then sweep the unbadged tiles.
**THEN:** "And here's the slide I'd want you to remember — why you can trust the output."

## Slide 7 — Why You Can Trust It ⏱ 90s — *the differentiator*

**SAY:** "**Most AI tools stop at 'the AI wrote some code.' This one proves the code runs.** It
deploys the output to a real Salesforce environment — validation-only, nothing destructive. It
reads the *actual* compiler errors, not guesses. And it heals three different ways: a missing
data field that's genuinely used in the original Java gets *added*, with evidence — never
guessed. Broken code goes back to the AI *with the real error message* and gets rewritten. And if
test coverage is below Salesforce's own 75% deployment requirement, it writes more tests until it
clears the bar. It loops until green — and anything it can't resolve is flagged for a human,
never silently shipped. Correctness comes from the loop, not from trusting the model."

**POINT TO:** the four loop boxes left-to-right, then the three healing cards.
**THEN:** "So what do you actually receive at the end?"

## Slide 8 — The Deliverable ⏱ 60s

**SAY:** "Six things in every run's output folder. The **code and its tests**. The **data model**.
The **data itself** as load-ready files with an import guide. The **schedules**, same timing.
The **decision document** — every call the Planner made, every finding the Critic raised. And the
**scorecard** — a High-Medium-Low confidence rating on every single class, so reviewers know
exactly where to spend their time. And the maturity markers at the bottom: sixty-three automated
tests all passing, three AI providers including the free offline mode, and every run reports its
own cost."

**POINT TO:** sweep the six tiles; tap MIGRATION_PLAN and FEASIBILITY_REPORT; then the chips.
**THEN:** "Let me land the business case."

## Slide 9 — The Business Case ⏱ 60s

**SAY:** "Left column versus right. **Months of manual rewriting becomes a verified first draft in
minutes to hours. Silently lost business rules become an AI reviewer plus a score that proves
preservation. 'Trust me, it compiles' becomes 'deployed to a real org and self-corrected until
verifiably green.'** Everything-becomes-custom-code becomes native Salesforce products where they
fit — less debt to own forever. And the black box becomes a decision log on every class. The
honest line at the bottom, and I'll say it out loud: this makes your expert reviewers
dramatically faster — it does not remove them, and we're not pretending it does."

**POINT TO:** run down the red column, then the green; finish on the honesty strip.
**THEN:** "Which brings me to the ask."

## Slide 10 — The Ask ⏱ 30s

**SAY:** "**Give us one real slice of a Hybris codebase — not production, just a real piece — and
we'll hand back verified Salesforce code plus the receipts on how we got there.** A pilot is days,
not months: free offline mode first so nothing sensitive leaves your side, a scored real run
second, your team's verdict third. That's it — happy to take questions, or show it running live."

---

## Timing cheat-sheet

| Slide | Budget | Running total |
|---|---|---|
| 1 · Cover | 0:45 | 0:45 |
| 2 · Problem | 1:00 | 1:45 |
| 3 · Accelerator | 1:15 | 3:00 |
| 4 · Architecture | 1:15 | 4:15 |
| 5 · Agent team | 1:30 | 5:45 |
| 6 · Pipeline | 1:00 | 6:45 |
| 7 · Trust / self-healing | 1:30 | 8:15 |
| 8 · Deliverable | 1:00 | 9:15 |
| 9 · Business case | 1:00 | 10:15 |
| 10 · The ask | 0:30 | **10:45** |

**Running long?** Compress slides 4 and 7's detail — read the green strips.
**Running short / strong interest?** Offer the live run ([DEMO_SCRIPT.md](DEMO_SCRIPT.md)) or the full docs ([README.md](README.md)).

## Q&A quick answers (30 seconds each)

- **"Does it replace developers?"** No — it replaces the grind. Experts review a scored draft; the confidence ratings show where to look.
- **"What if the AI hallucinates?"** It can only use fields that provably exist, a second AI reviews every class, and the code must compile against a real org.
- **"Is our code safe?"** It goes only to the AI vendor you configure — or nowhere at all in the free offline mode. Deploys are validation-only.
- **"What's not covered yet?"** Hybris workflow processes and storefront REST APIs — on the roadmap, and the tool tells you honestly what it skipped.
- **"Cost?"** Every run itemizes its own AI usage in the report; cheap models handle the simple stages automatically.

## The three lines to never forget

1. **"The code-move stops being the bottleneck — AI does the grind, your experts review a scored draft."** (Slide 3)
2. **"It doesn't just write code — it proves the code runs."** (Slide 7)
3. **"Dramatically faster expert reviewers — not replaced ones."** (Slide 9)
