@isTest
private class CustomerSelectorTest {
    @isTest
    static void testExecute() {
        List<Object> result = CustomerSelector.execute(new List<Object>());
        System.assertEquals(0, result.size(), 'mock stub returns input list');
    }
}