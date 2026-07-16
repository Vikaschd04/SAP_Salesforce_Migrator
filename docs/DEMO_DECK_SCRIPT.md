# Speaker Script — Executive Reference Deck

**Companion to:** `DEMO_DECK.pdf` (20 slides) · **Version:** 0.7.0
**Full talk:** ~20–25 minutes · **Short version:** ~8 minutes (see cheat-sheet at the end)

This is the talk track — what to *say* over each slide, in plain, human language. Each slide has:
**SAY** (speak it or paraphrase it — the bold first sentence is the must-say line),
**POINT TO** (what to gesture at), and **THEN** (the bridge to the next slide).

Every technical slide in the deck carries a green **"In plain words"** strip at the bottom —
if a slide ever feels too technical for the room, just read that strip aloud and move on.

---

## Before slide 1 (10 seconds)

**SAY:** "I'm going to walk you through a platform we've built that migrates an old SAP Hybris
system to Salesforce — mostly automatically, and with proof that the result actually works.
Twenty minutes, then a live run. Stop me anytime."

---

## Slide 1 — Cover

**SAY:** "**The headline is the whole story: migrated by AI, and proven to run.** Lots of tools
can generate code with AI now. The difference here is the second half — this platform deploys
its own output to a real Salesforce environment and fixes what breaks, before any human reviews
it. That's the theme you'll see on every slide."

**POINT TO:** the flow strip — Hybris → AI Agent Team → Salesforce.
**THEN:** "Here's the map of what we'll cover — you can also use this deck as a reference afterwards; everything is in it."

## Slide 2 — Agenda

**SAY:** "Quick map: the problem, what the platform does and how, a look inside the architecture
and the AI team for those who want it, the proof and security story, and then business case,
questions, and the ask. If you only remember three slides, make it 8, 11 and 14 — the team,
the self-healing, and the real evidence."

**THEN:** "Let's start with why this is worth anyone's time."

## Slide 3 — The Problem

**SAY:** "Moving off Hybris by hand hurts in three ways. **It's slow** — hundreds of code files,
a custom data model, live data, scheduled jobs; that's quarters or years. **It needs rare
people** — engineers senior in *both* platforms. **And the dangerous one: things get quietly
lost.** A rule like 'never accept a zero-value order' just disappears during a rewrite, and
nobody notices until production."

**POINT TO:** the three red cards; land on "Silent logic loss."
**READ the green strip if useful:** "It's like retyping a thousand-page contract from memory —
slow, and the fine print is what gets lost."
**THEN:** "So here's what we built."

## Slide 4 — What It Does

**SAY:** "**You point it at the old code; it hands back a working Salesforce project.** Left side:
what goes in — the Java logic, the data model, the actual data, the scheduled jobs. Right side:
what comes out — Salesforce code written the proper way, a test for every piece, the data and
schedules migrated, and a report that says what to trust and what to double-check. And the thing
in the middle isn't one AI — it's a team of them. That's coming up."

**POINT TO:** left box → black circle → right box.
**THEN:** "First, the sixty-second version of how."

## Slide 5 — How It Works (Four Moves)

**SAY:** "Four moves, same as a good engineering team. **One — understand:** read everything, map
the dependencies, write down the business rules found — before writing any code. **Two — plan:**
decide what each piece becomes, including what should *not* be custom code at all. **Three —
build and review:** write the code and tests, with a second AI reviewing every piece skeptically.
**Four — prove:** deploy to a real Salesforce environment and fix real errors, in a loop, until
it's green. And everything gets written down — no black box."

**POINT TO:** the four circles, left to right; note the green fourth circle — "prove" is the differentiator.
**THEN:** "Now one level deeper — the architecture. Don't worry, one slide."

## Slide 6 — Architecture

**SAY:** "Four layers. **Top: the interfaces** — a VS Code extension for people, a command line
for automation; both drive the same engine. **Second: orchestration** — two driving modes: the
smart 'agent team' mode, and a simpler assembly-line mode for cheaper runs. **Third — and this is
the important engineering decision — a single shared toolbox** of stage functions: parsing,
schema-building, code generation, verification. Both modes use the same tools, so every fix or
new feature lands in both automatically. **Bottom: the AI brain is swappable** — production-grade
Claude, cheaper models for iteration, or a free offline mode where nothing leaves the machine."

**POINT TO:** each layer top-to-bottom; tap the green-highlighted agentic row and the green "Mock" node.
**READ the green strip if the room is non-technical.**
**THEN:** "Here's what actually happens inside a run, stage by stage."

## Slide 7 — The Pipeline (10 Stages)

**SAY:** "Ten stages, and I'll give you the pattern instead of reading them all: **the black 'AI'
badge marks where the language model is used — only four of the ten.** Understanding code,
writing code, fixing code, and final verification — the places that need judgement. Everything
else — parsing files, building the data catalog, packaging the output — is ordinary, tested,
deterministic software: fast, free, and the same result every time. That split is deliberate:
we use AI only where it earns its keep."

