# Hybris-to-Apex Mapping Report

## SObject Mapping

### Customer -> Customer__c

| Hybris Field | Java Type | Apex Field | Apex Type |
|---|---|---|---|
| uid | java.lang.String | uid__c | Text(255) |
| name | java.lang.String | name__c | Text(255) |
| email | java.lang.String | email__c | Text(255) |
| phone | java.lang.String | phone__c | Text(255) |
| loyaltyTier | LoyaltyTier | loyaltyTier__c | Text(255) |

### Product -> Product__c

| Hybris Field | Java Type | Apex Field | Apex Type |
|---|---|---|---|
| code | java.lang.String | code__c | Text(255) |
| name | java.lang.String | name__c | Text(255) |
| price | java.math.BigDecimal | price__c | Currency(16,2) |
| stockLevel | java.lang.Integer | stockLevel__c | Number(9,0) |
| productType | ProductType | productType__c | Text(255) |
| active | java.lang.Boolean | active__c | Checkbox |

### Order -> Order__c

| Hybris Field | Java Type | Apex Field | Apex Type |
|---|---|---|---|
| code | java.lang.String | code__c | Text(255) |
| totalAmount | java.math.BigDecimal | totalAmount__c | Currency(16,2) |
| status | OrderStatus | status__c | Text(255) |
| orderDate | java.util.Date | orderDate__c | DateTime |
| paid | java.lang.Boolean | paid__c | Checkbox |

### OrderEntry -> OrderEntry__c

| Hybris Field | Java Type | Apex Field | Apex Type |
|---|---|---|---|
| entryNumber | java.lang.Integer | entryNumber__c | Number(9,0) |
| quantity | java.lang.Integer | quantity__c | Number(9,0) |
| unitPrice | java.math.BigDecimal | unitPrice__c | Currency(16,2) |

## Layer Mapping

| Hybris Layer | Hybris Class | Apex Class | Apex Kind |
|---|---|---|---|
| DAO | OrderDao | OrderSelector | Selector |
| Service | DefaultOrderService | OrderService | Service |
| Controller | OrderController | OrderController | RestResource |
| Job | OrderCleanupJob | OrderCleanupScheduler | Schedulable |

## Detailed Mapping Notes

### OrderSelector

OrderDao maps to OrderSelector owning all SOQL for Order__c. findByCode -> selectByCode/selectByCodes (bulk-safe, returns first or null). findByStatus -> selectByStatuses ordered by OrderDate__c DESC. findStaleUnpaidOrders -> selectStaleUnpaidOrders with Paid__c=false, Status__c='NEW', OrderDate__c<cutoff (Date->Datetime per type mapping). All inputs use bind variables; FLS enforced via Security.stripInaccessible on returns. findByMinimumPriority was OMITTED: the target schema has no priority field on Order__c, and the rules forbid querying fields not in the provided schema. OrderStatus enum modeled as picklist String values.

### OrderService

(No additional notes)

### OrderController

Controller exposed as @RestResource urlMapping '/orders/*'; @HttpGet handles both /orders/{code} (returns OrderSummary DTO) and /orders/status/{status} (serializes List<OrderSummary> into the response body since Apex REST can only have one @HttpGet). @HttpPost handles /orders/{code}/cancel, setting statusCode 204. Since no OrderService was provided (leaf class), selector-style SOQL helpers were kept private and bulk-safe (WHERE ... IN :codes), with no SOQL/DML in loops. OrderStatus.valueOf(status.toUpperCase()) mapped to status.toUpperCase() picklist match. Null-safe status mapping preserved. isExpedited was not defined upstream; implemented as paid && totalAmount>=500 (documented assumption). Cancellation restricted to non-SHIPPED orders per Javadoc. OrderSummary is a DTO wrapper so sObjects are never returned directly.

### OrderCleanupScheduler

perform(CronJobModel) body moved into execute(SchedulableContext). SOQL delegated to existing OrderSelector.selectStaleUnpaidOrders(cutoff); no inline SOQL. Cutoff computed as now-7 days (Datetime maps java.util.Date). Order status set to CANCELLED and DML consolidated into a single bulk update outside the loop. Hybris clearJobShouldAbort() abort-signal logic has no Schedulable equivalent, so cancellation proceeds for all matched records while preserving the core cancel-stale-unpaid business rule. SLF4J/Log4j logging replaced with System.debug. FLS enforced via Security.stripInaccessible(UPDATABLE).

## Constraints Applied

- No SOQL or DML inside for/while loops.
- Every generated class has a matching @isTest class with at least one System.assert.
- Use 'with sharing' on Service/Controller classes.
- Bulk-safe: methods accept and return collections where the Hybris method processed one record.
- Translate Spring @Autowired dependency injections to constructor injection patterns in Apex.
- Translate SLF4J/Log4j logging (e.g. LOG.info(), LOG.error()) to System.debug().
- Translate Java/Spring exceptions to Custom exceptions extending Exception, or AuraHandledException in Controllers.
- Remove Java package statements and org.springframework.* imports.
