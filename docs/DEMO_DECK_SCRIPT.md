# Speaker Script — Executive Demo Deck

**Companion to:** `DEMO_DECK.pdf` (the 13-slide deck) · **Version:** 0.7.0
**Total talk time:** ~13–15 minutes, then live demo + Q&A

This is the **talk track** — what to *say* over each slide, in plain, human language.
Read it aloud or paraphrase; it's written the way you'd actually speak to a room of
executives who've never seen the product. Each slide has:

- **SAY** — natural narration you can speak directly.
- **POINT TO** — what to gesture at on the slide.
- **THEN** — the one-line bridge into the next slide.

> **How to use it:** don't read it word-for-word — glance at the **SAY** block, then
> talk to the room. The bold first sentence of each is the one line that matters most
> if you're short on time.

---

## Before you start (10 seconds)

**SAY:** "I'm going to show you a tool we've built that takes an old SAP Hybris system
and turns it into working Salesforce code — mostly automatically. It'll take about
fifteen minutes, and then I'll show you a live run. Feel free to stop me with questions
at any point."

---

## Slide 1 — Cover · "From SAP Hybris to Salesforce. Automatically. Verifiably."

**SAY:** "The headline is right there. We take a company running on **SAP Hybris** — an
older e-commerce platform built in Java — and move it to **Salesforce**. The two words
that matter are at the bottom: *automatically*, and *verifiably*. Automatically, because
an AI does the heavy lifting instead of a team of engineers. And verifiably — this is the
part that makes it different — because the tool **proves its own work actually runs**
before any human sees it."

**POINT TO:** the flow — "SAP Hybris → AI Agent Team → Salesforce."

**THEN:** "So let me start with why anyone would want this."

---

## Slide 2 — The Problem

**SAY:** "Today, moving from Hybris to Salesforce means rewriting everything by hand, and
that's painful for three reasons. **First, it's slow** — a normal-sized system has
hundreds of pieces of code, plus data and scheduled jobs. That's not weeks, it's quarters,
sometimes years. **Second, it needs rare people** — engineers who are experts in *both*
platforms, which is one of the most expensive, hardest-to-find skill sets out there.
**And third — the dangerous one — things get quietly lost.** When someone rewrites code by
hand, a business rule like 'never accept an order for zero dollars' can just… disappear.
Nobody notices, until it breaks in production months later."

**POINT TO:** the three red cards, especially "Silent logic loss."

**THEN:** "So here's what we built to fix that."

---

## Slide 3 — What It Does

**SAY:** "In the simplest possible terms: you point it at the old code, and it hands you
back a working Salesforce project. **On the left is what goes in** — the Java business
logic, the data model, the actual data, the scheduled jobs. **On the right is what comes
out** — Salesforce code written the proper way, a test for every piece, all the data and
schedules migrated, and — importantly — a report that tells you exactly what to trust and
what to double-check. And the thing in the middle doing the work isn't one AI — it's a
small *team* of them, which is the interesting part."

**POINT TO:** left box → the gear in the middle → right box.

**THEN:** "Before I introduce the team, here's the four-step journey your code takes."

---

## Slide 4 — How It Works

**SAY:** "It works the same way a really good engineering team would. **Step one, it
understands** — it reads every file, works out which parts depend on which, and writes
down the business rules it finds, *before* writing a single line of new code. **Step two,
it plans** — it decides what each piece should become, including what should *not* be
custom code at all. **Step three, it builds and reviews** — it writes the code and tests,
and then a *second* AI reviews that work critically. **And step four, it proves it** — it
deploys the code to a real Salesforce environment and fixes any real errors itself, in a
loop, until it works. Every decision it makes gets written down in plain English, so it's
never a black box."

**POINT TO:** the four numbered circles, left to right.

**THEN:** "Let me introduce that team, because this is really the heart of it."

---

## Slide 5 — The AI Team

