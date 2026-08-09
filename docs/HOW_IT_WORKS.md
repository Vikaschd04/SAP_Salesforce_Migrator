# How It All Works — A Plain-English Guide

**Version:** 0.9.3 · No technical background required

This explains the whole project simply, as if you've never seen the code.

---

## The problem, in one sentence

A company runs its store on **SAP Hybris** (written in Java) and wants to move to **Salesforce** (which uses its own language, **Apex**) — and rewriting all that code by hand would take months.

## What this tool does

Point it at the old Hybris code. It reads it, understands it, and writes brand-new Salesforce code that does the same thing — automatically. Then, critically, it **checks its own work**: it tries deploying the code to a real Salesforce environment, reads any errors, and fixes them itself before handing it to a person.

Think of it less like a translator and more like a small team of AI engineers: one plans the work, one writes the code, one reviews it critically, and one tests that it actually runs.

**And it never works behind your back.** At every important moment it stops, shows you what it found or wrote, and waits for you to say "go ahead". You are the one deciding — the AI just does the typing.

## Three ways to use it

1. **The web dashboard (the cockpit).** Open it in a browser, upload a zip of your Hybris code, and watch the whole migration happen live — every step, every decision, every file. This is the one to use if you want to *see* what's happening. It's the easiest way to review and approve as it goes.
2. **VS Code extension.** Install it, right-click your Hybris folder, click **"H2A: Migrate to Apex"**, and get a finished `salesforce_<folder>/` project next to your source.
3. **Command line.** `python -m src.main agent-migrate --input <hybris_dir> --output <out_dir>` — for scripts and automated pipelines.

All three run **exactly the same engine**. There is no "lite" version — the dashboard and the command line produce identical output from identical code. They only differ in how much they show you along the way.

You'll need an AI key (we use Anthropic's Claude, or OpenRouter as an alternative) — or you can run in **`mock` mode** with no key at all. Mock mode makes no internet calls whatsoever, so it works on locked-down corporate laptops, costs nothing, and is perfect for seeing the whole pipeline work end to end with clearly-labelled placeholder code.

## What it can migrate

It handles more than just the Java code:

| What you have in Hybris | What you get in Salesforce |
|---|---|
| Java business logic (orders, pricing, customers) | **Apex** classes, plus a test for each one |
| Your data model (`items.xml`) | **Custom objects and fields** — the Salesforce equivalent of tables and columns |
| The Spartacus storefront (Angular screens) | **Lightning Web Components** — Salesforce's screen technology |
| Data files (ImpEx) | **CSV files** ready to load, plus a step-by-step guide |
| Scheduled jobs (e.g. "clean up at 2am") | **Scheduled Apex**, with the same timing |

## The AI "team" that does the work

| Role | What it does, in plain terms |
|---|---|
| **The Planner** | Reads everything first and decides the strategy: which old classes group together into which new Salesforce pieces, and in what order to build them. |
| **The Builder** | Actually writes the Salesforce code and a matching set of tests for each piece the Planner assigned. |
| **The Critic** | Reads the Builder's work skeptically — checking it still does what the original did, that it's secure, and that it follows Salesforce's best practices. When it finds a problem it also says *how to fix it*, not just that something's wrong. |
| **The Verifier** | Takes the finished code and actually tries to deploy it to a real Salesforce environment. If something doesn't compile, it reads the *real* error and fixes it — automatically, in a loop, until it works. |

This team works over a shared "whiteboard" (we call it the **Blackboard**) — a running record of every decision, so nothing is a mystery. The agents never talk to each other directly; they all read and write that one shared board. That sounds like a technical detail, but it's the reason you can pause the whole thing mid-run, look at anything, and change your mind.

## One important rule: it never quietly drops your logic

Sometimes a chunk of old code would be better served by a ready-made Salesforce product (their pricing engine, their approvals engine, and so on). Older versions of this tool would skip that code and just recommend the product.

**We changed that, deliberately.** Now it converts the logic *anyway*, in full, and adds a note saying "a Salesforce product may be a better long-term home for this — check before go-live."

