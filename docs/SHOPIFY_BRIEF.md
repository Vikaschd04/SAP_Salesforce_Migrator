# Moving from SAP Hybris to Shopify — in plain English

**Date:** 2026-11-11 · **Status:** for stakeholder review · **Slides:** [SHOPIFY_DECK.pptx](SHOPIFY_DECK.pptx) · **Technical detail:** [SHOPIFY_FEASIBILITY.md](SHOPIFY_FEASIBILITY.md)

## The short answer

**Yes, we can build a tool that moves an online store from SAP Hybris to Shopify, and it is a good idea — if we start small.**

- **Can it be done?** Yes. About half of the tool we already have can be reused.
- **Will it convert everything automatically?** No, and no tool could. Shopify works differently from Hybris, so most of a Hybris store is replaced by Shopify's own built-in features rather than copied across.
- **Should we do it?** Yes, in two steps. First, a report-only version that tells a customer exactly where every part of their store goes, which takes about 5–7 weeks to build. Then the full tool, if customers buy the first one.

The one thing to understand: moving to Shopify is less like translating a book and more like moving house. Most of the work is deciding what to bring, what the new place already has, and what to leave behind.

## What this is, in everyday terms

**SAP Hybris is a custom-built house. Shopify is a furnished apartment in a managed building.**

In the custom house, the owner built everything: the plumbing, the wiring, the alarm. In the apartment, the building already provides most of that, and you are not allowed to knock down walls.

So when a company moves from Hybris to Shopify, each part of its store lands in one of four piles:

1. **Left behind, because Shopify already has it** — the checkout page, payments, standard discounts.
2. **Brought across as it is** — products, customers, stock levels.
3. **Rebuilt to fit the new place** — a company's unusual discount, delivery or payment rules.
4. **Kept outside, in a small helper program** — things Shopify will not run inside the building, such as overnight batch jobs.

Our two current tools translate code from one system into another. This one mostly decides which pile each part belongs in, then does the work for each pile.

## What the tool will do, and what it won't

**It will**

- Read the whole Hybris store and list everything it does.
- Say where each part goes in Shopify, and why.
- Write the code for the parts that need it — for example, special discount, delivery and payment rules.
- Prepare products, customers and stock levels to load into Shopify.
- Test the new checkout rules automatically, against how the old store behaved.
- Produce a clear report: what was done, what was set up, and what needs a person.

**It won't**

- Design the new website's look — a designer does that.
- Build the link to the company's SAP back-office systems — an integration team does that.
- Keep every old behaviour exactly — a few things work differently on Shopify, and the tool names each one.
- Promise "100% converted". It promises "100% accounted for": every part has a home and a reason.

## Where the pieces of a Hybris store end up

**Fewer than a third of a Hybris store needs rebuilding for Shopify.** We sorted 28 typical parts of a Hybris store into the four piles. The count is by type of feature, not by size.

| Pile | Parts (of 28) | Examples |
|---|---|---|
| Left behind — Shopify already has it, or it is no longer needed | 10 | Standard discounts, price lists, business-customer accounts, multiple currencies and languages, search |
| Brought across as data | 5 | Products, customers, stock levels, old orders |
| Rebuilt to fit Shopify | 8 | Special discount, delivery and payment rules; checkout and admin screens; the website's pages and look |
| Kept outside in a helper program | 5 | Overnight jobs, automatic reactions to changes, custom business logic, links to other systems |

In other words, most of the work is choosing and setting up Shopify's own features, not writing new code.

## How confident can we be?

**We are most confident exactly where it matters most — the checkout rules — because Shopify gives us a free way to test them.** We are least confident about the parts people still have to finish.

| Area | Confidence | Why |
|---|---|---|
| Finding everything the old store does | High | We already do this for two other migrations; the tool reads the whole store's code |
| Special checkout rules: discounts, delivery, payment | High | Shopify lets us run the new rules on a free test store and compare the results with the old store's behaviour |
| Products, customers and stock levels | High | Loaded into a free test store and counted back, item by item |
| Old orders | Medium | Possible, but slow to move; we usually recommend keeping them in an archive |
| The small helper program outside Shopify | Medium | Checked by a real compiler, but only fully proven once connected to the live store |
| Old rules Shopify does not allow | Low | Some cannot work the same way — for example, a rule that stopped staff saving a wrong price. The tool lists each one for a person to decide |
| The website's look and feel | Low | Rebuilt by designers; the tool lists every page and piece and gives them a starting point |
| Links to SAP back-office systems | Low | Built by an integration team; the tool lists every link it finds and the data each one needs |