**SAY:** "Instead of asking one AI to do everything and hoping for the best, we split the
job across four specialists that check each other — just like a real team. **The Planner**
reads the whole codebase and sets the strategy. **The Builder** writes the actual code and
tests. **The Critic** — think of it as the skeptical senior reviewer — reads the Builder's
work and tries to poke holes in it. **And the Verifier** actually deploys it and confirms
it runs. Look at the little quotes on each card — that's the personality of each one. My
favourite is the Planner saying 'this shouldn't be custom code — Salesforce already has a
product for that.' That's a judgement call, and the AI makes it."

**POINT TO:** each card in turn; then the "shared whiteboard" strip at the bottom.

**SAY (on the whiteboard):** "And they all work off a shared whiteboard — a running record
of every decision and every question — which comes out as a plain document you can read
after every run."

**THEN:** "Now, the natural question is: can you actually *trust* what a bunch of AIs
produce? Here's the answer."

---

## Slide 6 — Why You Can Trust the Output

**SAY:** "This is the slide I'd put money on being the reason to buy. Most AI tools stop at
'the AI wrote some code.' We don't. **We take the code and actually deploy it to a real
Salesforce environment.** If it doesn't work, we read the *real* error message — not a
guess — and fix it automatically. If the code references a field that's missing, we add it.
If the code is broken, we repair it. And if Salesforce's own rule says you need 75% test
coverage to go live and we're below it, the tool writes more tests until it clears the bar.
It loops until everything is green. And anything it *isn't* confident about, it flags for a
human — it never quietly ships something it's unsure of."

**POINT TO:** the four-step loop, then the three cards — Grounded, Reviewed, Scored.

**SAY (on the three cards):** "Three safety nets underneath all of it: it can only use data
fields that provably exist, so it can't invent things; a second AI independently challenges
the first one's work; and every single class gets a confidence score, so your reviewers
know exactly where to spend their time."

**THEN:** "And I don't want you to take my word for any of this — so here are two things
that happened in a *real* run, that we didn't script."

---

## Slide 7 — Seen In A Real Run

**SAY:** "Two real moments. **On the left — the Planner's judgement.** We handed it a custom
discounts-and-promotions engine. A naive tool would just translate it. Instead, the Planner
*refused* to write custom code, and recommended we use **Salesforce CPQ** — the ready-made
Salesforce product built exactly for pricing rules. Its own words: 'discount and promo-code
pricing rules are a textbook fit for CPQ.' That's an architect's decision — it means less
code to maintain forever. **On the right — the Critic's catch.** The first version of a
class *compiled perfectly* — looked completely fine — but it had quietly dropped that
'reject zero-dollar orders' rule on one path. The Critic caught it and blocked it. That is
*exactly* the kind of bug that slips through a manual migration and blows up in production —
and here it was caught before a human even looked at the code."

**POINT TO:** left card, then right card, then the highlighted "verdict" boxes.

**THEN:** "So that's how it works. Here's what's actually built and working today — no
vapourware."

---

## Slide 8 — Current Implementation

**SAY:** "Everything with a green 'shipped' label is working right now. **The code
migration** is done. **The data model** — objects, fields, dropdowns, relationships — done.
**The actual data records** — done, turned into load-ready files with a safe re-runnable
import guide. **The scheduled jobs** — done, same timing preserved. And **the whole AI team
plus the self-verification loop** — done. The one on the roadmap, in grey, is Hybris's
workflow engine and storefront APIs, which are next. And to be concrete about maturity:
sixty-three automated tests, all passing; three AI providers including a completely free
offline mode for safe evaluation; and every run reports its own cost."

**POINT TO:** the green rows, then the three chips at the bottom.

**THEN:** "Now, the question a room like this always asks next is about security. Let me get
ahead of it."

---

## Slide 9 — Security & Data Handling

**SAY:** "Four things. **One — you control where your code goes.** It's only ever sent to the
AI provider *you* choose, and your keys live in your settings, never bundled into the product
or committed anywhere. **Two — there's a zero-exposure mode.** You can run the entire thing in
'mock' mode where *nothing* leaves your machine — perfect for sensitive code or a free trial.
**Three — the code it writes is secure by default** — it enforces Salesforce's own field-level
security and record-sharing rules as a house standard. **And four — nothing destructive
happens.** Every deployment is a validation-only dry run; a human always holds the final
'go live' button; and every AI decision is logged and auditable."

**POINT TO:** each of the four security cards.

