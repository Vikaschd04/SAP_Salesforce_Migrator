@isTest
private class OrderServiceTest {
    @isTest
    static void testExecute() {
        List<Object> result = OrderService.execute(new List<Object>());
        System.assertEquals(0, result.size(), 'mock stub returns input list');
    }
}