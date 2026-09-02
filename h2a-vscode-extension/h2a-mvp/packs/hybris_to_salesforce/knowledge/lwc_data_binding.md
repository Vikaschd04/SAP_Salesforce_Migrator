# LWC template data binding (the getter rule)

## Templates allow property references only — never expressions

The single biggest Angular→LWC gotcha. Angular templates evaluate expressions and pipes inline:
`{{ product.price | currency }}`, `{{ a + b }}`, `*ngIf="items.length > 0"`. **LWC templates
cannot do this.** `{ }` may contain only a property or getter reference — no operators, no function
calls, no pipes. Every computed value must be lifted into a JavaScript **getter**.

Angular: `{{ product.price | currency: product.currency }}`
LWC JS:  `get formattedPrice() { return new Intl.NumberFormat(undefined, { style: 'currency', currency: this.product.currency }).format(this.product.price); }`
LWC HTML: `{formattedPrice}`

Angular: `*ngIf="items.length > 0"` → JS getter `get hasItems() { return this.items.length > 0; }`,
markup `<template if:true={hasItems}>` (or `lwc:if={hasItems}`).

## Structural directives

`*ngFor="let item of items; trackBy: trackByCode"` becomes:
```html
<template for:each={items} for:item="item">
  <li key={item.code}>{item.name}</li>
</template>
```
`key` is mandatory and must be a stable unique value (the old `trackBy` return).
`*ngIf="c"` → `<template if:true={c}>`; the else branch → a second `<template if:false={c}>`.

## Event and attribute binding

`(click)="addToCart()"` → `onclick={addToCart}` (handler reference, not a call).
`[disabled]="isOut"` → `disabled={isOut}`. `[src]="url"` → `src={url}`.
`[class.active]="isActive"` → compute a class-string getter and bind `class={cardClass}`.
To read the input value in a handler, use `event.target.value` inside the JS method.

## Two-way binding

Angular `[(ngModel)]` has no LWC equivalent: bind `value={prop}` and handle `onchange`/`oninput`
to write the property back.
