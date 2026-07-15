@isTest
private class PromotionServiceTest {
    @isTest
    static void testExecute() {
        List<Object> result = PromotionService.execute(new List<Object>());
        System.assertEquals(0, result.size(), 'mock stub returns input list');
    }
}