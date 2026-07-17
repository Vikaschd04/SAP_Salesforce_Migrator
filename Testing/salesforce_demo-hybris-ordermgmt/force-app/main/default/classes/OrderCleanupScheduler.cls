public with sharing class OrderCleanupScheduler implements Schedulable {
    private static final Integer STALE_AFTER_DAYS = 7;
    private static final String STATUS_CANCELLED = 'CANCELLED';

    // Represents the external 'should abort' signal that the original Java cron job honoured.
    @TestVisible private static Boolean abortRequested = false;

    public class OrderCleanupException extends Exception {}

    public void execute(SchedulableContext sc) {
        Datetime cutoff = daysAgo(STALE_AFTER_DAYS);
        List<Order__c> staleOrders = new OrderSelector().selectStaleUnpaidOrders(cutoff);

        List<Order__c> toCancel = new List<Order__c>();
        Integer cancelled = 0;
        Boolean aborted = false;

        for (Order__c order : staleOrders) {
            // Mirror the Java job which acknowledges/clears the abort flag before EACH cancellation
            // and then checks whether it must stop gracefully mid-run.
            clearJobShouldAbort();
            if (jobShouldAbort()) {
                aborted = true;
                break;
            }

            order.Status__c = STATUS_CANCELLED;
            toCancel.add(order);
            cancelled++;
        }

        // Persist only the orders processed before the abort was honoured.
        // Kept as a single bulk DML (outside the loop) to stay bulk-safe, while the
        // break above preserves the 'already-cancelled ones persist on abort' semantics.
        if (!toCancel.isEmpty()) {
            SObjectAccessDecision d = Security.stripInaccessible(AccessType.UPDATABLE, toCancel);
            update d.getRecords();
        }

        if (aborted) {
            System.debug('OrderCleanupScheduler ABORTED gracefully after cancelling ' + cancelled + ' stale unpaid orders');
        } else {
            System.debug('OrderCleanupScheduler cancelled ' + cancelled + ' stale unpaid orders');
        }
    }

    // Acknowledges the current abort-check cycle (equivalent to the Java clearJobShouldAbort()).
    private void clearJobShouldAbort() {
        System.debug('OrderCleanupScheduler checking abort signal for next cancellation');
    }

    // Returns whether the job has been requested to stop gracefully.
    private Boolean jobShouldAbort() {
        return abortRequested;
    }

    private Datetime daysAgo(Integer days) {
        return Datetime.now().addDays(-days);
    }
}