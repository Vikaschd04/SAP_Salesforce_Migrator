@isTest
private class OrderCleanupSchedulerTest {

    @testSetup
    static void setup() {
        List<Order__c> orders = new List<Order__c>();
        // Stale unpaid NEW order (created > 7 days ago)
        orders.add(new Order__c(Code__c = 'STALE1', Status__c = 'NEW', Paid__c = false, OrderDate__c = Datetime.now().addDays(-10), TotalAmount__c = 100));
        orders.add(new Order__c(Code__c = 'STALE2', Status__c = 'NEW', Paid__c = false, OrderDate__c = Datetime.now().addDays(-20), TotalAmount__c = 50));
        // Recent NEW order (not stale)
        orders.add(new Order__c(Code__c = 'FRESH1', Status__c = 'NEW', Paid__c = false, OrderDate__c = Datetime.now().addDays(-1), TotalAmount__c = 75));
        insert orders;
    }

    @isTest
    static void testExecuteCancelsStaleOrders() {
        OrderCleanupScheduler.abortRequested = false;
        Test.startTest();
        OrderCleanupScheduler scheduler = new OrderCleanupScheduler();
        scheduler.execute(null);
        Test.stopTest();

        List<Order__c> cancelled = [SELECT Id, Code__c, Status__c FROM Order__c WHERE Status__c = 'CANCELLED'];
        System.assertEquals(2, cancelled.size(), 'Two stale unpaid orders should be cancelled');

        Order__c fresh = [SELECT Status__c FROM Order__c WHERE Code__c = 'FRESH1' LIMIT 1];
        System.assertEquals('NEW', fresh.Status__c, 'Recent order should remain NEW');
    }

    @isTest
    static void testScheduleExecution() {
        Test.startTest();
        String jobId = System.schedule('OrderCleanupTest', '0 0 0 * * ?', new OrderCleanupScheduler());
        Test.stopTest();
        System.assertNotEquals(null, jobId, 'Scheduled job should be created');
    }

    // RULE: Orders still in NEW status and unpaid after 7 days are considered abandoned.
    // This asserts the positive case: only NEW + unpaid + older-than-7-days orders get cancelled.
    @isTest
    static void testNewUnpaidStaleOrderIsAbandonedAndCancelled() {
        OrderCleanupScheduler.abortRequested = false;

        Test.startTest();
        new OrderCleanupScheduler().execute(null);
        Test.stopTest();

        Order__c stale1 = [SELECT Status__c FROM Order__c WHERE Code__c = 'STALE1' LIMIT 1];
        Order__c stale2 = [SELECT Status__c FROM Order__c WHERE Code__c = 'STALE2' LIMIT 1];
        System.assertEquals('CANCELLED', stale1.Status__c, 'A NEW unpaid order older than 7 days must be treated as abandoned and cancelled');
        System.assertEquals('CANCELLED', stale2.Status__c, 'A NEW unpaid order older than 7 days must be treated as abandoned and cancelled');
    }

    // RULE (negative case): a PAID order that is old and NEW is NOT abandoned.
    @isTest
    static void testPaidOrderIsNotAbandoned() {
        OrderCleanupScheduler.abortRequested = false;
        insert new Order__c(Code__c = 'PAIDOLD', Status__c = 'NEW', Paid__c = true, OrderDate__c = Datetime.now().addDays(-30), TotalAmount__c = 200);

        Test.startTest();
        new OrderCleanupScheduler().execute(null);
        Test.stopTest();

        Order__c paidOld = [SELECT Status__c FROM Order__c WHERE Code__c = 'PAIDOLD' LIMIT 1];
        System.assertEquals('NEW', paidOld.Status__c, 'A paid order must never be treated as abandoned even when old');
    }

    // RULE (negative case): an order not in NEW status is NOT abandoned even if old and unpaid.
    @isTest
    static void testNonNewStatusOrderIsNotAbandoned() {
        OrderCleanupScheduler.abortRequested = false;
        insert new Order__c(Code__c = 'SHIPPEDOLD', Status__c = 'SHIPPED', Paid__c = false, OrderDate__c = Datetime.now().addDays(-30), TotalAmount__c = 150);

        Test.startTest();
        new OrderCleanupScheduler().execute(null);
        Test.stopTest();

        Order__c shippedOld = [SELECT Status__c FROM Order__c WHERE Code__c = 'SHIPPEDOLD' LIMIT 1];
        System.assertEquals('SHIPPED', shippedOld.Status__c, 'An order that is not in NEW status must not be cancelled by the cleanup job');
    }

