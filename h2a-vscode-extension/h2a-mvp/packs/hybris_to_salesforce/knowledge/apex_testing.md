# Apex Testing

## Coverage requirement
- Salesforce requires at least 75% Apex code coverage across the org to deploy to
  production. Aim higher per class; a class with 0% blocks the whole deploy.
- Coverage counts executed lines, but a passing test must also ASSERT behavior —
  lines run is not the same as logic verified.

## Structure
- Test classes are annotated `@isTest` and are `private`.
- Each test method is `@isTest static void ...()`.
- Wrap the code under test in `Test.startTest()` / `Test.stopTest()` — this gives
  a fresh set of governor limits for the measured code and forces queued async
  (`@future`, Queueable, Batch) work to run before assertions.

## Data
- Tests do not see org data by default (`@isTest(SeeAllData=false)`), so create
  the records the test needs — in the method or a `@testSetup` method.

## Assertions
- Assert real outcomes: `System.assertEquals(expected, actual, 'message')`,
  `System.assert(condition, 'message')`. Assert error paths too (use try/catch
  around code that should throw and assert the exception type/message).

## Bulk tests
- Exercise the class with ~200 records to prove bulk-safety and that it stays
  within governor limits.
