# Apex Governor Limits

Salesforce runs Apex in a shared, multi-tenant environment and enforces per-transaction limits. Exceeding one throws an uncatchable LimitException.

## Key synchronous limits (per transaction)
- Total SOQL queries issued: 100
- Total records retrieved by SOQL: 50,000
- Total DML statements (insert/update/delete/undelete/upsert): 150
- Total records processed by DML: 10,000
- Total SOSL queries: 20
- CPU time on the Salesforce servers: 10,000 ms
- Heap size: 6 MB (synchronous), 12 MB (asynchronous)

## Asynchronous (Batch/Queueable/@future) differences
- SOQL queries: 200; CPU time: 60,000 ms; heap: 12 MB.

## The cardinal rule: bulkify
Never place a SOQL query or a DML statement inside a `for` or `while` loop — a
200-record trigger would blow the 100-query / 150-DML limits instantly. Instead:
- Query once for the whole set using `WHERE Id IN :ids` (bind a Set/List).
- Collect records into a `List<SObject>` inside the loop, then do ONE DML after.

## Symptoms in generated code to avoid
- `[SELECT ...]` or `Database.query(...)` inside a loop body.
- `insert x;` / `update x;` inside a loop body.
- Re-querying the same object per record instead of once for the batch.
