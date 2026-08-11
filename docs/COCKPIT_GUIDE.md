# What every screen shows — a guide for demos

**Audience:** anyone presenting the web cockpit.
**How to use it:** read the "Say this" line out loud, then point at the thing.

Every other migration tool converts your code. **This one proves it still behaves the
same** — rule by rule, line by line, against your own org. Nearly every panel below exists
to support that one sentence, so if you only remember one thing, remember that.

---

## The shape of the whole thing

A migration is one run through six stages, with **three points where it stops and waits
for a human**:

```
    scan  →  understand  →  plan  →  build + review  →  reconcile  →  verify
             ▲                ▲                    ▲
          GATE 1           GATE 2               GATE 3
        "is this           "is this            "is this code
      really your          the right              any good?"
        codebase?"           plan?"
```

Everything before Gate 1 is free — no AI is called, nothing is charged. That is why the
cost estimate can be shown *before* you spend anything.

---

## Before you start a run

| Screen | What it is | Say this |
|---|---|---|
| **Landing page** | Point at a codebase (a server path or upload a `.zip`), pick the AI provider, tick *supervised* to stop at the gates | "We point it at a real Hybris codebase. Nothing has been read yet." |
| **Recent migrations** (History) | Every past run, newest first, paginated. Click one to reopen it exactly as it was | "Runs are kept. You can walk back into any of them." |
| **API keys** | Your own provider key, encrypted at rest. Each customer bills their own account | "Your key, your bill. We never see it in plain text." |
| **Account menu** | Sign in / out. Every run belongs to one account and nobody else can open it | "Multi-tenant — your source code is yours." |

**If you upload something that isn't Hybris,** it refuses before creating a run and tells
you why. That's a nice thing to demo deliberately — it also reports any passwords or keys
it found inside the archive.

---

## The three gates (this is the demo)

### Gate 1 — "Review what the AI found in your codebase"

Shown **before a single AI call**. Four things sit on this screen:

| Card | Plain English |
|---|---|
| **Preflight** | "Yes, this really is a SAP Commerce project, version 2211, 17 Java files." Confidence as a percentage. |
| **Forecast** | "This run will cost **$1.59–$3.67** and take 1–2 minutes, plus 1.4–3.7 hours of your review time." A *range*, never one number. If it would blow your spend cap, it says so here — while raising the cap is still cheap. |
| **Target org fit** | Reads **your actual Salesforce org**. "You already have an `Order__c`. Deploying will clash." Found now costs a rename; found at deploy time costs the deploy. |
| **Anti-pattern radar** | Hybris habits that become Salesforce problems — a database query inside a loop will blow a governor limit at real volume. 11 rules. |

> **Say this:** "Before we've spent a penny, it has told us what this codebase is, what it
> will cost, what will break in *your* org, and where the landmines are."

### Gate 2 — "Approve the migration plan"

Every target listed as **Convert** or **Skip**, with a reason. You can flip any of them
before building.

> **Say this:** "The policy is convert everything. If pricing would be better off in
> Salesforce CPQ, we still convert the logic in full — and flag it for review. We never
> silently drop code because a product might do it better."

### Gate 3 — "Review the generated Salesforce code"

Every generated file, with the Critic's findings. You can send anything back for a rework
with feedback, or approve.

---

## The five main tabs

Once the run is going, everything lives under five tabs. Each has sub-tabs.

### 1 · Flow — *live pipeline*

The six stages lighting up as they happen, and every file appearing as it is built.

> **Say this:** "This is live. Nothing is pre-baked."

### 2 · Source — *what we read*

| Sub-tab | What it shows | Why anyone cares |
|---|---|---|
| **Discovery** | The whole repository: an architecture map of how classes depend on each other, the file tree, every class with its methods, and the data model pulled out of `items.xml`. Plus the four Gate-1 cards. | "It read the codebase properly — not a keyword search." |
| **Understanding** | For each class, in plain English: what it's for, **the business rules it contains**, the risks in moving it, what data it reads. | This is the heart of it. "It didn't just translate syntax — it worked out what the code *means*." |
| **Plan** | Every target: convert or skip, the reason, and any 'consider CPQ'-style flag. | "Nothing happens that you didn't approve." |

### 3 · Output — *what we wrote*

| Sub-tab | What it shows |
|---|---|
| **Artifacts** | Each generated file as a card. Four views inside: **Generated code**, **Compare with source** (SAP on the left, Salesforce on the right), **Findings** (what the Critic objected to, with fixes), **What was mapped**. Also **blast radius** — what else breaks if you change this one — and a **Regenerate** button to rebuild just that file. |
| **Compare** | A proper side-by-side diff editor across the whole run. |
| **Files** | The raw generated package — Apex classes, Lightning Web Components, metadata. |