**POINT TO:** the AI badges on stages 5, 6, 7, 10; then sweep the un-badged ones.
**THEN:** "Now the part everyone asks about — the agent team."

## Slide 8 — The Agentic Core (Blackboard)

**SAY:** "Think of it as **a manager, a whiteboard, and four specialists.** The Orchestrator at the
top routes the work. The dashed green box is the shared whiteboard — the schema, the plan, every
generated file, every decision, and every open question live there. The four specialists below
read from it and write to it. The reason this shape matters: **work can go backwards.** When the
reviewer finds a problem, it goes back to the builder — like a real team, not a one-way conveyor
belt. And the whiteboard is exported as a readable document after every run."

**POINT TO:** Orchestrator → whiteboard → the four agent tiles; emphasize the ▲▼ arrows.
**THEN:** "Let me introduce the four of them properly."

## Slide 9 — The Four Agents

**SAY:** "**The Planner** sets strategy — for every piece: build it as Salesforce code, or
recommend a ready-made Salesforce product instead, or skip it. Look at its quote: 'pricing rules?
That's Salesforce CPQ — don't hand-build it.' **The Builder** writes the code and tests, grounded
in the real data model and a built-in best-practice library. **The Critic** is the skeptical
senior reviewer — it checks the original behavior survived and that the code is secure, and it
can block work. **The Verifier** deploys to a real org and heals real failures. And note the small
grey boxes — what each agent *replaces*: blind translation, months of manual rewriting, hoping a
human catches everything, and 'trust me, it compiles.'"

**POINT TO:** each card's quote, then the grey "REPLACES" boxes.
**THEN:** "So what does using it actually feel like? Five steps."

## Slide 10 — The User Journey

**SAY:** "**For the user, the entire platform is one right-click.** Configure once — pick your AI
provider, paste a key, or choose the free offline mode. Right-click the Hybris folder, click
'Migrate to Apex.' Watch the dashboard stream progress. A `salesforce_` folder appears — a
complete, deployable project. Then review the report and ship. And the same run is scriptable
from a terminal for CI/CD, for the engineers in the room."

**POINT TO:** the five steps; the "behind the scenes" strip for the CI/CD point.
**THEN:** "Now the slide that I think is the reason to buy — the proof loop."

## Slide 11 — Self-Healing Verification

**SAY:** "**Most AI tools stop at 'the AI wrote code.' This platform proves the code runs.** It
deploys — a validation-only deploy, nothing destructive — to an actual Salesforce environment.
It reads the *real* compiler errors, not guesses. Then it heals, three different ways: a missing
data field, if it's genuinely used in the original Java, gets *added* — with evidence, never
guessed. Broken code goes back to the AI *with the real error message* and gets rewritten. And if
test coverage is below Salesforce's own 75% deploy requirement, the tool writes more tests until
it clears the bar. It loops until green — and anything it can't resolve is flagged for a human,
never silently shipped."

**POINT TO:** the four loop nodes left to right, then the three healing cards below.
**THEN:** "One more trust slide — how we stop the AI from inventing things in the first place."

## Slide 12 — Grounding & Safety

**SAY:** "Three mechanisms. **One — schema grounding:** before writing a single query, the AI is
shown the exact catalog of objects and fields that really exist; everything it writes is checked
against that catalog afterwards. **Two — evidence-based reconciliation:** if generated code
mentions a field the data model never declared, we check the original Java source. Genuinely used
there? Added, properly typed. No evidence? Flagged as a likely hallucination for a human — never
silently guessed. **Three — a built-in knowledge base:** Salesforce's limits, security rules, and
patterns are bundled as a reference library the agents look up and cite while working. The AI
works open-book."

**POINT TO:** cards 1 → 2 → 3; the green strip line "open book" is the sound bite.
**THEN:** "Here's everything that lands in the output folder."

## Slide 13 — The Deliverable

**SAY:** "Six things in every output. The **code and its tests**. The **data model** — objects,
fields, dropdowns, relationships. The **data itself**, as load-ready files with a safe re-runnable
import guide. The **schedules**, translated with identical timing and a ready-to-run script. The
**decision document** — every call the Planner made and every finding the Critic raised. And the
**scorecard** — a High-Medium-Low confidence rating on every class, deploy status, and what the
run cost. Not just code: the system, its data, its schedules, and the paper trail."

**POINT TO:** sweep the six tiles; linger on MIGRATION_PLAN and FEASIBILITY_REPORT.
**THEN:** "And I don't want you to take my word for it. Two things that happened in a real run."

## Slide 14 — Evidence (Real Run)

**SAY:** "Both unscripted. **Left — the Planner refused to write unnecessary code.** Handed a
custom discount engine, it recommended Salesforce CPQ — the native product for pricing — and
generated no custom code. Its own words are on the slide: 'a textbook fit for Salesforce CPQ.'
That's an architect's call, and it means less code to own forever. **Right — the Critic caught a
silently-lost business rule.** A class compiled perfectly but had dropped the 'reject zero-value
orders' check on one path. The Critic blocked it. That's precisely the bug that slips through
manual migrations and detonates in production — caught here before a human ever looked."

