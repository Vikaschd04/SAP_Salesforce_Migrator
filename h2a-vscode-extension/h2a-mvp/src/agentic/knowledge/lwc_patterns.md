# LWC component patterns

Conventions for well-formed, deployable Lightning Web Components.

## Bundle structure

A component `c/productList` is a folder with, at minimum, `productList.js`, `productList.html`,
`productList.js-meta.xml`, and optionally `productList.css`. Jest tests live in
`__tests__/productList.test.js`. File names match the folder (camelCase); the JS class is PascalCase
(`ProductList`) and is the default export.

## The JavaScript class

```js
import { LightningElement, api, wire, track } from 'lwc';

export default class ProductList extends LightningElement {
    @api recordId;            // public, reactive (set by a parent or page)
    products = [];            // private reactive (plain field — reassign to re-render)
    error;

    get hasProducts() {       // computed values live in getters, not the template
        return this.products.length > 0;
    }
}
```
`@track` is only needed to make deep mutations of objects/arrays reactive; reassigning a field is
usually enough. Never mutate an `@api` property from inside the component.

## The .js-meta.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<LightningComponentBundle xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>60.0</apiVersion>
    <isExposed>true</isExposed>
    <targets>
        <target>lightning__AppPage</target>
        <target>lightning__RecordPage</target>
        <target>lightning__HomePage</target>
    </targets>
</LightningComponentBundle>
```
`isExposed` must be true for the component to be usable in App Builder / as a child; without valid
targets a deploy of an exposed component is rejected.

## Events (child → parent)

Dispatch a `CustomEvent` (lowercase name) instead of an Angular `@Output`:
```js
this.dispatchEvent(new CustomEvent('addtocart', { detail: { code: product.code }, bubbles: true }));
```

## Governor-limit awareness

Data comes from Apex; the same limits apply. Never trigger a per-row Apex call inside a `for:each`;
fetch in bulk with one `@wire`/imperative call and render the collection.

## Accessibility

Preserve semantics from the source: `alt` on images, `<label>` for inputs, button text, and ARIA
roles. Prefer Salesforce Lightning Base Components (`lightning-button`, `lightning-input`,
`lightning-card`) which are accessible by default.
