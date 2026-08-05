# How It All Works — A Plain-English Guide

**Version:** 0.9.2 · No technical background required

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

## The journey of your code, step by step

**1. Sort & schedule.** It finds every source file, groups them by business topic (Order, Customer, Product…), figures out which topics depend on which, and translates dependencies first — so a class that needs another class already has it ready. *No AI is used here; it's ordinary code reading.* → **you review this**

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

## Built for real projects, not just demos

A demo migrates 6 files. A real Hybris estate has hundreds. Four things make that difference survivable:

**It's fast.** It works on many classes at once instead of one at a time — about **7× faster** on a typical repository. It's careful about ordering, so the result is *identical* to running them one by one, just quicker.

**It doesn't redo finished work.** Migrations are never one-shot; you'll run it again and again as you fix things. On a re-run it only re-does the classes that actually changed. Change nothing and it skips **100%** of the AI work — near-instant, and free.

**It survives failures.** Over hundreds of AI calls, occasional failures are a certainty, not a risk. It retries intelligently, and it saves progress as it goes — so if a run is interrupted, restarting picks up where it stopped instead of starting over. If one class fails outright, it's flagged for manual work and the rest of the run continues; one bad file never kills the job.

**It tells you what it costs.** You see exactly how much each run spent, broken down by AI model. It also uses a cheaper AI for the simpler thinking (reading and planning) and saves the expensive one for the hard parts (writing and reviewing code).

## Where to go next

- **See the architecture visually?** `ARCHITECTURE_DECK.pptx` and `architecture-diagram.png`
- **Want to see it live?** [DEMO_SCRIPT.md](DEMO_SCRIPT.md)
- **Want to set it up yourself?** [HOW_TO_USE.md](HOW_TO_USE.md)
- **Want the technical detail?** [TDD.md](TDD.md) and [CODEBASE_GUIDE.md](CODEBASE_GUIDE.md)
- **Want to know what's coming?** [ROADMAP.md](ROADMAP.md)
