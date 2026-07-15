public with sharing class CustomerSelector {

    public List<Schema.SObjectField> getSObjectFieldList() {
        return new List<Schema.SObjectField>{
            Customer__c.Id,
            Customer__c.Name,
            Customer__c.Email__c,
            Customer__c.Name__c,
            Customer__c.Uid__c
        };
    }

    public Schema.SObjectType getSObjectType() {
        return Customer__c.SObjectType;
    }

    private String fieldCsv() {
        List<String> names = new List<String>();
        for (Schema.SObjectField f : getSObjectFieldList()) {
            names.add(f.getDescribe().getName());
        }
        return String.join(names, ', ');
    }

    public List<Customer__c> selectSObjectsById(Set<Id> ids) {
        if (ids == null || ids.isEmpty()) {
            return new List<Customer__c>();
        }
        String soql = 'SELECT ' + fieldCsv() + ' FROM Customer__c WHERE Id IN :ids';
        List<Customer__c> records = Database.query(soql);
        SObjectAccessDecision decision = Security.stripInaccessible(AccessType.READABLE, records);
        return (List<Customer__c>) decision.getRecords();
    }

    /** Maps CustomerDao.findByUid: retrieve customers by unique identifiers (bulk-safe). */
    public List<Customer__c> selectByUids(Set<String> uids) {
        if (uids == null || uids.isEmpty()) {
            System.debug('selectByUids called with empty uid set');
            return new List<Customer__c>();
        }
        String soql = 'SELECT ' + fieldCsv() + ' FROM Customer__c WHERE Uid__c IN :uids';
        List<Customer__c> records = Database.query(soql);
        SObjectAccessDecision decision = Security.stripInaccessible(AccessType.READABLE, records);
        return (List<Customer__c>) decision.getRecords();
    }

    /** Convenience single-uid lookup preserving CustomerDao.findByUid semantics. */
    public Customer__c selectByUid(String uid) {
        List<Customer__c> results = selectByUids(new Set<String>{ uid });
        return results.isEmpty() ? null : results[0];
    }

    /** Maps CustomerDao.findByEmailDomain: retrieve customers whose email matches the domain. */
    public List<Customer__c> selectByEmailDomain(String domain) {
        if (String.isBlank(domain)) {
            System.debug('selectByEmailDomain called with blank domain');
            return new List<Customer__c>();
        }
        String pattern = '%@' + domain;
        String soql = 'SELECT ' + fieldCsv() + ' FROM Customer__c WHERE Email__c LIKE :pattern';
        List<Customer__c> records = Database.query(soql);
        SObjectAccessDecision decision = Security.stripInaccessible(AccessType.READABLE, records);
        return (List<Customer__c>) decision.getRecords();
    }
}