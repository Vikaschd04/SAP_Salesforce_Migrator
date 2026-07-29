# Demo Commerce Suite — Complete End-to-End Migration

The **one folder that has everything**: a coherent SAP Commerce slice with a Java/Spring
**backend**, its **data model + real data + a scheduled job**, and a Spartacus (Angular)
**frontend** — all sharing the same Order/Product/Customer domain. Point the migrator at this
folder and one run produces a full Salesforce project: Apex + SObjects + picklists + lookups +
CSV data + a schedule runbook + Lightning Web Components.

```
demo-commerce-suite/
├── backend/                         SAP Hybris extension (Order Management)
│   ├── src/…                        DAO, Service, PromotionService, Controller, cleanup Job (Java)
│   └── resources/
│       ├── *-items.xml              data model: Customer, Product, Order, OrderEntry + enums + relations
│       ├── *-spring.xml             cron trigger (nightly cleanup)
│       └── impex/*.impex            seed data: 5 customers, 6 products, 5 orders
└── frontend/                        SAP Spartacus storefront (Angular)
    └── src/app/
        ├── product-list/ (PLP)      *ngFor catalogue, filter/sort, add-to-cart
        ├── product-detail/ (PDP)    @Input/@Output, quantity + stock rules
        ├── cart/                    line items, total getter, checkout event
        └── services/                ProductService (REST), CartService (state)
```

## What one migration produces

| From | To |
|---|---|
| `backend/src/**/*.java` | Apex — `OrderSelector`, `OrderService`, **`PromotionService` (converted + CPQ review flag)**, `OrderController`, `OrderCleanupScheduler` |
| `backend/resources/*-items.xml` | Custom objects + **picklists** + **lookups** |
| `backend/resources/impex/*.impex` | Load-ready **CSVs** + `DATA_MIGRATION.md` |
| `backend/resources/*-spring.xml` | Scheduled Apex + `CRON_JOBS.md` |
| `frontend/**/*.component.ts` | **LWC bundles** — `lwc/productList`, `lwc/productDetail`, `lwc/cart` (+ `@AuraEnabled` Apex controllers) |
| NgModule / TS interfaces | Skipped **with a reason** (framework glue / type-only) — see the completeness ledger |

## Run it

```bash
cd h2a-mvp && source .venv/bin/activate

# Free, keyless — proves the whole pipeline end-to-end (structure, completeness, wiring):
H2A_PROVIDER=mock python -m src.main agent-migrate \
  --input ../Testing/demo-commerce-suite --output ../Testing/out-suite

# Real AI translation (needs a valid key) — the actual code quality + CPQ flagging:
python -m src.main agent-migrate \
  --input ../Testing/demo-commerce-suite --output ../Testing/out-suite
```

Every run ends with a **completeness ledger** (`converted | flagged | skipped | unaccounted`) in
`MIGRATION_PLAN.md` and `FEASIBILITY_REPORT.md` — the proof that no logic was silently dropped.