Why? Because silently skipping code is how migrations lose business rules that nobody notices until something breaks in production. A note you can act on is safe. A gap you never knew about is not.

The only thing it genuinely skips is provably dead code — and even then it has to give a reason, and that reason is written down.

## You are in the loop — the review gates

This is the part that makes it usable on a real project rather than a demo. The migration **stops and waits for you** three times:

**Gate 1 — after it reads your code, before it writes anything.**
You get shown the whole picture: the file tree, how files connect, the architecture, every class it found, and your data model. You review it and decide whether the tool actually understood your system.

> This gate happens **before a single AI call is made**. That's deliberate. If the tool has misunderstood your codebase, you find out at zero cost and walk away having spent nothing.

**Gate 2 — after it plans, before it builds.**
You see the plan: every new Salesforce piece it intends to create, which old classes go into it, and why. Each item comes with what the AI understood about it — its purpose, the business rules it found, the risks it sees, and how complex it thinks the job is.

**Gate 3 — after it builds, before it finishes.**
You see every generated file. You can open any of them side by side with the original Java to compare. If one looks wrong, you can **regenerate just that single file** — you don't re-run the whole migration. If something failed, the error is shown right there so you can deal with it on the spot.

At any gate you can approve, reject with written feedback, or stop entirely. There's also a built-in **Copilot** you can ask questions ("why did you make this a Selector?") and give instructions to ("redo OrderService as a Selector") without leaving the screen.

If you'd rather it just run start to finish, turn supervised mode off and it will.

## Before anything else: is this even the right code?

Point the tool at a folder of holiday photos and it used to start a migration, find
nothing, and walk you through three review screens to tell you so.

Now it looks first, and it does that without using any AI at all:

- **Is this a SAP Commerce project?** It looks for the things only Hybris produces — the
  extension descriptor, the type-system files, ImpEx data, `de.hybris` references in the
  code, or a Spartacus storefront.
- **What is it?** Version, extension names, how much of each kind of file.
- **Is there anything that stops us?** No source to migrate, or none of the markers.
- **Is there anything here that shouldn't have been sent?** Hybris extensions routinely
  ship config files containing **live database passwords and API tokens**. Uploading one
  copies those secrets onto someone else's machine.

If it isn't the right kind of project, you get told immediately and **nothing runs and
nothing is charged**. If it is, but something looks off — credentials in the archive, a
missing data model — you get told that too, at the first review screen, still before any
AI is used.

> **On the credentials check:** it reports the file and line and what kind of secret it
> looks like. It never shows the value, never stores it, and never sends it anywhere. If
> it finds something real, rotate it.

## The journey of your code, step by step

**1. Check & sort.** It confirms the codebase is what you say it is (above), then finds every source file, groups them by business topic (Order, Customer, Product…), figures out which topics depend on which, and translates dependencies first — so a class that needs another class already has it ready. Test files are set aside here, not migrated. *No AI is used in this whole step.* → **you review this**

**2. Understand.** For each piece of code, the AI reads it and writes a short summary: what it does, what business rules it enforces (e.g. "an order total must be positive"), what could go wrong in migration, and how hard it will be.

**3. Plan.** The Planner decides what each piece becomes, and in what order. → **you review this**

**4. Build.** The AI writes the actual Salesforce code, following Salesforce's own best-practice patterns (the same patterns a senior Salesforce developer would use) — plus a test for every piece. Angular screens become Lightning Web Components here too.

**5. Review.** The Critic re-reads every piece of generated code with fresh eyes, checking that the *original business logic* survived, that it's secure, and that nothing sloppy slipped through. → **you review this**

**6. Fill in the data model.** It builds the actual Salesforce data structures — including dropdown lists (picklists) and required-field rules — derived from your original Hybris data model.

**7. Move the data.** Data files become CSVs ready to load into Salesforce, with a step-by-step guide.

**8. Move the scheduled jobs.** Anything that ran on a timer gets translated into Salesforce's scheduling system, with the exact same timing.

