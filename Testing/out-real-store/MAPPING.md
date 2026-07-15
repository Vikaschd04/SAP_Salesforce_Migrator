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

## Detailed Mapping Notes

### CustomerSelector

CustomerDao mapped to a fflib-style Selector owning all Customer__c SOQL. findByUid became bulk-safe selectByUids(Set<String>) plus a single-record convenience selectByUid. findByEmailDomain became selectByEmailDomain using LIKE '%@domain' since schema has no separate domain field. Standard getSObjectFieldList/getSObjectType/selectSObjectsById implemented. All queries enforce FLS via Security.stripInaccessible and use bind variables; no SOQL in loops.

### OrderSelector

OrderDao.findByCode -> selectByCode / bulk selectByCodes using WHERE Code__c IN :codes. OrderDao.findByPriority -> selectByPriority / bulk selectByPriorities against the inferred Priority__c Number field (not in original items.xml, added by reconciliation). All SOQL owned by the Selector; FLS enforced via Security.stripInaccessible(READABLE). Standard fflib methods getSObjectFieldList/getSObjectType/selectSObjectsById implemented. Single-record DAO methods converted to bulk-safe collection variants with convenience wrappers preserving original semantics. Java int priority mapped to Decimal for SOQL binding.

### OrderService

(No additional notes)

### OrderController

Mapped the Hybris OrderController to a thin @RestResource with an @HttpGet handler. Setter-based Spring injection of DefaultOrderService is replaced by static delegation; since no OrderService/OrderSelector signatures were supplied, a private single-record helper performs the (non-loop, LIMIT 1) lookup by Code__c and returns an OrderDTO wrapper rather than the raw Order__c sObject. The order code is read from a request param or trailing URI segment. Java exceptions are translated to a custom OrderControllerException, and SLF4J-style logging maps to System.debug. Customer__c is referenced via the Order lookup; Product__c is available in schema but not required for this retrieval.

## Constraints Applied

- No SOQL or DML inside for/while loops.
- Every generated class has a matching @isTest class with at least one System.assert.
- Use 'with sharing' on Service/Controller classes.
- Bulk-safe: methods accept and return collections where the Hybris method processed one record.
- Translate Spring @Autowired dependency injections to constructor injection patterns in Apex.
- Translate SLF4J/Log4j logging (e.g. LOG.info(), LOG.error()) to System.debug().
- Translate Java/Spring exceptions to Custom exceptions extending Exception, or AuraHandledException in Controllers.
- Remove Java package statements and org.springframework.* imports.