> **Say this** (on Artifacts): "You can disagree with any single file and rebuild just that
> one, without re-running the migration."

### 4 · Assurance — *is it right?*

**This is the tab that wins the deal.** Everything else converts code; this proves it.

| Sub-tab | The question it answers | Plain English |
|---|---|---|
| **Triage** | *Where do I spend my review time?* | Nobody reads 400 generated classes carefully. This ranks them **must review / worth a look / routine**, each with the reasons. "The 12 that matter are at the top." |
| **Rules** | *Did the business logic survive?* | Every business rule found in the SAP code, and whether it is **asserted** (a test proves it), **implemented** (it's there, untested), **at risk**, or **dropped**. Dropped is the one to look for — that's logic no generated code carries. |
| **Alignment** | *Where did this rule go, and what proves it?* | One row per rule: the intent, the Salesforce method that implements it, and the evidence it still holds. A text diff across two languages is useless; this is the useful version. |
| **Parity** | *Does it behave the same?* | We take the **original JUnit tests**, extract what the old code actually did, and replay it against the new Apex. This is golden-master testing. |
| **Origin** | *Where did this code come from?* | Every generated method traced back to the Java method that produced it, with real line numbers. Also the two lists worth checking: Apex with no origin (invented?) and **Java with no Apex counterpart** (lost logic?). |

> **Say this:** "Any tool can give you Apex. The question your architect will ask is 'how do
> I know it still does what it did?' — that's this whole tab."

**A note on line numbers, if someone technical asks:** we never ask the AI for line
numbers. Models are fluent about structure and unreliable about counting, so those come
back plausible and wrong. We locate the symbols in both files ourselves. The numbers are
facts, not opinions.

### 5 · Records — *the paper trail*

| Sub-tab | What it shows |
|---|---|
| **Sign-off** | The audit as a deliverable: who approved which gate, when, on what evidence — and, at the same size beside it, **what this does not certify**. |
| **Reports** | Every document the run produced (14+ markdown files), the **completeness ledger** chips, exactly **what the run cost** per model, and **⬇ Download SFDX package**. |
| **Decisions** | Every AI call, keyed and replayable — the cache as an audit trail. |
| **Audit** | Every agent decision, in order, as it happened. |

> **Say this** (on Sign-off): "Migrations end in an audit. We made the audit a button. And
> notice — if nobody reviewed the run, it says **unreviewed**. It won't pretend."

---

## The two things that impress technical buyers most

**1 — It refuses to overstate.** There is no "100% migrated" badge anywhere, deliberately.
The sign-off lists what it can't prove as prominently as what it can. If no human reviewed
a run, it says so. If the code was never deployed to an org, it says so.

> "Anyone can print a green tick. We'd rather you trust the number when it *is* green."

**2 — Nothing was silently dropped.** The completeness ledger accounts for every single
input class: converted, flagged, skipped (with a reason), or — loudly — unaccounted for.

---

## Also on screen

- **Copilot** — ask questions about the run in plain English ("what was skipped and why?"),
  or tell it to rework a file ("make OrderService use an fflib Selector").
- **Checkpoints** (CLI today) — the run is snapshotted before each gate, so you can go back
  to *before you approved the plan* and compare the two, instead of re-running from zero.

---

## A 10-minute demo path

1. **Landing** → point at the sample Hybris project → tick *supervised* → start.
2. **Gate 1** → walk the four cards. Land on the **cost forecast** and the **org collision**.
3. Approve → **Source › Understanding** → show it extracting real business rules.
4. **Gate 2** → show a *converted + consider CPQ* flag. "We never drop it."
5. Approve → let it build → **Output › Artifacts** → open one file, show **Compare with
   source** and the **Critic findings**.
6. **Assurance › Triage** → "here are the 3 that need you, out of 12."
7. **Assurance › Rules** → the ledger. If anything is *dropped*, show it. Honesty sells.
8. **Records › Sign-off** → the audit. Finish on: *"and it tells you what it can't prove."*
9. **Records › Reports** → ⬇ **Download SFDX package** → "that deploys."

---

## Words to avoid, and what to say instead

| Don't say | Say |
|---|---|
| "100% accurate" | "Every rule is tracked, and it tells you which ones aren't proven yet" |
| "Fully automated" | "Automated, with three points where a human decides" |
| "It's verified" | "It's deploy-verified when you connect an org — otherwise it says it isn't" |
| "It understands your code" | "It extracts the business rules and shows you them, so you can check" |
