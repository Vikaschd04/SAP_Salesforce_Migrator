# ACME Commerce — SAP Commerce (Hybris) reference project

A realistic multi-extension SAP Commerce codebase, used as the demo and test corpus for
the H2A migrator. The directory layout follows the real platform convention
(`core-customize/hybris/bin/custom/<extension>`, `js-storefront/<app>`), verified against
SAP's own published sample repository.

## What is here

| Extension | Contains |
|---|---|
| `acmecore` | Type system, DAOs, services, an interceptor, a cronjob and an event listener |
| `acmefacades` | Facade + Converter/Populator layer — the standard Hybris DTO pattern |
| `acmeoccaddon` | OCC REST controllers |
| `js-storefront/acmestorefront` | Spartacus components and services |

## Why it looks like this

It is deliberately **not** clean-room code. Real Hybris estates carry patterns that are
hazardous on Salesforce, and a migrator that is only ever tested on tidy code proves
nothing. Present here on purpose:

- a **FlexibleSearch call inside a loop** (`DefaultOrderFulfilmentService.advanceAllocatedOrders`)
  — SOQL-101 territory once migrated
- a Spring **`@Transactional`** boundary, which has no Apex equivalent
- a **session-scoped bean** (`CheckoutContext`) — Apex is stateless
- an **interceptor** enforcing invariants that services alone cannot guarantee
- pricing rules **duplicated** between a service and a populator, which is exactly the
  kind of drift a migration must not silently resolve

## Business rules worth preserving

Concentrated in `DefaultPricingService` and `DefaultOrderFulfilmentService`, and asserted
by the JUnit suites in `testsrc/` — which is also what the characterization harness
replays against the generated Apex.

- orders at or above 5000 receive 10% off
- GOLD and PLATINUM receive a further 12%, SILVER 5%
- promo codes deduct a fixed amount and never take a total below zero
- an order total must be strictly greater than zero
- fulfilment advances one state at a time and never runs backwards
- an order that has shipped or been delivered cannot be cancelled