**THEN:** "So let me bring it back to the business."

---

## Slide 10 — The Business Case

**SAY:** "Same story, the practical version. **Months of manual rewriting** becomes a working
first draft in minutes to hours. **Business rules getting silently lost** becomes a dedicated
AI reviewer that checks they survived, with a score to prove it. **'Trust me, it compiles'**
becomes 'it deployed to a real environment and self-corrected until it was verifiably green.'
And instead of *everything* becoming custom code you own forever, the tool actively points you
to native Salesforce products where they fit — which means less long-term debt. I want to be
honest about the positioning, though" — **point to the line at the bottom** — "this gives you a
strong, *verified* first draft plus a prioritized review list. It makes your expert reviewers
dramatically faster. It doesn't remove them — and we're not pretending it does."

**POINT TO:** the before/after rows; land on the honesty line at the bottom.

**THEN:** "Let me pre-empt the questions I know you're all thinking."

---

## Slide 11 — Common Questions

**SAY:** "The six we always get. **'Does this replace our developers?'** No — it replaces the
*grind*; they review a scored draft instead of rewriting from scratch. **'What if the AI makes
something up?'** Three nets — it can only use fields that exist, a second AI reviews everything,
and it has to actually compile against a real org. **'Is our code safe?'** It goes only where
you send it, or nowhere at all in mock mode. **'What does it cost?'** Every run itemizes its own
usage, and it uses cheaper models for the simple steps automatically. **'What can't it do yet?'**
Workflows and storefront APIs — and it tells you honestly what it skipped. **'Can we try it on
our code?'** Yes — today, with a right-click, for free in mock mode first."

**POINT TO:** whichever question the room actually cares about — you don't have to read all six;
pick two or three and say "the rest are here for you to read."

**THEN:** "A quick word on where this is heading, then I'll show you a live run."

---

## Slide 12 — Where This Is Going

**SAY:** "We built this in phases, and each one de-risks the next. **Phase zero was proving
correctness** — the self-healing, the confidence scoring — done. **Phase one was building the
AI team** — done. **Phase two is covering the whole platform** — data, schema, and scheduled
jobs are done; workflows and storefront APIs are what we're on now. **Phase three is
enterprise-grade** — a review workspace, audit trails, and private model hosting for regulated
environments. **And phase four is where it starts to learn** — every migration makes the next
one better and cheaper. The single thread through all of it is at the bottom: moving from output
you have to *trust*, to output you can *verify*."

**POINT TO:** the five phase cards; land on the "trust → verify" line.

**THEN:** "So here's the ask."

---

## Slide 13 — The Ask

**SAY:** "Give us one real slice of a Hybris codebase — not production, just a real piece — and
we'll hand back verified Salesforce code, plus the full receipts on how we got there. A pilot is
days, not months. We'd start in the free mock mode so nothing sensitive leaves your side, then
do a real scored run, and then your team gives the verdict. That's it. Now — let me actually show
it to you running."

**POINT TO:** the three chips — "live demo today," "full docs," "pilot-ready."

**THEN:** transition to the **live product demo** — see [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for the
step-by-step run on the sample project (right-click → migrate → walk through the output).

---

## Presenter cheat-sheet (keep this visible)

| If you have… | Do this |
|---|---|
| **5 minutes** | Slides 1, 3, 6, 7, 13. (Problem → what it does → why trust it → real proof → the ask.) |
| **15 minutes** | All 13 slides as scripted above. |
| **15 min + live demo** | All slides, then the run in [DEMO_SCRIPT.md](DEMO_SCRIPT.md). |
| **A skeptical technical person in the room** | Lean into Slides 6 and 7 — the self-healing loop and the real Critic catch. Offer them [TDD.md](TDD.md) afterward. |
| **A security-focused stakeholder** | Slow down on Slide 9; offer [TRD.md](TRD.md) §3 afterward. |

## The three lines to never forget

1. **"It doesn't just write code — it proves the code runs."** (Slide 6)
2. **"It caught a business rule that was silently lost — before a human ever looked."** (Slide 7)
3. **"A strong verified first draft that makes your experts faster — not a replacement for them."** (Slide 10)
