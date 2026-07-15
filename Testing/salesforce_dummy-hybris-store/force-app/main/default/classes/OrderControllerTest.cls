@isTest
private class OrderControllerTest {
    @isTest
    static void testExecute() {
        List<Object> result = OrderController.execute(new List<Object>());
        System.assertEquals(0, result.size(), 'mock stub returns input list');
    }
}