**9. Prove it works.** Given access to a real (test) Salesforce environment, it actually deploys everything. If anything fails, it reads the real error message and fixes it itself — including strengthening tests if coverage isn't high enough to deploy.

**10. Report back.** It writes a set of plain documents (see below).

## What you get at the end

Besides the code itself, every run produces documents you can read without being a developer:

| Document | What it tells you |
|---|---|
| `MIGRATION_PLAN.md` | Every decision it made and why — the full audit trail |
| `BUSINESS_RULES.md` | **Every business rule it found, and what happened to it** |
| `FEASIBILITY_REPORT.md` | How confident it is in each piece (High / Medium / Low), and what a human should double-check |
| `DATA_MIGRATION.md` | How to load your data into Salesforce |
| `CRON_JOBS.md` | Your scheduled jobs and their new Salesforce equivalents |
| `PARITY.md` | Whether the generated tests actually check your original rules |

## The number that actually matters

Most migration tools report **"100% of files converted."** That is an easy number to hit and it answers the wrong question. Nobody actually cares how many files moved. What they care about is: *does it still do what it did?*

So we measure something harder. Every business rule the AI finds in your old code — "orders over ₹5,000 get a 10% discount", "refunds are denied after 30 days" — gets tracked individually, all the way through to the finished code. Each one ends up in one of four buckets:

| Bucket | Meaning |
|---|---|
| **Asserted** | The rule is in the new code, and a test checks it |
| **Implemented** | The rule is in the new code, but no test proves it |
| **At risk** | The code that should carry this rule failed to generate |
| **Dropped** | **Nothing in the new code carries this rule at all** |

That last bucket is the important one, and it's the thing no other tool shows you. Those are rules that existed in your old system and silently didn't make it. They're listed first, in red, so you can't miss them.

The headline becomes *"147 of 152 business rules preserved and asserted"* — a number that means something.

> **Being straight with you about this:** "Asserted" means the test *mentions* what the rule is about. That's real evidence, and it's far better than nothing — but it isn't mathematical proof that the new code behaves identically. Treat it as "a test probably covers this," and use a real deployment plus your own testing for proof. We'd rather tell you that than let a green number mislead you.

## Why "check its own work" matters so much

AI can make mistakes — it can write code that looks right but subtly loses a business rule, or references something that doesn't exist. So this tool doesn't stop at "the AI wrote some code." It:

- Only lets the AI use fields and objects that are **proven to exist** in your data model.
- Has a *second* AI (the Critic) specifically try to poke holes in the *first* AI's work.
- Actually deploys the code and fixes **real compiler errors**, not guesses.
- Tracks whether the generated tests actually check your original business rules.
- **Accounts for every single input file.** At the end it proves that every class you gave it was either converted or explicitly skipped-with-a-reason. Nothing can silently vanish.

That's the difference between a tool that *produces* code and one that produces code you can actually trust as a starting point.

## Under the hood — how the thing is actually built

You don't need this section to *use* the tool. But if you're going to trust it with a real migration — or explain it to someone who asks "how does it actually work?" — here's the inside, still in plain words.

The system is built as **five layers stacked on top of each other**, like floors in a building. The rule is simple and it's the whole trick: **each floor only knows about the floor directly below it.** The engine that does migrations has no idea a web browser exists. That sounds pedantic, but it's exactly why the dashboard, the VS Code extension, and the command line can never drift apart — they're all just different front doors into the same building.

```
     Hybris code  ──▶   LAYER 1 · SURFACES        the three front doors
                        LAYER 2 · ORCHESTRATION   the foreman
                        LAYER 3 · AGENTS          the crew + the whiteboard
                        LAYER 4 · CAPABILITIES    the toolbox
                        LAYER 5 · AI GATEWAY      the single door to the AI
                                                                ──▶  Salesforce project
```

### Layer 1 — Surfaces: the front doors

