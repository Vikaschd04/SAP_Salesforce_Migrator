# Behavioral Parity Report

Scores how well each generated `@isTest` class asserts the **business rules** comprehended from the Hybris source. This is a proxy for behavioral equivalence — a reviewable checklist, not a dual-execution oracle (that requires a runnable Hybris instance; see the roadmap).

## Summary

- **Overall rule-assertion parity**: n/a (no business rules were comprehended)
- **Targets with assertion-bearing tests**: 6/6

> A rule counts as *asserted* when the test contains assertions and enough of the rule's distinctive terms appear in the test source. Uncovered rules are the highest-value place to strengthen the generated tests.

## CustomerSelector

- **Source Hybris**: CustomerDao
- **Rule parity**: n/a

**Apex surface:**

- `CustomerSelector.execute(List<Object> records) : List<Object>`

_No business rules were comprehended for this target._

## OrderSelector

- **Source Hybris**: OrderDao
- **Rule parity**: n/a

**Apex surface:**

- `OrderSelector.execute(List<Object> records) : List<Object>`

_No business rules were comprehended for this target._

## OrderService

- **Source Hybris**: DefaultOrderService
- **Rule parity**: n/a

**Apex surface:**

- `OrderService.execute(List<Object> records) : List<Object>`

_No business rules were comprehended for this target._

## OrderController

- **Source Hybris**: OrderController
- **Rule parity**: n/a

**Apex surface:**

- `OrderController.execute(List<Object> records) : List<Object>`

_No business rules were comprehended for this target._

## OrderCleanupScheduler

- **Source Hybris**: OrderCleanupJob
- **Rule parity**: n/a

**Apex surface:**

- `OrderCleanupScheduler.execute(List<Object> records) : List<Object>`

_No business rules were comprehended for this target._

## PromotionService

- **Source Hybris**: DefaultPromotionService
- **Rule parity**: n/a

**Apex surface:**

- `PromotionService.execute(List<Object> records) : List<Object>`

_No business rules were comprehended for this target._