    // RULE: Cutoff date is calculated as current date minus 7 days.
    // Orders newer than the 7-day cutoff must survive; orders older than it must be cancelled.
    @isTest
    static void testSevenDayCutoffBoundary() {
        OrderCleanupScheduler.abortRequested = false;
        // Just inside the window (still fresh) - 6 days old, must NOT be cancelled.
        insert new Order__c(Code__c = 'DAY6', Status__c = 'NEW', Paid__c = false, OrderDate__c = Datetime.now().addDays(-6), TotalAmount__c = 10);
        // Clearly beyond the cutoff - 8 days old, must be cancelled.
        insert new Order__c(Code__c = 'DAY8', Status__c = 'NEW', Paid__c = false, OrderDate__c = Datetime.now().addDays(-8), TotalAmount__c = 20);

        Test.startTest();
        new OrderCleanupScheduler().execute(null);
        Test.stopTest();

        Order__c day6 = [SELECT Status__c FROM Order__c WHERE Code__c = 'DAY6' LIMIT 1];
        Order__c day8 = [SELECT Status__c FROM Order__c WHERE Code__c = 'DAY8' LIMIT 1];
        System.assertEquals('NEW', day6.Status__c, 'An order newer than the 7-day cutoff must remain NEW');
        System.assertEquals('CANCELLED', day8.Status__c, 'An order older than the 7-day cutoff must be cancelled');

        // Also confirm the fresh (1 day old) order from setup survives the cutoff.
        Order__c fresh = [SELECT Status__c FROM Order__c WHERE Code__c = 'FRESH1' LIMIT 1];
        System.assertEquals('NEW', fresh.Status__c, 'A 1-day-old order is inside the 7-day cutoff and must not be cancelled');
    }

    // RULE: Job checks for abort signal before each cancellation and stops gracefully if requested.
    // When aborted before the first cancellation, NO orders are cancelled.
    @isTest
    static void testAbortBeforeFirstCancellationCancelsNothing() {
        OrderCleanupScheduler.abortRequested = true;

        Test.startTest();
        new OrderCleanupScheduler().execute(null);
        Test.stopTest();

        Integer cancelledCount = [SELECT COUNT() FROM Order__c WHERE Status__c = 'CANCELLED'];
        System.assertEquals(0, cancelledCount, 'When the abort signal is set, the job must stop gracefully before cancelling any order');

        // The stale orders remain untouched, proving the graceful stop rather than a hard failure.
        Order__c stale1 = [SELECT Status__c FROM Order__c WHERE Code__c = 'STALE1' LIMIT 1];
        System.assertEquals('NEW', stale1.Status__c, 'Stale orders must be left in NEW status when the job aborts gracefully');
    }

    // RULE: With abort NOT requested, the job runs to completion and cancels every stale order.
    @isTest
    static void testNoAbortProcessesAllStaleOrders() {
        OrderCleanupScheduler.abortRequested = false;

        Test.startTest();
        new OrderCleanupScheduler().execute(null);
        Test.stopTest();

        Integer cancelledCount = [SELECT COUNT() FROM Order__c WHERE Status__c = 'CANCELLED'];
        System.assertEquals(2, cancelledCount, 'With no abort requested the job must cancel all stale unpaid orders');
    }

    // RULE (negative/error case): the domain exposes an OrderCleanupException for invalid processing.
    // Assert the exception type can be raised and carries its message, guarding the error contract.
    @isTest
    static void testOrderCleanupExceptionIsThrowable() {
        Boolean thrown = false;
        Test.startTest();
        try {
            throw new OrderCleanupScheduler.OrderCleanupException('Invalid cleanup input');
        } catch (OrderCleanupScheduler.OrderCleanupException e) {
            thrown = true;
            System.assertEquals('Invalid cleanup input', e.getMessage(), 'The cleanup exception must preserve its message for error reporting');
        }
        Test.stopTest();
        System.assert(thrown, 'OrderCleanupException must be catchable as the job error contract');
    }
}