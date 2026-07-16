# Demo Hybris Project — Order Management

A small but **complete and realistic** SAP Hybris extension, built for the live migration demo.
It covers one coherent business capability — **Order Management** — and exercises *every* surface
the migrator knows how to convert: Java business logic, the data model, real data, and a scheduled
job. Every method has a real body; nothing here is a stub.

Point the VS Code extension at the **`acmeordermanagement/`** folder (or this whole folder) and run
the migration during the demo.

> This project deliberately contains **only** logic that maps cleanly to Salesforce. There is no
> cart/checkout/session/payment machinery — so the generated Apex deploys without needing anything
> that isn't in a standard org.

---

## What's inside

```
acmeordermanagement/
├── extensioninfo.xml                     Hybris extension descriptor
├── src/com/acme/commerce/order/
│   ├── dao/OrderDao.java                 Data access — 4 parameterised FlexibleSearch queries
│   ├── service/DefaultOrderService.java  Order business rules (place / total / cancel / expedite)
│   ├── service/DefaultPromotionService.java  Discounts, loyalty tiers, promo codes
│   ├── controller/OrderController.java   REST endpoints under /orders
│   ├── controller/OrderSummary.java      REST response object
│   └── job/OrderCleanupJob.java          Nightly job: cancel stale unpaid orders
└── resources/
    ├── acmeordermanagement-items.xml     Data model — 4 types, 3 enums, 3 relations
    ├── acmeordermanagement-spring.xml     Bean wiring + the cron trigger (daily 02:00)
    └── impex/
        ├── customers.impex               5 customers
        ├── products.impex                6 products
        └── orders.impex                  5 orders + 7 line items
```

## How each Hybris piece becomes Salesforce

| Hybris (source) | Salesforce (generated) |
|---|---|
| `OrderDao` (FlexibleSearch) | `OrderSelector` (SOQL, fflib selector pattern) |
| `DefaultOrderService` | `OrderService` Apex class + `OrderServiceTest` |
| `OrderController` (REST) | `@RestResource` Apex REST class |
| `OrderCleanupJob` + cron trigger | `OrderCleanupScheduler implements Schedulable` + a schedule script |
| `items.xml` types / enums / relations | Custom objects, **picklists**, **lookup** fields |
| `*.impex` | Load-ready **CSV** files + an import runbook |
| `DefaultPromotionService` | *(no code)* — Planner recommends **Salesforce CPQ** instead |

## The three moments to point at during the demo

These are planted on purpose so the AI has something meaningful to *decide*, not just transcribe:

1. **A business rule the Critic protects.**
   `DefaultOrderService.placeOrder()` rejects any order whose total is **≤ 0**
   ("Order total must be greater than zero"). Watch that this rule survives into the Apex — and
   note that `orders.impex` contains a deliberately broken **`ORD-9005` with a `0.00` total** to
   make the rule concrete.

2. **A judgement call the Planner makes.**
   `DefaultPromotionService` is classic price/discount logic. On Salesforce that belongs in **CPQ**,
   not hand-written Apex. The Planner should *recommend CPQ and generate no code for it* — which is
   also why the deploy stays clean (no CPQ package needed in the org).

3. **A gap the Reconciler fills from evidence.**
   The Java uses `order.getPriority()` (see `isExpedited()` and `findByMinimumPriority()`), but
   **`priority` is intentionally missing from `items.xml`**. The migrator should detect it is
   genuinely used and add a `Priority__c` field — with the code as evidence, not a guess.

> **Rehearse in mock, demo for real.** Moments **2** and **3** are *AI-judgement* moments — the
> Planner recommending CPQ and the Reconciler adding `Priority__c` from the generated Apex. They
> appear in the **real run with your API key**, not in the free `H2A_PROVIDER=mock` rehearsal
> (which uses a deterministic planner and placeholder code). Use mock to rehearse the *flow* and the
> clean structure; run with the key live to show the intelligence. Moment **1** (the zero-total rule)
> lives in the source itself, so it's visible either way.

---

## Running the migration (during the demo)

**With the VS Code extension** — right-click the `acmeordermanagement` folder → **"H2A: Migrate to
Salesforce"**, with your API key set in the extension settings. Output lands in a sibling folder.

**Or from the command line:**

```bash
cd h2a-mvp && source .venv/bin/activate
python -m src.main agent-migrate \
  --input ../Testing/demo-hybris-ordermgmt/acmeordermanagement \
  --output ../Testing/out-ordermgmt
```

(Add `H2A_PROVIDER=mock` in front for a free, keyless dry run to rehearse the flow.)

---

## How the deploy-verification against your org works — in plain English

You asked: *if I give it a demo org, how does it "check" the migration by deploying?*

Here's the whole idea in one line: **the tool doesn't decide for itself whether the Apex is
correct — it asks Salesforce, by trying to compile the code inside your real org.**

### The mechanism, step by step

1. **You connect the org once.** Using Salesforce's own CLI, you log into your demo org in a browser
   and give it a nickname. From then on the tool can talk to that org.
2. **The tool sends the generated project to the org — as a dry run.** This is a *validate-only*
   deploy (`--dry-run`/check-only). Salesforce **compiles every class and checks every field and
   object, but saves nothing**. Your org is never actually changed.
3. **Salesforce sends back the real result.** Not the tool's opinion — the platform's own compiler
   output: which classes compiled, which failed, and the exact error on the exact line.
4. **The tool reads those real errors and heals them** (this is the self-healing loop):
   - *Missing field?* If the original Java genuinely uses it, the field is added to the data model —
     with the code as proof.
   - *A class won't compile?* The real error message is handed back to the AI, which rewrites that
     class and tries again.
   - *Not enough test coverage?* Salesforce requires **75%** to deploy for real; if the code is
     below that, the tool writes more tests until it clears the bar.
5. **It repeats until the org reports success — or flags what it couldn't fix** for a human. It never
   silently ships something that failed.

> **The key point for stakeholders:** "verified" doesn't mean *the AI thinks it looks right.* It
> means **Salesforce itself compiled it in a real org and it passed.** That's the difference between
> a demo and a promise.

### To turn it on for your demo org

Your demo org: `orgfarm-abdbcce80e-dev-ed` (a Salesforce Developer Edition org).

```bash
# 1. Install the Salesforce CLI (one time)
#    https://developer.salesforce.com/tools/salesforcecli   (or: brew install sf)

# 2. Log into your demo org in the browser and nickname it "demo"
sf org login web --alias demo --instance-url https://orgfarm-abdbcce80e-dev-ed.develop.my.salesforce.com

# 3. Make it the default org the tool deploys to
sf config set target-org demo

# 4. Run the migration WITH verification
python -m src.main agent-migrate \
  --input ../Testing/demo-hybris-ordermgmt/acmeordermanagement \
  --output ../Testing/out-ordermgmt \
  --verify
```

In the extension, tick **"Verify by deploying to Salesforce"** in settings (it adds `--verify` for
you) once the org is connected and set as default.

The result of the verification — deployed / failed, per-class, with coverage — is written into
**`FEASIBILITY_REPORT.md`** in the output folder, alongside the High/Medium/Low confidence score for
every class.

> **Note:** this is a *validate-only* deploy. It compiles and checks against your org but does not
> create records or change anything. It is safe to run against a live org.