The dashboard, the VS Code extension, and the command line. Their only job is talking to *you* — showing progress, taking your approvals. They contain no migration logic at all. If you deleted all three tomorrow, the engine would still work perfectly; you'd just have no way to talk to it.

### Layer 2 — Orchestration: the foreman

This is the one that runs the job. One file, `orchestrator.py`, is the foreman on the site. It doesn't write any code itself — it decides who does what, in what order, and when to stop and ask you something. Four ideas live here, and they're the ones worth understanding:

**The stage machine — the recipe.**
The whole migration is six numbered steps that always happen in the same order: read the code → understand it → plan → build and review → assemble everything → verify. You can't bake before you've mixed. The foreman announces "starting step 3" and "finished step 3" out loud, which is exactly what you see scrolling past in the dashboard. That's all a "stage machine" is: a recipe it works through, narrating as it goes.

**Wavefronts — doing things at the same time, safely.**
Here's the problem it solves. Some pieces of code depend on others. If `OrderService` uses `OrderDao`, then `OrderDao` has to be built first — otherwise the AI is writing code against something that doesn't exist yet.

But if you take that seriously and do everything one at a time, a big migration takes forever.

So the foreman sorts all the work into **waves**. A wave is a group of pieces that don't depend on each other *at all*, which means every piece in it can be built simultaneously with no risk. It does wave 1 all at once, waits for it to finish completely, then does wave 2 all at once, and so on.

> Think of building a house. You can pour every foundation at the same time — they don't depend on each other. But you can't start any walls until all the foundations are done. Foundations are wave 1, walls are wave 2. You get the speed of doing things in parallel without ever building a wall on wet concrete.

The result is roughly **7× faster** than one-at-a-time — and here's the important part: the finished output is **identical**, character for character. Going faster changes the clock, never the answer.

**Human gates — the pause button.**
These are the three review points described earlier. Technically, the foreman genuinely *stops* — the work halts, mid-migration, and sits there waiting. It isn't running ahead in the background and showing you a replay. Nothing further happens until you click approve. And if you close the tab or hit stop, it stops for real and lets go cleanly, so you can start a fresh run whenever you like.

**Containment — one bad file doesn't kill the job.**
Occasionally the AI just can't convert something. The naive behaviour would be to crash and lose the entire run — which on a 300-class migration would be infuriating.

Instead, the foreman puts a clearly-labelled placeholder in that spot saying *"automatic conversion failed here, this is why, migrate this one by hand"*, marks it in the reports, and carries on with everything else.

> It's the difference between a builder who hits a problem in one room and downs tools for the day, versus one who tapes off that room, notes what's wrong, and finishes the rest of the house.

You end up with 299 converted classes and one honest flag, instead of nothing.

**Checkpointing — autosave.**
It saves its progress continuously as it works. If a run is interrupted halfway — laptop sleeps, connection drops, you hit stop — restarting picks up where it left off instead of starting from zero.

### Layer 3 — Agents: the crew and the whiteboard

This is the Planner, Builder, Critic, and Verifier described earlier. The structural point is *how they communicate*: **they never talk to each other directly.**

Instead there's a big shared whiteboard in the middle of the room — we call it the **Blackboard**. The Planner writes its plan on the board. The Builder reads the plan off the board and writes the finished code back onto it. The Critic reads that code off the board and writes its findings next to it.

Why do it that way? Because it means **you can walk up to the board at any moment and see everything** — every decision, every draft, every objection, in one place. That single design choice is what makes the review gates, the side-by-side code comparison, the regenerate-one-file button, and the full audit trail possible. If the agents just phoned each other, all of that would be invisible and none of those features could exist.

Three quieter helpers live on this floor too:

| Helper | What it does, plainly |
|---|---|
| **The reference library** | A small bundled set of Salesforce rulebooks. Before writing anything, the relevant pages get pulled up and kept open in front of the AI. It's what stops it inventing Salesforce features that don't exist. |
| **The dispatcher** | Picks which AI to use for which task — a cheaper, faster one for the simpler thinking (reading and planning), the expensive one for the hard parts (writing and reviewing code). You don't send a senior architect to do data entry. |
| **The memory** | Remembers what it converted last time and what the code looked like then, so a re-run only redoes what actually changed. |

