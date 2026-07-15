public with sharing class OrderSelector {

    /** Returns the list of fields this Selector queries. */
    public List<Schema.SObjectField> getSObjectFieldList() {
        return new List<Schema.SObjectField>{
            Order__c.Id,
            Order__c.Name,
            Order__c.Code__c,
            Order__c.Customer__c,
            Order__c.Status__c,
            Order__c.TotalAmount__c,
            Order__c.Priority__c
        };
    }

    public Schema.SObjectType getSObjectType() {
        return Order__c.SObjectType;
    }

    private String buildFieldListCsv() {
        List<String> names = new List<String>();
        for (Schema.SObjectField f : getSObjectFieldList()) {
            names.add(f.getDescribe().getName());
        }
        return String.join(names, ', ');
    }

    /** Bulk select by Id. Mirrors generic FlexibleSearch by primary key. */
    public List<Order__c> selectSObjectsById(Set<Id> ids) {
        if (ids == null || ids.isEmpty()) {
            return new List<Order__c>();
        }
        List<Order__c> records = [
            SELECT Id, Name, Code__c, Customer__c, Status__c, TotalAmount__c, Priority__c
            FROM Order__c
            WHERE Id IN :ids
        ];
        SObjectAccessDecision decision = Security.stripInaccessible(AccessType.READABLE, records);
        return (List<Order__c>) decision.getRecords();
    }

    /**
     * Translates OrderDao.findByCode(String code).
     * Bulk-safe: accepts a Set of codes and returns matching orders.
     */
    public List<Order__c> selectByCodes(Set<String> codes) {
        if (codes == null || codes.isEmpty()) {
            return new List<Order__c>();
        }
        List<Order__c> records = [
            SELECT Id, Name, Code__c, Customer__c, Status__c, TotalAmount__c, Priority__c
            FROM Order__c
            WHERE Code__c IN :codes
        ];
        SObjectAccessDecision decision = Security.stripInaccessible(AccessType.READABLE, records);
        return (List<Order__c>) decision.getRecords();
    }

    /** Convenience single-code wrapper preserving original findByCode semantics. */
    public Order__c selectByCode(String code) {
        if (String.isBlank(code)) {
            return null;
        }
        List<Order__c> results = selectByCodes(new Set<String>{ code });
        return results.isEmpty() ? null : results[0];
    }

    /**
     * Translates OrderDao.findByPriority(int priority).
     * Bulk-safe: accepts a Set of priorities and returns matching orders
     * ordered by priority so they can be ranked/filtered.
     */
    public List<Order__c> selectByPriorities(Set<Integer> priorities) {
        if (priorities == null || priorities.isEmpty()) {
            return new List<Order__c>();
        }
        List<Decimal> priorityValues = new List<Decimal>();
        for (Integer p : priorities) {
            if (p != null) {
                priorityValues.add((Decimal) p);
            }
        }
        if (priorityValues.isEmpty()) {
            return new List<Order__c>();
        }
        List<Order__c> records = [
            SELECT Id, Name, Code__c, Customer__c, Status__c, TotalAmount__c, Priority__c
            FROM Order__c
            WHERE Priority__c IN :priorityValues
            ORDER BY Priority__c ASC
        ];
        SObjectAccessDecision decision = Security.stripInaccessible(AccessType.READABLE, records);
        return (List<Order__c>) decision.getRecords();
    }

    /** Convenience single-priority wrapper preserving original findByPriority semantics. */
    public List<Order__c> selectByPriority(Integer priority) {
        if (priority == null) {
            return new List<Order__c>();
        }
        return selectByPriorities(new Set<Integer>{ priority });
    }
}