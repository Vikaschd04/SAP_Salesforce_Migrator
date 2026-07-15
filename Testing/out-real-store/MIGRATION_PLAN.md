# Agentic Migration Plan

Produced by the Phase-1 agent team. The Planner decides each target's home (Apex / native Salesforce / skip); the Critic reviews each built artifact for behavior, security, and governor safety.

## 1. Plan

| Target | Pattern | Decision | Rationale |
|---|---|---|---|
| `CustomerSelector` | Selector | Apex | Standard DAO data-access logic belongs in Apex selector class. |
| `OrderSelector` | Selector | Apex | Query/filter logic on inferred Priority__c field is core data-access in Apex. |
| `OrderService` | Service | Apex | Business validation and order orchestration is genuine service logic for Apex. |
| `OrderController` | Controller | Apex | Controller entry point for order operations maps to Apex controller. |
| `PromotionService` | Service | Native → Salesforce CPQ (price rules/discount schedules) | Discount/promo-code pricing rules are a textbook fit for Salesforce CPQ. |

## 2. Artifact review (Critic)

| Artifact | Status | Findings |
|---|---|---|
| `CustomerSelector.cls` | accepted | 4 |
| `OrderSelector.cls` | accepted | 6 |
| `OrderService.cls` | needs_review | 7 |
| `OrderController.cls` | accepted | 3 |

## 3. Decisions log

- **Planner** — planned: 5 targets → 4 Apex, 1 native-recommended, 0 skipped
- **Retriever** — loaded: 19 chunks from bundled Salesforce docs (lexical RAG)
- **Builder** — generated: CustomerSelector (Selector)
- **Critic** — reviewed: CustomerSelector: 4 finding(s) → accepted
- **Builder** — generated: OrderSelector (Selector)
- **Critic** — reviewed: OrderSelector: 6 finding(s) → accepted
- **Builder** — generated: OrderService (Service)
- **Critic** — reviewed: OrderService: 7 finding(s) → needs_review
- **Builder** — generated: OrderController (Controller)
- **Critic** — reviewed: OrderController: 3 finding(s) → accepted
- **Reconciler** — schema_augmented: +0 object(s), +1 field(s)
- **DataMigrator** — impex: 3 object(s), 6 record(s) → CSV + runbook
- **Parity** — strengthened: 4 rule(s) newly asserted

## 4. Open questions for human review

- [Planner] PromotionService: consider Salesforce CPQ (price rules/discount schedules) instead of custom Apex — Discount/promo-code pricing rules are a textbook fit for Salesforce CPQ.
- [Critic] OrderService: [balanced_braces] Unbalanced braces: 50 open vs 47 close.
- [Critic] OrderService: [java_syntax_leak] Java/Spring annotation found.
- [Critic] OrderService: [BEHAVIOR] The 'order total must be greater than zero' rule attached to getOrder in the Java original is lost. Java's getOrder(code) throws IllegalStateException when totalAmount <= 0; the Apex getOrder(Set<Id>) simply returns selector results with no positive-total validation. This business rule is only enforced in placeOrder, so the getOrder path silently returns non-positive-total orders that the original would have rejected.
- [Critic] OrderService: [COMPILATION] Test assertions use 'System.System.System.assertEquals(...)' which is not a valid Apex identifier and will not compile. Every assertion in OrderServiceTest is affected; should be 'System.assertEquals' (or 'Assert.areEqual').
- [Critic] OrderService: [COMPILATION] The provided OrderServiceTest is truncated mid-method (testPlaceOrderSuccess ends abruptly with no body/closing braces), so the test class as delivered will not compile and cannot demonstrate coverage.