### Layer 4 — Capabilities: the toolbox

A drawer of single-purpose tools. Each one does exactly one job and knows nothing about the others: *read Java · read the data model · read Angular screens · write Apex · write LWC · check the result · deploy it · trace the business rules · convert the data · convert the scheduled jobs · write the reports.*

They're deliberately dumb and self-contained. That's what makes it possible to test each one on its own and know it works — which is where most of the 85 automated tests point.

### Layer 5 — The AI gateway: one door, with a meter on it

Every single request to the AI — from any agent, any stage — goes through **one door**. Nothing is allowed to sneak around it. Four things live at that door:

| At the door | What it does |
|---|---|
| **The switch** | Which AI you're using: Claude, OpenRouter, or mock (no AI at all). Everything above this floor is written once and works with all three. |
| **The retry** | AI services occasionally get busy and refuse. Across hundreds of calls that stops being bad luck and becomes a certainty, so it waits and tries again, backing off politely rather than hammering. |
| **The notebook** | Remembers answers it already got. Ask the same question twice and it doesn't pay twice. |
| **The meter** | Counts every request and what it cost, which is where your cost report comes from. |

Putting all four in one place is the point. It means no part of the system can accidentally skip the retry, dodge the meter, or bypass your choice of AI — and adding a new AI provider later means changing one file, not fifty.

### Why the layering is the actual feature

Stack those five ideas and you get the property that matters: **the migration engine doesn't know who's asking.** It can't tell whether the request came from a browser, an editor, or a script.

That's why you get identical results from all three, why the web dashboard could be added without changing a single line of how the command line behaves, and why a new front end tomorrow would need no changes to the engine at all.

> Want the same thing as a diagram? See `architecture-diagram.png`, or `ARCHITECTURE_DECK.pptx` for the presentable version.

## Built for real projects, not just demos

A demo migrates 6 files. A real Hybris estate has hundreds. The machinery described above exists for that gap, and here is what it actually buys you — all measured on this repository, not estimated:

| | Result |
|---|---|
| **Speed** | **~7× faster** than one-at-a-time (the waves), with byte-for-byte identical output |
| **Re-runs** | Change nothing and it skips **100%** of the AI work — near-instant, and free. Change one class and it redoes one class. |
| **Failures** | One class failing costs you that class, not the run. An interrupted run resumes instead of restarting. |
| **Cost** | Reported per run and per AI model, so there's never a surprise bill |

And when more than one person uses it:

| | |
|---|---|
| **Accounts** | Everyone signs in. Your migrations — and the source code you uploaded — are visible only to you. Nobody else can list them, open them, or download them. |
| **Your own AI key** | You can store your own, so your runs bill your account rather than a shared one. It is encrypted, and the tool will never show it back to you — you can replace it, not read it. |
| **A queue** | Only so many migrations run at once. The rest wait in line and tell you your position. Each migration is memory-hungry, so an unbounded free-for-all would take the whole thing down. |
| **Nothing is lost** | Close the tab, lose your connection, restart the server — you rejoin the run where you left it, and finished runs stay in your history. |

The re-run number is the one people underestimate. Migrations are never one-shot — you'll run it again and again as you fix things, adjust the plan, and re-review. A tool that charges you full price every time is a tool you use twice and abandon.

## Where to go next

- **See the architecture visually?** `ARCHITECTURE_DECK.pptx` and `architecture-diagram.png`
- **Want to see it live?** [DEMO_SCRIPT.md](DEMO_SCRIPT.md)
- **Want to set it up yourself?** [HOW_TO_USE.md](HOW_TO_USE.md)
- **Want the technical detail?** [TDD.md](TDD.md) and [CODEBASE_GUIDE.md](CODEBASE_GUIDE.md)
- **Want to know what's coming?** [ROADMAP.md](ROADMAP.md)
