# Behavioral Parity Report

Scores how well each generated `@isTest` class asserts the **business rules** comprehended from the Hybris source. This is a proxy for behavioral equivalence — a reviewable checklist, not a dual-execution oracle (that requires a runnable Hybris instance; see the roadmap).

## Summary

- **Overall rule-assertion parity**: 100% (5/5 business rules asserted)
- **Targets with assertion-bearing tests**: 4/4

> A rule counts as *asserted* when the test contains assertions and enough of the rule's distinctive terms appear in the test source. Uncovered rules are the highest-value place to strengthen the generated tests.

## CustomerSelector

- **Source Hybris**: CustomerDao
- **Rule parity**: n/a

**Apex surface:**

- `CustomerSelector.getSObjectFieldList() : List<Schema.SObjectField>`
- `CustomerSelector.getSObjectType() : Schema.SObjectType`
- `CustomerSelector.selectSObjectsById(Set<Id> ids) : List<Customer__c>`
- `CustomerSelector.selectByUids(Set<String> uids) : List<Customer__c>`
- `CustomerSelector.selectByUid(String uid) : Customer__c`
- `CustomerSelector.selectByEmailDomain(String domain) : List<Customer__c>`

_No business rules were comprehended for this target._

## OrderSelector

- **Source Hybris**: OrderDao
- **Rule parity**: 100%

**Apex surface:**

- `OrderSelector.getSObjectFieldList() : List<Schema.SObjectField>`
- `OrderSelector.getSObjectType() : Schema.SObjectType`
- `OrderSelector.selectSObjectsById(Set<Id> ids) : List<Order__c>`
- `OrderSelector.selectByCodes(Set<String> codes) : List<Order__c>`
- `OrderSelector.selectByCode(String code) : Order__c`
- `OrderSelector.selectByPriorities(Set<Integer> priorities) : List<Order__c>`
- `OrderSelector.selectByPriority(Integer priority) : List<Order__c>`

| Business rule (from comprehension) | Asserted in test? |
|---|---|
| Orders can be ranked/filtered by an integer priority | ✅ yes |
| 'priority' field is not declared in items.xml, so reconciliation should add inferred Priority__c (Number) field | ✅ yes |

## OrderService

- **Source Hybris**: DefaultOrderService
- **Rule parity**: 100%

**Apex surface:**

- `OrderService.getSObjectFieldList() : List<Schema.SObjectField>`
- `OrderService.getSObjectType() : Schema.SObjectType`
- `OrderService.selectSObjectsById(Set<Id> ids) : List<Customer__c>`
- `OrderService.selectByUids(Set<String> uids) : List<Customer__c>`
- `OrderService.selectByUid(String uid) : Customer__c`
- `OrderService.selectByEmailDomain(String domain) : List<Customer__c>`
- `OrderService.getSObjectFieldList() : List<Schema.SObjectField>`
- `OrderService.getSObjectType() : Schema.SObjectType`
- `OrderService.selectSObjectsById(Set<Id> ids) : List<Order__c>`
- `OrderService.selectByCodes(Set<String> codes) : List<Order__c>`
- `OrderService.getOrder(Set<Id> orderIds) : List<Order__c>`
- `OrderService.placeOrder(List<Order__c> orders) : List<Order__c>`
- `OrderService.getOrders(List<Id> orderIds) : List<Order__c>`
- `OrderService.placeOrders(List<Order__c> orders) : List<Order__c>`

| Business rule (from comprehension) | Asserted in test? |
|---|---|
| An order total must be greater than zero | ✅ yes |
| Orders with priority greater than 5 are expedited | ✅ yes |
| A customer must exist before an order can be placed for them | ✅ yes |

## OrderController

- **Source Hybris**: OrderController
- **Rule parity**: n/a

**Apex surface:**

- `OrderController.getOrder() : OrderDTO`

_No business rules were comprehended for this target._
