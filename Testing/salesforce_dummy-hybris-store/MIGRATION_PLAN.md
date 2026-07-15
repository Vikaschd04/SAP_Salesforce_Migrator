# Agentic Migration Plan

Produced by the Phase-1 agent team. The Planner decides each target's home (Apex / native Salesforce / skip); the Critic reviews each built artifact for behavior, security, and governor safety.

## 1. Plan

| Target | Pattern | Decision | Rationale |
|---|---|---|---|
| `CustomerSelector` | Selector | Apex | deterministic default (mock/offline: all targets built as Apex) |
| `OrderSelector` | Selector | Apex | deterministic default (mock/offline: all targets built as Apex) |
| `OrderService` | Service | Apex | deterministic default (mock/offline: all targets built as Apex) |
| `OrderController` | Controller | Apex | deterministic default (mock/offline: all targets built as Apex) |
| `OrderCleanupScheduler` | Utility | Apex | deterministic default (mock/offline: all targets built as Apex) |
| `PromotionService` | Service | Apex | deterministic default (mock/offline: all targets built as Apex) |

## 2. Artifact review (Critic)

| Artifact | Status | Findings |
|---|---|---|
| `CustomerSelector.cls` | accepted | none |
| `OrderSelector.cls` | accepted | none |
| `OrderService.cls` | accepted | none |
| `OrderController.cls` | accepted | none |
| `OrderCleanupScheduler.cls` | accepted | none |
| `PromotionService.cls` | accepted | none |

## 3. Decisions log

- **Planner** — planned: 6 targets → 6 Apex, 0 native-recommended, 0 skipped
- **Retriever** — loaded: 19 chunks from bundled Salesforce docs (lexical RAG)
- **Builder** — generated: CustomerSelector (Selector)
- **Critic** — reviewed: CustomerSelector: 0 finding(s) → accepted
- **Builder** — generated: OrderSelector (Selector)
- **Critic** — reviewed: OrderSelector: 0 finding(s) → accepted
- **Builder** — generated: OrderService (Service)
- **Critic** — reviewed: OrderService: 0 finding(s) → accepted
- **Builder** — generated: OrderController (Controller)
- **Critic** — reviewed: OrderController: 0 finding(s) → accepted
- **Builder** — generated: OrderCleanupScheduler (Utility)
- **Critic** — reviewed: OrderCleanupScheduler: 0 finding(s) → accepted
- **Builder** — generated: PromotionService (Service)
- **Critic** — reviewed: PromotionService: 0 finding(s) → accepted
- **DataMigrator** — impex: 3 object(s), 6 record(s) → CSV + runbook
- **JobScheduler** — cronjobs: 1 trigger(s) resolved, 0 unresolved

## 4. Open questions for human review

_(none)_
