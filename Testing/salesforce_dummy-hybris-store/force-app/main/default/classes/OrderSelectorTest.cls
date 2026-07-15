@isTest
private class OrderSelectorTest {
    @isTest
    static void testExecute() {
        List<Object> result = OrderSelector.execute(new List<Object>());
        System.assertEquals(0, result.size(), 'mock stub returns input list');
    }
}