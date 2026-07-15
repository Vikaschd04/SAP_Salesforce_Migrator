@isTest
private class OrderControllerTest {

    @testSetup
    static void setup() {
        Customer__c cust = new Customer__c(
            Name__c = 'Test Customer',
            Uid__c = 'test-uid',
            Email__c = 'test@example.com'
        );
        insert cust;

        Order__c ord = new Order__c(
            Code__c = 'ORD-100',
            Status__c = 'CREATED',
            TotalAmount__c = 250.00,
            Customer__c = cust.Id
        );
        insert ord;
    }

    @isTest
    static void testGetOrderByParam() {
        RestRequest req = new RestRequest();
        req.requestURI = '/services/apexrest/order/ORD-100';
        req.httpMethod = 'GET';
        req.params.put('code', 'ORD-100');
        RestContext.request = req;
        RestContext.response = new RestResponse();

        Test.startTest();
        OrderController.OrderDTO dto = OrderController.getOrder();
        Test.stopTest();

        System.System.assertNotEquals(null, dto, 'DTO should not be null');
        System.System.assertEquals('ORD-100', dto.code, 'Code should match');
        System.System.assertEquals('CREATED', dto.status, 'Status should match');
        System.System.assertEquals(250.00, dto.totalAmount, 'Total should match');
    }

    @isTest
    static void testGetOrderByUri() {
        RestRequest req = new RestRequest();
        req.requestURI = '/services/apexrest/order/ORD-100';
        req.httpMethod = 'GET';
        RestContext.request = req;
        RestContext.response = new RestResponse();

        Test.startTest();
        OrderController.OrderDTO dto = OrderController.getOrder();
        Test.stopTest();

        System.System.assertNotEquals(null, dto, 'DTO should not be null');
        System.System.assertEquals('ORD-100', dto.code, 'Code should be parsed from URI');
    }

    @isTest
    static void testGetOrderNotFound() {
        RestRequest req = new RestRequest();
        req.requestURI = '/services/apexrest/order/DOES-NOT-EXIST';
        req.httpMethod = 'GET';
        req.params.put('code', 'DOES-NOT-EXIST');
        RestContext.request = req;
        RestContext.response = new RestResponse();

        Test.startTest();
        OrderController.OrderDTO dto = OrderController.getOrder();
        Test.stopTest();

        System.System.assertNotEquals(null, dto, 'Wrapper should still return');
        System.System.assertEquals(null, dto.code, 'No order should be resolved');
    }

    @isTest
    static void testGetOrderBlankCode() {
        RestRequest req = new RestRequest();
        req.requestURI = '/services/apexrest/order/';
        req.httpMethod = 'GET';
        RestContext.request = req;
        RestContext.response = new RestResponse();

        Test.startTest();
        OrderController.OrderDTO dto = OrderController.getOrder();
        Test.stopTest();

        System.System.assertNotEquals(null, dto, 'Wrapper should be returned for blank code');
        System.System.assertEquals(null, dto.code, 'Blank code resolves to null order');
    }
}