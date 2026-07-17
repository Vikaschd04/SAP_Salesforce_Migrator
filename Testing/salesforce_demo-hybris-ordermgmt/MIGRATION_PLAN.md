# Agentic Migration Plan

Produced by the Phase-1 agent team. The Planner decides each target's home (Apex / native Salesforce / skip); the Critic reviews each built artifact for behavior, security, and governor safety.

## 1. Plan

| Target | Pattern | Decision | Rationale |
|---|---|---|---|
| `OrderSummary` | Utility | Skip | Pure DTO/utility with no logic to migrate. |
| `OrderSelector` | Selector | Apex | Data-access queries map to Apex SOQL selectors with bound params. |
| `OrderService` | Service | Apex | Core order validation and lifecycle business logic belongs in Apex service. |
| `OrderController` | Controller | Apex | REST/controller delegation layer built as Apex. |
| `OrderCleanupScheduler` | Utility | Apex | Scheduled batch cleanup fits Apex Schedulable/Batch with abort handling. |
| `PromotionService` | Service | Native → Salesforce CPQ | Discounts/promo codes/loyalty pricing fit Salesforce CPQ. |

## 2. Artifact review (Critic)

| Artifact | Status | Findings |
|---|---|---|
| `OrderSelector.cls` | accepted | 3 |
| `OrderService.cls` | needs_review | 8 |
| `OrderController.cls` | needs_review | 7 |
| `OrderCleanupScheduler.cls` | needs_review | 5 |

## 3. Decisions log

- **Planner** — planned: 6 targets → 4 Apex, 1 native-recommended, 1 skipped
- **Retriever** — loaded: 19 chunks from bundled Salesforce docs (lexical RAG)
- **Builder** — generated: OrderSelector (Selector)
- **Critic** — reviewed: OrderSelector: 3 finding(s) → accepted
- **Builder** — generated: OrderService (Service)
- **Critic** — reviewed: OrderService: 8 finding(s) → needs_review
- **Builder** — generated: OrderController (Controller)
- **Critic** — reviewed: OrderController: 7 finding(s) → needs_review
- **Builder** — generated: OrderCleanupScheduler (Utility)
- **Critic** — reviewed: OrderCleanupScheduler: 5 finding(s) → needs_review
- **DataMigrator** — impex: 4 object(s), 23 record(s) → CSV + runbook
- **JobScheduler** — cronjobs: 1 trigger(s) resolved, 0 unresolved
- **Parity** — strengthened: 10 rule(s) newly asserted

## 4. Open questions for human review

- [Planner] OrderSummary: recommended skip — Pure DTO/utility with no logic to migrate.
- [Planner] PromotionService: consider Salesforce CPQ instead of custom Apex — Discounts/promo codes/loyalty pricing fit Salesforce CPQ.
- [Critic] OrderService: [balanced_braces] Unbalanced braces: 91 open vs 89 close.
- [Critic] OrderService: [java_syntax_leak] Java/Spring annotation found.
- [Critic] OrderService: [BEHAVIOR] cancelOrders uses the wrong status guard. The original blocks cancellation of SHIPPED or DELIVERED orders, but the Apex checks for 'COMPLETED' instead — so SHIPPED/DELIVERED orders would be silently cancelled, violating the core rule. Additionally, cancelling an already-CANCELLED order must be a no-op (return silently) in the original, but the Apex throws OrderValidationException instead.
- [Critic] OrderService: [BEHAVIOR] isExpedited semantics are completely changed. The original treats an order as expedited when its numeric priority field is >= 5 (EXPEDITED_PRIORITY_THRESHOLD). The Apex filterExpedited instead flags orders whose TotalAmount > 1000. This is a different business rule on a different field (and Order__c has no priority field at all), so the expedited rule is not preserved.
- [Critic] OrderController: [java_syntax_leak] Java/Spring annotation found.
- [Critic] OrderController: [BEHAVIOR] Cancel rule is too narrow. The business rule / Javadoc restricts cancellation to orders 'not yet shipped', but OrderService.cancelOrders only rejects the exact literal Status__c == 'SHIPPED'. Any post-shipment status (e.g. DELIVERED, COMPLETED, RETURNED) would still be cancellable, which violates the 'not yet shipped' semantics. The service should whitelist cancellable (pre-ship) statuses rather than blacklisting a single value.
- [Critic] OrderCleanupScheduler: [GOVERNOR] A nightly cleanup job that scans ALL orders still NEW/unpaid can accumulate large volumes. This is a plain Schedulable running a single synchronous transaction: OrderSelector.selectStaleUnpaidOrders has no visible LIMIT (risk of >50,000 SOQL rows → uncatchable LimitException) and the single `update d.getRecords()` can exceed the 10,000 DML-row limit. The Java job processed an unbounded list one save at a time; to preserve that at scale this must be implemented as Batch Apex (Database.Batchable), not a single-transaction Schedulable.
