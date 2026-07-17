@isTest
private class OrderSelectorTest
{
    @testSetup
    static void setup()
    {
        Datetime now = Datetime.now();
        List<Order__c> orders = new List<Order__c>{
            new Order__c(Code__c = 'ORD-1001', Status__c = 'NEW', Paid__c = false, TotalAmount__c = 100, OrderDate__c = now.addDays(-10)),
            new Order__c(Code__c = 'ORD-1002', Status__c = 'NEW', Paid__c = false, TotalAmount__c = 200, OrderDate__c = now.addDays(-2)),
            new Order__c(Code__c = 'ORD-1003', Status__c = 'NEW', Paid__c = true,  TotalAmount__c = 300, OrderDate__c = now.addDays(-10)),
            new Order__c(Code__c = 'ORD-1004', Status__c = 'SHIPPED', Paid__c = true, TotalAmount__c = 400, OrderDate__c = now.addDays(-1))
        };
        insert orders;
    }

    @isTest
    static void testSelectByCode()
    {
        OrderSelector sel = new OrderSelector();
        Order__c o = sel.selectByCode('ORD-1001');
        System.assertNotEquals(null, o, 'Expected an order for ORD-1001');
        System.assertEquals('ORD-1001', o.Code__c, 'Wrong order returned');

        Order__c missing = sel.selectByCode('DOES-NOT-EXIST');
        System.assertEquals(null, missing, 'Expected null for unknown code');
    }

    @isTest
    static void testSelectByStatuses()
    {
        OrderSelector sel = new OrderSelector();
        List<Order__c> results = sel.selectByStatuses(new Set<String>{ 'NEW' });
        System.assertEquals(3, results.size(), 'Expected 3 NEW orders');
        // Newest first: OrderDate descending
        System.assert(results[0].OrderDate__c >= results[1].OrderDate__c, 'Results not ordered newest first');
    }

    @isTest
    static void testSelectStaleUnpaidOrders()
    {
        OrderSelector sel = new OrderSelector();
        Datetime cutoff = Datetime.now().addDays(-5);
        List<Order__c> stale = sel.selectStaleUnpaidOrders(cutoff);
        System.assertEquals(1, stale.size(), 'Expected only ORD-1001 to be stale unpaid NEW before cutoff');
        System.assertEquals('ORD-1001', stale[0].Code__c, 'Wrong stale order returned');
    }

    @isTest
    static void testSelectSObjectsByIdAndFieldList()
    {
        OrderSelector sel = new OrderSelector();
        Set<Id> ids = new Map<Id, Order__c>([SELECT Id FROM Order__c]).keySet();
        List<Order__c> records = sel.selectSObjectsById(ids);
        System.assertEquals(4, records.size(), 'Expected all 4 orders by id');
        System.assert(!sel.getSObjectFieldList().isEmpty(), 'Field list should not be empty');
        System.assertEquals(Order__c.SObjectType, sel.getSObjectType(), 'Wrong SObjectType');
    }

    /**
     * Rule: findByCode returns null when no match, else the FIRST result.
     * Asserts both the positive (first result returned) and negative (null) branches
     * explicitly, including the case where multiple codes are requested.
     */
    @isTest
    static void testSelectByCodeReturnsFirstMatchOrNull()
    {
        OrderSelector sel = new OrderSelector();

        Test.startTest();
        // Positive: an existing code yields a non-null record whose Code__c matches.
        Order__c first = sel.selectByCode('ORD-1002');
        // Negative: an unknown code yields null (no match).
        Order__c noMatch = sel.selectByCode('UNKNOWN-CODE');
        // Bulk variant: matching codes returned, non-matching silently absent.
        List<Order__c> bulk = sel.selectByCodes(new Set<String>{ 'ORD-1001', 'ORD-9999' });
        Test.stopTest();

        System.assertNotEquals(null, first, 'findByCode should return a record for an existing code');
        System.assertEquals('ORD-1002', first.Code__c, 'findByCode should return the record owning the requested code');

        System.assertEquals(null, noMatch, 'findByCode must return null when no order matches the code');

        System.assertEquals(1, bulk.size(), 'Only the single existing code should match in the bulk variant');
        System.assertEquals('ORD-1001', bulk[0].Code__c, 'Bulk variant returned the wrong record');
    }