**Overall:** high confidence that every part is found and given a home, and that the rebuilt checkout rules work. The website design and the back-office links stay human work, and the report says so.

## Is it a good idea?

**Yes — if we sell it as "every part accounted for", not "everything converted", and start with the report-only version.**

**Why it's a good idea**

- **Customers have to move anyway.** SAP stopped main support for the self-hosted version of Hybris on July 31, 2026.
- **People already pay for this.** Agencies sell this migration as a hand-done service and charge for weeks of analysis up front. Our tool does that analysis automatically.
- **We are half-way there.** About half of what we have already built can be reused.
- **We can prove it works.** Shopify gives free test stores, so the new checkout rules can be tested for real — stronger proof than either of our current tools can give.
- **We can earn early.** The report-only version can be sold before the full tool exists.

**Why we should be careful**

- **Less to show.** Less of the old store turns into code. The value is in the decisions and the evidence, and it has to be sold that way.
- **An expensive plan for customers.** In practice they need Shopify Plus, Shopify's top plan, from about $2,300 a month.
- **Some work stays with people.** Website design and links to SAP back-office systems are not automated.
- **More to look after.** A third product to maintain, on a platform that changed its rules twice in 2026 alone.
- **It changes an earlier decision.** We agreed to support only two migrations, and this takes engineers away from making our current tools handle very large stores.

## Time and effort

**The report-only version could be ready in 5–7 weeks; the full tool in 26–34 weeks with one engineer.**

| Step | How long | What you get |
|---|---|---|
| 1. Report-only version | 5–7 weeks | For each customer: every part of their store, where it goes in Shopify, and what needs a person |
| 2. The full tool (includes step 1) | 26–34 weeks with one engineer; about 17–23 with two | Generated code, data ready to load, automatic testing, and a final sign-off report |

These are estimates based on how long our previous migrations took to build, not measurements. We would decide on step 2 only once step 1 is in customers' hands.

## Common questions

**Will it move everything automatically?** No. It finds everything, says where each part goes, and does the work where it can. A clear list shows what a person must finish.

**Will customers lose their accounts?** No. Customer records move across. Passwords do not — but they don't need to: Shopify customers now sign in with a one-time code sent by email.

**Can old orders be moved?** Yes, but it is slow. We usually recommend keeping old orders in an archive, and moving them only if the business needs them inside Shopify.

**Will the new store behave exactly like the old one?** Mostly. Checkout rules are tested against the old store's behaviour. A few things work differently on Shopify — for example, a custom rule cannot stop a staff member saving a change. The tool lists every such difference.

**Does the customer need a special Shopify plan?** In practice, yes: Shopify Plus, from about $2,300 a month. The custom checkout rules need it.

**Will this affect our two current migrations?** No. They are protected by automatic checks that fail if one migration ever affects another.

**Why not build a brand-new tool from scratch?** It would roughly double the work, and every problem would need fixing twice. Instead it would get its own Shopify-branded website, running on the same engine.

**Does anyone else already do this?** From a first look: agencies do it by hand, and some tools copy products and customers. We did not find one that works through a store's custom code and tests the result. That would be our opening — it needs a proper market check.

## What we need you to decide

Three decisions, in this order:

1. **Do we want a third migration at all?** We earlier agreed to support only two. Our recommendation: yes, starting with the report-only version.
2. **Start with the report-only version?** Our recommendation: yes. It takes 5–7 weeks, can be sold on its own, and tells us whether the full tool is worth building.
3. **Accept that customers will need Shopify Plus?** Our recommendation: yes, and say so upfront.

Two figures here come from outside sources and should be confirmed before they go to a customer: the Shopify Plus price, and the date SAP stopped main support. The design, sources and full risk list are in [SHOPIFY_FEASIBILITY.md](SHOPIFY_FEASIBILITY.md).
