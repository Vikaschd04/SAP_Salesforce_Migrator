# Speaker Script — Executive Accelerator Deck (10 slides · 10–12 minutes)

**Companion to:** `DEMO_DECK.pptx` · **Version:** 0.10.0
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

**SAY:** "Five layers, top to bottom. **Surfaces** — a web cockpit where you watch and approve as
it runs, a VS Code right-click for developers, a command line for automation; all the same engine.
**Orchestration** — the agent team, with three points where a human decides. **One shared toolbox**
of proven functions underneath, so every improvement lands everywhere automatically. Then
**assurance** — and note this layer uses *no AI at all*; it checks the AI's work by reading what
the run recorded. And at the bottom, **the AI brain is swappable**: production-grade Claude,
cheaper models for iteration, or a free offline mode where nothing leaves the machine — which is
also how you evaluate this with zero exposure."

**POINT TO:** each layer top-to-bottom; pause on ASSURANCE, then tap "Mock — free, offline" last.
**THEN:** "Now the heart of it — the agent team."

## Slide 5 — The AI Agent Team ⏱ 90s — *the key slide*

**SAY:** "**This isn't one AI call and hope — it's four specialists that check each other, like a
real team.** They work around a shared whiteboard — the plan, every generated file, every
decision, every open question lives there, and it's exported as a readable document after every
run. **The Planner** sets strategy — and here's a policy worth calling out: it **converts
everything**. Where a native Salesforce product like CPQ would be the better long-term home, it
still converts the logic in full and *flags it for review*. It never silently drops your code
because a product might do it better. That decision stays yours. **The
Builder** writes the code and tests, grounded in *your* real data model. **The Critic** is the
skeptical reviewer — its quote is real: it caught a zero-total business rule that had been
silently dropped, and blocked the class. **And the Verifier** deploys to a real Salesforce org
and fixes real errors until it's green. Not 'looks right' — it actually ran."

**POINT TO:** the whiteboard bar, then each card's quote in turn.
**THEN:** "Under the hood, the run is ten stages — and you're in three of them."

## Slide 6 — The Pipeline ⏱ 60s

**SAY:** "I won't read ten boxes — two patterns matter. First, **the black AI badge appears on
only four stages.** Understanding the code, writing it, reviewing it, verifying it — the
judgement work. Everything else is ordinary, tested, deterministic software: fast, free, same
result every time. Second, **the copper YOU badges — three review gates.** And look *where the
first one is*: stage four, before any AI has been used. By then it has already told you whether
this is really a Hybris codebase, what the run will cost as a range, and what will collide in
your own Salesforce org — all for free. **You approve the spend before there is any spend.**"

**POINT TO:** the four AI badges, then the three copper YOU badges, then tap stage 03.
**THEN:** "And here's the slide I'd want you to remember — why you can trust the output."

## Slide 7 — Why You Can Trust It ⏱ 90s — *the differentiator*

**SAY:** "**Most AI tools stop at 'the AI wrote some code.' This one proves it still behaves the
same.** Top row: it deploys to a real Salesforce environment — validation-only, nothing
destructive — reads the *actual* compiler errors, fixes them, and loops until green. Anything it
can't resolve is flagged, never silently shipped.

But compiling isn't behaving, so — bottom row. **Every business rule** found in your Java is
followed through to the finished code and lands in one of four buckets: asserted, implemented, at
risk, or **dropped**. That last bucket is rules that existed in your old system and didn't make
it — and it's the one no other tool will show you. **Second, we replay your own tests.** We mine
your existing JUnit suite for what the old code actually did and run it against the new Apex —
and the AI is allowed to set the test up, but it is *never* allowed to write the expected answer.
A model that could write its own expectations could make anything pass.

**And third — the one I'd actually lead with.** It tells you what it *can't* prove. Untested
rules, methods with no traceable origin, whether a real org ever compiled it. There is no '100%'
badge anywhere in this product, deliberately."

**POINT TO:** the four loop boxes left-to-right, then each of the three proof cards.
**THEN:** "So what do you actually receive at the end?"

## Slide 8 — The Deliverable ⏱ 60s

**SAY:** "Six things in every run's output folder. The **code and its tests** — Apex and, where
you had a Spartacus storefront, Lightning Web Components. The **data model**. The **data and
schedules**, load-ready, same timing. Then the three that matter to a reviewer: the **sign-off
contract** — who approved which stage, on what evidence, and what it does *not* certify. The
**triage list** — every file ranked by how much it actually needs you, because nobody reviews
four hundred classes carefully; they read thirty properly and rubber-stamp the rest. And the
**scorecard**. Maturity markers at the bottom: three hundred and forty automated tests all
passing, three AI providers including the free offline mode, and every run reports its own cost."

**POINT TO:** sweep the six tiles; tap SIGN_OFF and TRIAGE; then the chips.
**THEN:** "Let me land the business case."

## Slide 9 — The Business Case ⏱ 60s

**SAY:** "Left column versus right. **Months of manual rewriting becomes a verified first draft in
minutes to hours. Silently lost business rules become every rule tracked to a verdict — including
the ones nothing carries. 'Trust me, it compiles' becomes 'deployed to a real org and
self-corrected until verifiably green.'** Everything-becomes-custom-code becomes native Salesforce
products flagged where they fit. The black box becomes a signed audit. And the last row is the one
I care about: **'it converted 100% of files' becomes a number that means something** — rules
preserved, not files touched. Anyone can move a file. The honest line at the bottom, and I'll say
it out loud: this makes your expert reviewers dramatically faster — it does not remove them, and
we're not pretending it does."

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

- **"Does it replace developers?"** No — it replaces the grind. Experts review a *ranked* draft; the triage list puts the dozen that matter at the top instead of leaving four hundred files to skim.
- **"What if the AI hallucinates?"** It can only use fields that provably exist, a second AI reviews every class, and the code must compile against a real org. Separately: wherever the AI could grade its own homework, it isn't allowed to — it never writes a test's expected answer, and never reports its own line numbers.
- **"How do we know a business rule survived?"** Every rule gets a verdict, and your own JUnit tests are replayed against the new code. If nothing carries a rule, it's listed as *dropped* — we surface that rather than hide it.
- **"Is our code safe?"** It goes only to the AI vendor you configure — or nowhere at all in the free offline mode. Deploys are validation-only. Preflight also warns you if the upload contains live credentials, which Hybris config files routinely do.
- **"What will it cost, and can it run away?"** You get a cost *range* before the first billable call, and a hard per-run cap (default $25) enforced before every call. Every run itemizes its own usage.
- **"What's not covered yet?"** Hybris workflow processes and storefront REST APIs — on the roadmap, and the tool tells you honestly what it skipped.
- **"How mature is this really?"** 340 automated tests, three delivery surfaces, and a full assurance layer. Straight answer on the gap: it's been validated end-to-end in free offline mode, and the paid-model run on a real estate is exactly what a pilot is for.

## The three lines to never forget

1. **"The code-move stops being the bottleneck — AI does the grind, your experts review a ranked draft."** (Slide 3)
2. **"Every other tool converts your code. This one proves it still behaves the same."** (Slide 7)
3. **"And it tells you what it can't prove."** (Slide 7 — the line that closes technical buyers)
4. **"Dramatically faster expert reviewers — not replaced ones."** (Slide 9)

> **One thing to avoid saying:** never claim "100% accurate" or "fully verified". The product
> deliberately refuses to print a 100% badge, and the sign-off tab lists what it could not prove.
> If you overclaim and someone opens that tab, the tool contradicts you in the room. Make the
> honesty the pitch — it is the actual differentiator.
