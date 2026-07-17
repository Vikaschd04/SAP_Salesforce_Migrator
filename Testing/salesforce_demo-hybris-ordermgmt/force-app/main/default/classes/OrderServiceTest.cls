@isTest
private class OrderServiceTest {

    @testSetup
    static void setupData() {
        Customer__c customer = new Customer__c(
            Name__c = 'Test Customer',
            Email__c = 'test@example.com',
            LoyaltyTier__c = 'Gold',
            Phone__c = '5551234567',
            Uid__c = 'CUST-001'
        );
        insert customer;

        Product__c product = new Product__c(
            Name__c = 'Test Product',
            Code__c = 'PROD-001',
            Price__c = 25.00,
            ProductType__c = 'Standard',
            StockLevel__c = 100,
            Active__c = true
        );
        insert product;

        Order__c order = new Order__c(
            Code__c = 'ORD-001',
            Customer__c = customer.Id,
            OrderDate__c = System.now(),
            Paid__c = false,
            Status__c = 'New',
            TotalAmount__c = 50.00
        );
        insert order;

        OrderEntry__c entry = new OrderEntry__c(
            EntryNumber__c = 1,
            Order__c = order.Id,
            Product__c = product.Id,
            Quantity__c = 2,
            UnitPrice__c = 25.00
        );
        insert entry;
    }

    @isTest
    static void testOrderCreation() {
        Test.startTest();
        List<Order__c> orders = [SELECT Id, Code__c, TotalAmount__c, Status__c FROM Order__c WHERE Code__c = 'ORD-001'];
        Test.stopTest();

        System.assertEquals(1, orders.size(), 'Exactly one order should exist.');
        System.assertEquals('ORD-001', orders[0].Code__c, 'Order code should match the inserted value.');
        System.assertEquals(50.00, orders[0].TotalAmount__c, 'Total amount should match the inserted value.');
    }

    @isTest
    static void testOrderEntries() {
        Order__c order = [SELECT Id FROM Order__c WHERE Code__c = 'ORD-001' LIMIT 1];

        Test.startTest();
        List<OrderEntry__c> entries = [SELECT Id, Quantity__c, UnitPrice__c FROM OrderEntry__c WHERE Order__c = :order.Id];
        Test.stopTest();

        System.assertEquals(1, entries.size(), 'Exactly one order entry should exist.');
        System.assertEquals(2, entries[0].Quantity__c, 'Quantity should match the inserted value.');
        System.assert(entries[0].UnitPrice__c == 25.00, 'Unit price should match the inserted value.');
    }

    @isTest
    static void testCustomerAndProduct() {
        Test.startTest();
        List<Customer__c> customers = [SELECT Id, Name__c, LoyaltyTier__c FROM Customer__c WHERE Uid__c = 'CUST-001'];
        List<Product__c> products = [SELECT Id, Code__c, Active__c FROM Product__c WHERE Code__c = 'PROD-001'];
        Test.stopTest();

        System.assertEquals(1, customers.size(), 'Exactly one customer should exist.');
        System.assertEquals('Gold', customers[0].LoyaltyTier__c, 'Loyalty tier should match.');
        System.assertEquals(1, products.size(), 'Exactly one product should exist.');
        System.assert(products[0].Active__c, 'Product should be active.');
    }
}