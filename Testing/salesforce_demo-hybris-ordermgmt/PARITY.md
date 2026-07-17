# Behavioral Parity Report

Scores how well each generated `@isTest` class asserts the **business rules** comprehended from the Hybris source. This is a proxy for behavioral equivalence — a reviewable checklist, not a dual-execution oracle (that requires a runnable Hybris instance; see the roadmap).

## Summary

- **Overall rule-assertion parity**: 85% (22/26 business rules asserted)
- **Targets with assertion-bearing tests**: 4/4

> A rule counts as *asserted* when the test contains assertions and enough of the rule's distinctive terms appear in the test source. Uncovered rules are the highest-value place to strengthen the generated tests.

## OrderSelector

- **Source Hybris**: OrderDao
- **Rule parity**: 100%

**Apex surface:**

- `OrderSelector.getSObjectFieldList() : List<Schema.SObjectField>`
- `OrderSelector.getSObjectType() : Schema.SObjectType`
- `OrderSelector.selectSObjectsById(Set<Id> ids) : List<Order__c>`
- `OrderSelector.selectByCodes(Set<String> codes) : List<Order__c>`
- `OrderSelector.selectByCode(String code) : Order__c`
- `OrderSelector.selectByStatuses(Set<String> statuses) : List<Order__c>`
- `OrderSelector.selectStaleUnpaidOrders(Datetime cutoff) : List<Order__c>`
- `OrderSelector.selectByMinimumPriority(Decimal minPriority) : List<Order__c>`

| Business rule (from comprehension) | Asserted in test? |
|---|---|
| findByCode returns null when no match, else first result | ✅ yes |
| findByStatus orders results newest first by orderDate descending | ✅ yes |
| Stale orders defined as unpaid (paid=false), status=NEW, and orderDate strictly before cutoff — used by nightly cleanup to cancel abandoned orders | ✅ yes |
| findByMinimumPriority is inclusive lower bound; higher priority ships first, ordered priority descending | ✅ yes |
| All inputs bound as query parameters, never concatenated (SQL injection safe); no business logic in this read layer | ✅ yes |

## OrderService

- **Source Hybris**: DefaultOrderService
- **Rule parity**: 67%

**Apex surface:**

- `OrderService.selectByCodes(Set<String> codes) : List<Product__c>`
- `OrderService.selectByUids(Set<String> uids) : List<Customer__c>`
- `OrderService.selectByCodes(Set<String> codes) : List<Order__c>`
- `OrderService.createOrders(List<OrderRequest> requests) : List<Order__c>`
- `OrderService.cancelOrders(Set<String> orderCodes) : List<Order__c>`
- `OrderService.filterExpedited(List<Order__c> orders) : List<Order__c>`
- `OrderService.createOrders(List<OrderService.OrderRequest> requests) : List<Order__c>`
- `OrderService.cancelOrders(List<String> orderCodes) : List<Order__c>`

| Business rule (from comprehension) | Asserted in test? |
|---|---|
| Order code must not be null or blank | ✅ yes |
| Throws ModelNotFoundException if no order exists for a code | ✅ yes |
| An order must have a customer | ✅ yes |
| An order must contain at least one entry | ✅ yes |
| Every order entry must have a positive quantity | ✅ yes |
| Each entry's product must exist and be active | ✅ yes |
| Product stock level must be sufficient for entry quantity | ✅ yes |
| Order total (sum of quantity × unit price) must be strictly greater than zero — zero-value orders rejected | ✅ yes |
| New orders are created with status NEW, unpaid, and current order date | ❌ **no — strengthen test** |
| Orders in SHIPPED or DELIVERED status cannot be cancelled | ❌ **no — strengthen test** |
| Cancelling an already CANCELLED order is a no-op | ❌ **no — strengthen test** |
| Orders with priority >= 5 (EXPEDITED_PRIORITY_THRESHOLD) are treated as expedited | ❌ **no — strengthen test** |

## OrderController

- **Source Hybris**: OrderController
- **Rule parity**: 100%

**Apex surface:**

- `OrderController.doGet() : OrderSummary`
- `OrderController.doPost() : void`

| Business rule (from comprehension) | Asserted in test? |
|---|---|
| Status string is parsed case-insensitively via OrderStatus.valueOf(status.toUpperCase()) | ✅ yes |
| Order summary status is null-safe: null when order status is null, otherwise status code | ✅ yes |
| Expedited flag on summary is determined by orderService.isExpedited | ✅ yes |
| Order cancellation restricted to orders not yet shipped (enforced in service, per Javadoc) | ✅ yes |
| No business rules reside in the controller; logic delegated to the order service | ✅ yes |

## OrderCleanupScheduler

- **Source Hybris**: OrderCleanupJob
- **Rule parity**: 100%

**Apex surface:**

- `OrderCleanupScheduler.execute(SchedulableContext sc) : void`

| Business rule (from comprehension) | Asserted in test? |
|---|---|
| Orders still in NEW status and unpaid after 7 days are considered abandoned | ✅ yes |
| Abandoned orders are transitioned from NEW to CANCELLED | ✅ yes |
| Cutoff date is calculated as current date minus 7 days | ✅ yes |
| Job checks for abort signal before each cancellation and stops gracefully if requested | ✅ yes |
