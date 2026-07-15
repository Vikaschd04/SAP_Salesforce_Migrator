# Hybris-to-Apex Mapping Report

## SObject Mapping

### Customer -> Customer__c

| Hybris Field | Java Type | Apex Field | Apex Type |
|---|---|---|---|
| uid | java.lang.String | uid__c | Text(255) |
| name | java.lang.String | name__c | Text(255) |
| email | java.lang.String | email__c | Text(255) |

### Product -> Product__c

| Hybris Field | Java Type | Apex Field | Apex Type |
|---|---|---|---|
| code | java.lang.String | code__c | Text(255) |
| name | java.lang.String | name__c | Text(255) |
| price | java.math.BigDecimal | price__c | Currency(16,2) |
| type | ProductType | type__c | Text(255) |
| stockLevel | java.lang.Integer | stockLevel__c | Number(9,0) |

### Order -> Order__c

| Hybris Field | Java Type | Apex Field | Apex Type |
|---|---|---|---|
| code | java.lang.String | code__c | Text(255) |
| totalAmount | java.math.BigDecimal | totalAmount__c | Currency(16,2) |
| status | OrderStatus | status__c | Text(255) |

## Layer Mapping

| Hybris Layer | Hybris Class | Apex Class | Apex Kind |
|---|---|---|---|
| DAO | CustomerDao | CustomerSelector | Selector |
| DAO | OrderDao | OrderSelector | Selector |
| Service | DefaultOrderService | OrderService | Service |
| Controller | OrderController | OrderController | RestResource |
| Job | OrderCleanupJob | OrderCleanupScheduler | Schedulable |
| Service | DefaultPromotionService | PromotionService | Service |

## Detailed Mapping Notes

### CustomerSelector

[mock] Deterministic stub output (provider=mock).

### OrderSelector

[mock] Deterministic stub output (provider=mock).

### OrderService

[mock] Deterministic stub output (provider=mock).

### OrderController

[mock] Deterministic stub output (provider=mock).

### OrderCleanupScheduler

[mock] Deterministic stub output (provider=mock).

### PromotionService

[mock] Deterministic stub output (provider=mock).

## Constraints Applied

- No SOQL or DML inside for/while loops.
- Every generated class has a matching @isTest class with at least one System.assert.
- Use 'with sharing' on Service/Controller classes.
- Bulk-safe: methods accept and return collections where the Hybris method processed one record.
- Translate Spring @Autowired dependency injections to constructor injection patterns in Apex.
- Translate SLF4J/Log4j logging (e.g. LOG.info(), LOG.error()) to System.debug().
- Translate Java/Spring exceptions to Custom exceptions extending Exception, or AuraHandledException in Controllers.
- Remove Java package statements and org.springframework.* imports.
