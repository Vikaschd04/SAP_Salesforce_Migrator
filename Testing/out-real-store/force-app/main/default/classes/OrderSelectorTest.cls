@isTest
private class OrderSelectorTest {

    @testSetup
    static void setup() {
        Customer__c cust = new Customer__c(
            Name__c = 'Acme',
            Uid__c = 'acme@store.com',
            Email__c = 'acme@store.com'
        );
        insert cust;

        List<Order__c> orders = new List<Order__c>{
            new Order__c(Code__c = 'ORD-1', Customer__c = cust.Id, Status__c = 'CREATED', TotalAmount__c = 100, Priority__c = 5),
            new Order__c(Code__c = 'ORD-2', Customer__c = cust.Id, Status__c = 'CREATED', TotalAmount__c = 200, Priority__c = 5),
            new Order__c(Code__c = 'ORD-3', Customer__c = cust.Id, Status__c = 'SHIPPED', TotalAmount__c = 300, Priority__c = 1)
        };
        insert orders;
    }

    @isTest
    static void testSelectByCode() {
        OrderSelector sel = new OrderSelector();
        Test.startTest();
        Order__c result = sel.selectByCode('ORD-1');
        Test.stopTest();
        System.System.assertNotEquals(null, result, 'Order with code ORD-1 should be found');
        System.System.assertEquals('ORD-1', result.Code__c, 'Returned order code should match');
    }

    @isTest
    static void testSelectByCodesBulk() {
        OrderSelector sel = new OrderSelector();
        List<Order__c> results = sel.selectByCodes(new Set<String>{ 'ORD-1', 'ORD-2' });
        System.System.assertEquals(2, results.size(), 'Two orders should match the given codes');
    }

    @isTest
    static void testSelectByPriority() {
        OrderSelector sel = new OrderSelector();
        Test.startTest();
        List<Order__c> results = sel.selectByPriority(5);
        Test.stopTest();
        System.System.assertEquals(2, results.size(), 'Two orders should have priority 5');
    }

    @isTest
    static void testSelectByPrioritiesBulk() {
        OrderSelector sel = new OrderSelector();
        List<Order__c> results = sel.selectByPriorities(new Set<Integer>{ 5, 1 });
        System.System.assertEquals(3, results.size(), 'All three orders should match priorities 5 and 1');
    }

    @isTest
    static void testSelectSObjectsById() {
        List<Order__c> all = [SELECT Id FROM Order__c];
        Set<Id> ids = new Set<Id>();
        for (Order__c o : all) {
            ids.add(o.Id);
        }
        OrderSelector sel = new OrderSelector();
        List<Order__c> results = sel.selectSObjectsById(ids);
        System.System.assertEquals(all.size(), results.size(), 'All orders should be returned by Id');
    }

    @isTest
    static void testEmptyInputs() {
        OrderSelector sel = new OrderSelector();
        System.System.assertEquals(0, sel.selectByCodes(new Set<String>()).size(), 'Empty codes returns empty list');
        System.System.assertEquals(0, sel.selectSObjectsById(new Set<Id>()).size(), 'Empty ids returns empty list');
        System.System.assertEquals(null, sel.selectByCode(''), 'Blank code returns null');
        System.System.assertEquals(false, sel.getSObjectFieldList().isEmpty(), 'Field list should not be empty');
        System.System.assertEquals(Order__c.SObjectType, sel.getSObjectType(), 'SObjectType should be Order__c');
    }

    /**
     * Rule: 'priority' was not declared in items.xml, so reconciliation should have added
     * an inferred Priority__c field. Assert the field exists on Order__c and is exposed by
     * the selector's field list.
     */
    @isTest
    static void testInferredPriorityFieldIsDeclaredOnSchema() {
        Map<String, Schema.SObjectField> fieldMap = Order__c.SObjectType.getDescribe().fields.getMap();
        System.System.assertEquals(true, fieldMap.containsKey('priority__c'), 'Inferred Priority__c field should exist on Order__c');

        OrderSelector sel = new OrderSelector();
        Boolean priorityInSelector = false;
        for (Schema.SObjectField f : sel.getSObjectFieldList()) {
            if (f.getDescribe().getName() == 'Priority__c') {
                priorityInSelector = true;
            }
        }
        System.System.assertEquals(true, priorityInSelector, 'Selector field list should include the inferred Priority__c field');
    }

    /**
     * Rule: the inferred Priority__c field must be reconciled as a Number type.
     */
    @isTest
    static void testInferredPriorityFieldIsNumberType() {
        Schema.DescribeFieldResult dfr = Order__c.Priority__c.getDescribe();
        System.System.assertEquals(
            Schema.DisplayType.DOUBLE,
            dfr.getType(),
            'Inferred Priority__c field should be reconciled as a Number (Double) type'
        );
    }

    /**
     * Rule: because Priority__c is an inferred Number field, it must round-trip numeric values
     * through persistence and be filterable/queryable by the selector.
     */
    @isTest
    static void testInferredPriorityFieldStoresAndQueriesNumericValue() {
        OrderSelector sel = new OrderSelector();
        Test.startTest();
        List<Order__c> highPriority = sel.selectByPriority(1);
        Test.stopTest();
        System.System.assertEquals(1, highPriority.size(), 'Exactly one order should have inferred priority 1');
        System.System.assertEquals(1, highPriority[0].Priority__c, 'The stored Priority__c numeric value should be preserved');
        System.System.assertEquals('ORD-3', highPriority[0].Code__c, 'The priority-1 order should be ORD-3');
    }

    /**
     * Negative case: a null priority is not a valid numeric input, so the selector must reject it
     * by returning an empty result rather than querying with a bad value.
     */
    @isTest
    static void testInferredPriorityRejectsNullInput() {
        OrderSelector sel = new OrderSelector();
        Integer badInput = null;
        List<Order__c> results = sel.selectByPriority(badInput);
        System.System.assertEquals(0, results.size(), 'Null priority input should be rejected and return an empty list');

        List<Order__c> resultsSet = sel.selectByPriorities(new Set<Integer>{ (Integer) null });
        System.System.assertEquals(0, resultsSet.size(), 'A set containing only null priorities should be rejected and return an empty list');
    }
}