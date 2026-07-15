# SOQL, DML, and Security

## SOQL best practices
- Use bind variables (`:codes`) — never string-concatenate user input into SOQL
  (SOQL injection). With dynamic `Database.query`, use `String.escapeSingleQuotes`.
- Filter to the working set with `WHERE Id IN :ids` / `WHERE Code__c IN :codes`.
- For very large result sets iterate with a SOQL for-loop:
  `for (Account a : [SELECT Id FROM Account WHERE ...]) { ... }`.

## DML best practices
- Operate on lists: build a `List<SObject>` then a single `insert list;`.
- Use `Database.insert(list, false)` for partial-success + per-row error handling.
- Never DML inside a loop.

## Field-Level Security (FLS) and CRUD
- Read: `SObjectAccessDecision d = Security.stripInaccessible(AccessType.READABLE, records);`
  then `d.getRecords()` — removes fields the running user can't see.
- Write: `Security.stripInaccessible(AccessType.CREATABLE, records)` before insert,
  `AccessType.UPDATABLE` before update.
- Alternatively enforce in the query with `WITH SECURITY_ENFORCED`.

## Sharing
- Add `with sharing` to any class that queries or modifies records so row-level
  sharing rules apply. Services and Controllers should be `with sharing`.
