# Demo Spartacus Storefront — Frontend Migration Sample

A small but **complete and realistic** SAP Spartacus (Angular) storefront slice, built for
the frontend migration demo. It covers the classic storefront trio — **Product List (PLP)**,
**Product Detail (PDP)**, and **Cart** — with real component logic, services, RxJS, and
templates. Every method has a real body; nothing here is a stub.

Point the migrator at the **`storefront/`** folder and it converts each Angular component into
a **Lightning Web Component (LWC)** bundle, wiring data access to `@AuraEnabled` Apex.

> This pairs with `demo-hybris-ordermgmt` (the backend): the storefront consumes the same
> Product/Order data model, so a full demo shows **backend → Apex** *and* **frontend → LWC**.

---

## What's inside

```
storefront/src/app/
├── models/product.model.ts          Product + CartItem interfaces
├── services/
│   ├── product.service.ts           Catalogue reads (HttpClient) → @AuraEnabled Apex
│   └── cart.service.ts              Client-side cart state (BehaviorSubject) + rules
├── product-list/  (PLP)             @Component, *ngFor, filter + sort, add-to-cart
├── product-detail/ (PDP)            @Input productCode, @Output added, quantity + stock rules
├── cart/          (Cart)            line items, remove, running total (getter), checkout event
└── storefront.module.ts            NgModule (framework glue)
```

## How each Angular concept becomes LWC

| Angular (source) | LWC (generated) |
|---|---|
| `@Component({selector, templateUrl})` | an LWC bundle: `.js` + `.html` + `.css` + `.js-meta.xml` |
| `@Input() productCode` | `@api productCode` |
| `@Output() added = EventEmitter` | `this.dispatchEvent(new CustomEvent('added', …))` |
| `*ngFor="let p of items"` | `<template for:each={items} for:item="p">` |
| `*ngIf="loading"` | `<template if:true={loading}>` |
| `{{ price \| currency }}` | a getter `get formattedPrice()` (LWC allows only property refs in `{ }`) |
| `ProductService` (HttpClient REST) | imperative Apex / `@wire` to `@AuraEnabled` controller |
| RxJS `Observable` / `subscribe` | reactive properties / `@wire` |
| `(click)="addToCart()"` | `onclick={addToCart}` |
| `StorefrontModule` (NgModule) | **Skipped** — framework glue, logged with a reason |

## The demo moments to point at

1. **Real behavior preserved, not just markup.** PDP enforces "quantity bounded by stock" and
   "no add when out of stock / inactive"; Cart caps quantity at stock and computes the total.
   Watch these survive into the LWC JS.
2. **Template intelligence.** Angular allows expressions like `{{ price | currency }}` in the
   template; LWC does **not**. The migrator must lift these into JS **getters** — a real
   Angular→LWC gotcha the agents handle.
3. **Frontend↔backend wiring.** `product.service.ts` calls a REST catalogue; the migrator
   generates an `@AuraEnabled(cacheable=true)` Apex controller (`ProductController.getProducts`)
   and wires the LWC to it with `@wire` — the industry-standard LWC + Apex pattern.

---

## Running the migration

```bash
cd h2a-mvp && source .venv/bin/activate
python -m src.main agent-migrate \
  --input ../Testing/demo-spartacus-storefront/storefront \
  --output ../Testing/out-storefront
```
(Prefix `H2A_PROVIDER=mock` for a free, keyless rehearsal of the flow.)

Output LWC bundles land in `force-app/main/default/lwc/{productList,productDetail,cart}/`,
alongside the generated `@AuraEnabled` Apex controller in `.../classes/`.
