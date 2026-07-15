# How It All Works — A Plain-English Guide

**Version:** 0.7.0 · No technical background required

This explains the whole project simply, as if you've never seen the code.

---

## The problem, in one sentence

A company runs its store on **SAP Hybris** (written in Java) and wants to move to **Salesforce** (which uses its own language, **Apex**) — and rewriting all that code by hand would take months.

## What this tool does

Point it at the old Hybris code. It reads it, understands it, and writes brand-new Salesforce code that does the same thing — automatically. Then, critically, it **checks its own work**: it tries deploying the code to a real Salesforce environment, reads any errors, and fixes them itself before handing it to a person.

Think of it less like a translator and more like a small team of AI engineers: one plans the work, one writes the code, one reviews it critically, and one tests that it actually runs.

## Two ways to use it

1. **VS Code extension (easy way).** Install it, right-click your Hybris folder, click **"H2A: Migrate to Apex"**, watch progress, get a finished `salesforce_<folder>/` project next to your source.
2. **Command line (developer way).** `python -m src.main agent-migrate --input <hybris_dir> --output <out_dir>` — same engine, for scripts or automated pipelines.

Both need an AI key (we use Anthropic's Claude) — or you can run in **`mock` mode** with no key at all, to see the whole pipeline work with clearly-labeled placeholder code, for free.

## The AI "team" that does the work

| Role | What it does, in plain terms |
|---|---|
| **The Planner** | Reads everything first and decides the strategy: "this class should become Salesforce code," or "this one is better handled by a ready-made Salesforce feature instead of custom code," or "this one isn't worth migrating at all." |
| **The Builder** | Actually writes the Salesforce code and a matching set of tests for each piece the Planner assigned. |
| **The Critic** | Reads the Builder's work skeptically — checking it still does what the original did, that it's secure, and that it follows Salesforce's best practices. If it finds a real problem, it sends it back for a fix. |
| **The Verifier** | Takes the finished code and actually tries to deploy it to a real Salesforce environment. If something doesn't compile, it reads the *real* error and fixes it — automatically, in a loop, until it works. |

This team works over a shared "whiteboard" (we call it the Blackboard) — a running record of every decision, so nothing is a mystery. Every run produces a plain document (`MIGRATION_PLAN.md`) showing exactly what was decided and why.

## The journey of your code, step by step

**1. Sort & schedule.** It finds every source file, groups them by business topic (Order, Customer, Product…), figures out which topics depend on which, and translates dependencies first — so a class that needs another class already has it ready.

**2. Understand.** For each piece of code, the AI reads it and writes a short summary: what it does, what business rules it enforces (e.g. "an order total must be positive").

**3. Plan.** The Planner decides what each piece becomes: real Salesforce code, a recommendation to use a built-in Salesforce feature instead, or a decision to skip it entirely.

**4. Build.** For everything marked "build," the AI writes the actual Salesforce code, following Salesforce's own best-practice patterns (the same patterns a senior Salesforce developer would use) — plus a test for every piece.

**5. Review.** The Critic re-reads every piece of generated code with fresh eyes, checking specifically that the *original business logic* survived the translation, that it's secure, and that nothing sloppy slipped through. Anything it's unsure about gets flagged for a human to look at.

**6. Fill in the data model.** Along the way, the tool also builds the actual Salesforce data structures (the equivalent of database tables and columns) — including things like dropdown lists (picklists) and required-field rules, derived from your original Hybris data model.

**7. Move the data.** If your Hybris project has actual data files, those get turned into spreadsheets (CSVs) ready to load into Salesforce, along with a step-by-step guide.

**8. Move the scheduled jobs.** If Hybris had anything running on a timer (like "clean up old orders every night at 2am"), that gets translated into Salesforce's scheduling system too, with the exact same timing.

**9. Prove it works.** If you give it access to a real (test) Salesforce environment, it actually deploys everything there. If anything fails, it reads the real error message and fixes it itself — including automatically strengthening tests if the test coverage isn't high enough to deploy.

**10. Report back.** Finally, it writes a plain report: what got built, how confident it is in each piece (High / Medium / Low), what a human should double-check, and how much this run cost in AI usage.

## Why "check its own work" matters so much

AI can make mistakes — it can write code that looks right but subtly loses a business rule, or references something that doesn't exist. So this tool doesn't stop at "the AI wrote some code." It:
- Only lets the AI use fields and objects that are proven to exist in your data model.
- Has a *second* AI (the Critic) specifically try to poke holes in the *first* AI's work.
- Actually deploys the code and fixes real compiler errors, not just guesses.
- Tracks whether the generated tests actually check the original business rules, not just whether the code "runs."

That's the difference between a tool that *produces* code and one that produces code you can actually trust as a starting point.

## Where to go next

- **Want to see it live?** [DEMO_SCRIPT.md](DEMO_SCRIPT.md)
- **Want to set it up yourself?** [HOW_TO_USE.md](HOW_TO_USE.md)
- **Want the technical detail?** [TDD.md](TDD.md)
- **Want to know what's coming?** [ROADMAP.md](ROADMAP.md)
