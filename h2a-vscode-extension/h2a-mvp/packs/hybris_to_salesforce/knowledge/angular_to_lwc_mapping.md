# Angular (Spartacus) → LWC mapping

Authoritative mapping for translating SAP Spartacus / Angular components to Lightning Web Components.

## Component shell

An Angular `@Component({ selector, templateUrl, styleUrls })` class becomes an LWC **bundle** — a
folder `c/<name>` containing `<name>.js`, `<name>.html`, `<name>.css`, and `<name>.js-meta.xml`.
The JS class `extends LightningElement` and is the `default export`. There is no decorator on the
class itself. Bundle folder + file names are camelCase; the JS class name is PascalCase.

## Inputs and outputs

`@Input() productCode: string;` becomes a public reactive property `@api productCode;` (import
`api` from `lwc`). In markup a parent binds it kebab-cased: `<c-product-detail product-code={code}>`.

`@Output() added = new EventEmitter<Product>();` becomes a DOM event:
`this.dispatchEvent(new CustomEvent('added', { detail: product }));`. Event names must be
all-lowercase, no camelCase. The parent listens with `onadded={handleAdded}`.

## Dependency injection

Angular constructor injection (`constructor(private svc: ProductService)`) has no LWC equivalent —
services become **Apex** the component calls via `@wire` or imperative Apex, or plain JS modules
imported at the top. HttpClient REST calls map to `@AuraEnabled` Apex methods.

## Lifecycle

`ngOnInit()` → `connectedCallback()`. `ngOnDestroy()` → `disconnectedCallback()`.
`ngOnChanges()` has no direct equal; use a getter/setter on the `@api` property.
For data loaded on init, prefer `@wire` (declarative) over calling Apex in `connectedCallback`.

## What has no home

Angular `NgModule`s (declarations/imports/exports) are framework wiring with no LWC equivalent —
they are not converted. RxJS operators become plain JS or `@wire` reactivity.
