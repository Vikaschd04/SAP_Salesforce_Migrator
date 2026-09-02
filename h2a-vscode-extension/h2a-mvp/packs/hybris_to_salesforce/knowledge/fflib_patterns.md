# fflib Apex Enterprise Patterns

A layered architecture that keeps Apex bulk-safe, testable, and separated by concern. Hybris DAO/Service/Controller map cleanly onto it.

## Selector (maps from Hybris DAO / FlexibleSearch)
- Owns ALL SOQL for exactly one SObject. No other layer writes queries.
- Standard methods: `getSObjectFieldList()`, `getSObjectType()`, and bulk
  `selectSObjectsById(Set<Id> ids)` returning a `List<SObject>`.
- Every query is bulk: accept a `Set`/`List` of keys, use bind variables
  (`WHERE Code__c IN :codes`), never a single-record query in a loop.
- Enforce field-level security on read with `Security.stripInaccessible`.

## Service (maps from Hybris Service / Facade)
- Stateless: `public with sharing class`, all `public static` methods.
- Bulkified: accept and return collections (`Map<String, X>`, `List<X>`).
- Contains business logic and orchestration but delegates SOQL to Selectors and
  DML to a Unit of Work (or a single bulk DML). No SOQL/DML in loops.
- Preserve the original business rules exactly (validation, error conditions).

## Controller (maps from Hybris Controller)
- Thin `@RestResource` class. Parse the request, call the Service, return a DTO
  wrapper — no business logic, no SOQL of its own.

## Domain / Unit of Work (optional)
- Domain classes hold record-level behavior/validation for one SObject.
- Unit of Work batches DML across objects in the correct dependency order.
