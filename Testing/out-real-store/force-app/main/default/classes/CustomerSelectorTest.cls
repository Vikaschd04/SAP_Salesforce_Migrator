@isTest
private class CustomerSelectorTest {

    @testSetup
    static void setup() {
        List<Customer__c> customers = new List<Customer__c>{
            new Customer__c(Name = 'Alice', Uid__c = 'alice1', Email__c = 'alice@example.com', Name__c = 'Alice'),
            new Customer__c(Name = 'Bob', Uid__c = 'bob1', Email__c = 'bob@example.com', Name__c = 'Bob'),
            new Customer__c(Name = 'Carol', Uid__c = 'carol1', Email__c = 'carol@other.com', Name__c = 'Carol')
        };
        insert customers;
    }

    @isTest
    static void testSelectByUid() {
        CustomerSelector sel = new CustomerSelector();
        Test.startTest();
        Customer__c c = sel.selectByUid('alice1');
        Test.stopTest();
        System.System.assertNotEquals(null, c, 'Should find customer by uid');
        System.System.assertEquals('alice1', c.Uid__c, 'Uid should match');
    }

    @isTest
    static void testSelectByUidsBulk() {
        CustomerSelector sel = new CustomerSelector();
        List<Customer__c> results = sel.selectByUids(new Set<String>{ 'alice1', 'bob1' });
        System.System.assertEquals(2, results.size(), 'Should find two customers by uids');
    }

    @isTest
    static void testSelectByEmailDomain() {
        CustomerSelector sel = new CustomerSelector();
        List<Customer__c> results = sel.selectByEmailDomain('example.com');
        System.System.assertEquals(2, results.size(), 'Should find two example.com customers');
    }

    @isTest
    static void testSelectSObjectsById() {
        Customer__c existing = [SELECT Id FROM Customer__c WHERE Uid__c = 'carol1' LIMIT 1];
        CustomerSelector sel = new CustomerSelector();
        List<Customer__c> results = sel.selectSObjectsById(new Set<Id>{ existing.Id });
        System.System.assertEquals(1, results.size(), 'Should return one record by Id');
    }

    @isTest
    static void testEmptyInputs() {
        CustomerSelector sel = new CustomerSelector();
        System.System.assertEquals(0, sel.selectByUids(new Set<String>()).size(), 'Empty uid set returns empty');
        System.System.assertEquals(0, sel.selectByEmailDomain('').size(), 'Blank domain returns empty');
        System.System.assertEquals(0, sel.selectSObjectsById(new Set<Id>()).size(), 'Empty id set returns empty');
    }
}