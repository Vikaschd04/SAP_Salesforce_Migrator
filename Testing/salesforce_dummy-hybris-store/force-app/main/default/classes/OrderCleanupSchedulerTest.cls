@isTest
private class OrderCleanupSchedulerTest {
    @isTest
    static void testExecute() {
        List<Object> result = OrderCleanupScheduler.execute(new List<Object>());
        System.assertEquals(0, result.size(), 'mock stub returns input list');
    }
}