    /**
     * Rule: findByMinimumPriority is an inclusive lower bound, higher priority ships first,
     * ordered priority descending. The current Order__c schema has NO Priority__c field, so
     * the business rule cannot be satisfied and the method must fail fast with a descriptive
     * OrderSelector.OrderSelectorException rather than silently returning data.
     */
    @isTest
    static void testSelectByMinimumPriorityThrowsUntilSchemaSupportsIt()
    {
        OrderSelector sel = new OrderSelector();
        Boolean threw = false;
        String message = null;

        Test.startTest();
        try
        {
            sel.selectByMinimumPriority(5);
            System.assert(false, 'Expected OrderSelectorException because Order__c has no Priority__c field');
        }
        catch (OrderSelector.OrderSelectorException e)
        {
            threw = true;
            message = e.getMessage();
        }
        Test.stopTest();

        System.assert(threw, 'findByMinimumPriority must throw OrderSelectorException while the schema gap exists');
        System.assertNotEquals(null, message, 'Exception should carry a descriptive message');
        System.assert(message.contains('Priority__c'), 'Message should explain the missing Priority__c field');
        System.assert(message.contains('findByMinimumPriority'), 'Message should name the unsupported operation');
    }

    /**
     * Rule: all inputs are bound as query parameters, never string-concatenated, so the read
     * layer is SQL-injection safe. A malicious payload passed as a code must be treated as a
     * literal value: it simply matches nothing and cannot alter the query, returning null/empty
     * without error and without leaking other records.
     */
    @isTest
    static void testInputsAreBoundNotConcatenatedInjectionSafe()
    {
        OrderSelector sel = new OrderSelector();
        String injection = '\' OR Code__c != null OR Code__c = \'';

        Test.startTest();
        Order__c singleResult = sel.selectByCode(injection);
        List<Order__c> bulkResult = sel.selectByCodes(new Set<String>{ injection });
        // A status-based injection attempt is likewise treated as a literal picklist value.
        List<Order__c> statusResult = sel.selectByStatuses(new Set<String>{ 'NEW\' OR 1=1 OR \'' });
        Test.stopTest();

        System.assertEquals(null, singleResult, 'Injection payload must be bound as a literal and match no records');
        System.assertEquals(0, bulkResult.size(), 'Bound bulk code query must not leak records for an injection payload');
        System.assertEquals(0, statusResult.size(), 'Bound status query must not leak records for an injection payload');
    }

    /**
     * Rule: this is a pure read layer with no business logic. selectByCodes returns exactly the
     * matching rows, unmodified and unfiltered by any hidden logic, with values straight from
     * the persisted records.
     */
    @isTest
    static void testReadLayerReturnsRawDataNoBusinessLogic()
    {
        OrderSelector sel = new OrderSelector();

        Test.startTest();
        List<Order__c> results = sel.selectByCodes(new Set<String>{ 'ORD-1003', 'ORD-1004' });
        Test.stopTest();

        System.assertEquals(2, results.size(), 'Read layer should return exactly the matching records');
        Map<String, Order__c> byCode = new Map<String, Order__c>();
        for (Order__c o : results)
        {
            byCode.put(o.Code__c, o);
        }
        System.assert(byCode.containsKey('ORD-1003'), 'Expected ORD-1003 in results');
        System.assert(byCode.containsKey('ORD-1004'), 'Expected ORD-1004 in results');
        // Values are returned untouched by any business logic.
        System.assertEquals(300, byCode.get('ORD-1003').TotalAmount__c, 'TotalAmount should be returned unmodified');
        System.assertEquals(true, byCode.get('ORD-1003').Paid__c, 'Paid flag should be returned unmodified');
        System.assertEquals('SHIPPED', byCode.get('ORD-1004').Status__c, 'Status should be returned unmodified');
    }
}