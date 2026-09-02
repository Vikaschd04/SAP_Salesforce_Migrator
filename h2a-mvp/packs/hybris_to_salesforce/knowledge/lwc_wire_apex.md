# LWC data access: @wire and imperative Apex

Angular services that fetch data over REST (HttpClient) become **Apex** on Salesforce. The LWC
calls that Apex, never a raw REST endpoint to its own org.

## The Apex controller

Expose read methods as `@AuraEnabled(cacheable=true)` on a `with sharing` class. `cacheable=true`
is required for `@wire` and enables client caching; use it for pure reads (no DML).

```apex
public with sharing class ProductController {
    @AuraEnabled(cacheable=true)
    public static List<Product__c> getProducts() {
        return [SELECT Id, Code__c, Name__c, Price__c, StockLevel__c
                FROM Product__c WHERE Active__c = true WITH USER_MODE];
    }
    @AuraEnabled(cacheable=true)
    public static Product__c getProduct(String code) {
        return [SELECT Id, Code__c, Name__c, Price__c, StockLevel__c
                FROM Product__c WHERE Code__c = :code WITH USER_MODE LIMIT 1];
    }
}
```
Writes (add to cart, place order) are `@AuraEnabled` **without** `cacheable`, called imperatively.

## @wire (declarative reads)

```js
import { LightningElement, wire } from 'lwc';
import getProducts from '@salesforce/apex/ProductController.getProducts';

export default class ProductList extends LightningElement {
    @wire(getProducts) products;   // products.data / products.error
}
```
Reactive parameters use `$prop`: `@wire(getProduct, { code: '$productCode' }) product;`.

## Imperative Apex (writes / on-demand)

```js
import placeOrder from '@salesforce/apex/OrderController.placeOrder';
async handleCheckout() {
    try {
        await placeOrder({ items: this.items });
    } catch (e) {
        this.error = e.body ? e.body.message : 'Unknown error';
    }
}
```

## Rules

- One `@AuraEnabled` method per logical operation; keep controllers thin — delegate to the migrated
  Service/Selector Apex.
- Always query `WITH USER_MODE` (or enforce FLS) in `@AuraEnabled` methods.
- Never put SOQL/DML in a loop; bulkify.