**POINT TO:** the quoted verdict boxes on both cards.
**THEN:** "So what's real today versus roadmap? Here's the honest inventory."

## Slide 15 — Current Implementation

**SAY:** "**Everything marked 'shipped' works right now** — code migration, the data model, the
data records, the scheduled jobs, and the full agent team with self-healing verification. The
grey row — Hybris workflow processes and storefront APIs — is next on the roadmap, and we say so
plainly. Concrete maturity markers at the bottom: sixty-three automated tests all passing, three
AI providers including the free offline mode, and every run reports its own cost."

**POINT TO:** the green pills, the one grey pill, the three chips.
**THEN:** "The next question every room asks is security. Let me get ahead of it."

## Slide 16 — Security & Data Handling

**SAY:** "Four commitments. **One — you control where code goes:** only to the AI vendor you
configure; keys live in your settings, never in the product, audited every release. **Two —
a zero-exposure mode:** the whole pipeline can run with nothing leaving the machine — that's also
the free trial path. **Three — the generated code is secure by default:** Salesforce's own
field-level security and sharing rules are the house standard. **Four — nothing destructive:**
deployments are validation-only, a human holds the go-live button, and every AI decision is
logged. And on the roadmap: private hosting for regulated environments."

**POINT TO:** the numbered cards 1–4.
**THEN:** "Bringing it back to the business."

## Slide 17 — The Business Case

**SAY:** "The practical before-and-after. Months of rewriting → a working first draft in minutes
to hours. Silently lost rules → an AI reviewer plus a score that proves preservation. 'Trust me,
it compiles' → deployed and self-corrected until verifiably green. Everything-becomes-custom-code
→ native products recommended where they fit, which means less debt. Black box → a decision log
and a confidence score on every class. And the honest line at the bottom, which I'll say out
loud: **this makes your expert reviewers dramatically faster — it does not remove them, and we're
not pretending it does.**"

**POINT TO:** the red column, the green column, then the green honesty strip.
**THEN:** "Let me pre-empt the usual questions."

## Slide 18 — FAQ

**SAY:** "Six we always get — pick the ones your room cares about: **Does it replace developers?**
No; it replaces the grind — they review a scored draft. **What if the AI invents something?**
Three nets: only provably-existing fields, a second AI review, and it must actually compile
against a real org. **Is our code safe?** It goes only where you send it — or nowhere, in mock
mode. **Cost?** Every report itemizes its own usage. **What can't it do yet?** Workflows and
storefront APIs — and it tells you what it skipped. **Can we try it?** Today. Right-click. Free
mode first."

**POINT TO:** two or three the audience cares about; say "the rest are here for you to read."
**THEN:** "A minute on where this is going."

## Slide 19 — Roadmap

**SAY:** "Built in phases, each de-risking the next. **Phase zero — proving correctness — done.
Phase one — the agent team — done.** Phase two — covering the whole platform — data, schema, and
jobs are done; workflows and storefront APIs are in flight. Phase three is enterprise-grade:
review workspace, audit trail, private models. Phase four is where it starts to learn — every
migration makes the next one better and cheaper. And the through-line, at the bottom: everything
moves along one axis — **from output you have to trust, to output you can verify.**"

**POINT TO:** the two green-topped phases, the amber one, then the green strip.
**THEN:** "Which brings me to the ask."

## Slide 20 — The Ask

**SAY:** "**Give us one real slice of a Hybris codebase — not production, just a real piece —
and we'll hand back verified Salesforce code plus the full receipts on how we got there.** A
pilot is days, not months: free mock mode first, so nothing sensitive leaves your side; a real
scored run second; your team's verdict third. That's the whole ask. Now let me show it running."

**THEN:** switch to the live demo — [DEMO_SCRIPT.md](DEMO_SCRIPT.md) has the step-by-step run.

---

## Presenter cheat-sheet

| If you have… | Do this |
|---|---|
| **8 minutes** | Slides 1, 3, 4, 8, 11, 14, 20. (Story → problem → in/out → the team → the proof loop → evidence → ask.) |
| **20–25 minutes** | All 20 slides as scripted. |
| **+ live demo** | All slides, then [DEMO_SCRIPT.md](DEMO_SCRIPT.md). |
| **A technical skeptic in the room** | Slow down on 6, 7, 11, 12 (architecture, pipeline, healing, grounding). Offer [TDD.md](TDD.md) after. |
| **A security stakeholder** | Slow down on 16; offer [TRD.md](TRD.md) §3 after. |
| **A slide feels too technical mid-flight** | Read its green **"In plain words"** strip aloud and move on. That's what it's for. |

## The three lines to never forget

1. **"It doesn't just write code — it proves the code runs."** (Slide 11)
2. **"It caught a silently-lost business rule before a human ever looked."** (Slide 14)
3. **"It makes your expert reviewers dramatically faster — it doesn't remove them."** (Slide 17)
