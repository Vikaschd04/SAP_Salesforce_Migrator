public with sharing class OrderSelector
{
    /**
     * Custom exception used when a requested business rule cannot be satisfied
     * by the current Order__c schema (e.g. missing Priority__c field).
     */
    public class OrderSelectorException extends Exception {}

    /**
     * Fields selected for Order__c queries.
     */
    public List<Schema.SObjectField> getSObjectFieldList()
    {
        return new List<Schema.SObjectField>{
            Order__c.Id,
            Order__c.Code__c,
            Order__c.Customer__c,
            Order__c.OrderDate__c,
            Order__c.Paid__c,
            Order__c.Status__c,
            Order__c.TotalAmount__c
        };
    }

    public Schema.SObjectType getSObjectType()
    {
        return Order__c.SObjectType;
    }

    /**
     * Bulk select by Id.
     */
    public List<Order__c> selectSObjectsById(Set<Id> ids)
    {
        List<Order__c> records = [
            SELECT Id, Code__c, Customer__c, OrderDate__c, Paid__c, Status__c, TotalAmount__c
            FROM Order__c
            WHERE Id IN :ids
        ];
        SObjectAccessDecision decision = Security.stripInaccessible(AccessType.READABLE, records);
        return (List<Order__c>) decision.getRecords();
    }

    /**
     * findByCode: returns the single order owning the given business code, or null when none.
     * Bulk-safe variant accepts a set of codes and returns matching orders.
     */
    public List<Order__c> selectByCodes(Set<String> codes)
    {
        System.debug('OrderSelector.selectByCodes codes=' + codes);
        List<Order__c> records = [
            SELECT Id, Code__c, Customer__c, OrderDate__c, Paid__c, Status__c, TotalAmount__c
            FROM Order__c
            WHERE Code__c IN :codes
        ];
        SObjectAccessDecision decision = Security.stripInaccessible(AccessType.READABLE, records);
        return (List<Order__c>) decision.getRecords();
    }

    /**
     * findByCode single-code convenience: returns the first match or null.
     */
    public Order__c selectByCode(String code)
    {
        List<Order__c> orders = selectByCodes(new Set<String>{ code });
        return orders.isEmpty() ? null : orders.get(0);
    }

    /**
     * findByStatus: every order in a given status, newest first (OrderDate__c descending).
     */
    public List<Order__c> selectByStatuses(Set<String> statuses)
    {
        System.debug('OrderSelector.selectByStatuses statuses=' + statuses);
        List<Order__c> records = [
            SELECT Id, Code__c, Customer__c, OrderDate__c, Paid__c, Status__c, TotalAmount__c
            FROM Order__c
            WHERE Status__c IN :statuses
            ORDER BY OrderDate__c DESC
        ];
        SObjectAccessDecision decision = Security.stripInaccessible(AccessType.READABLE, records);
        return (List<Order__c>) decision.getRecords();
    }

    /**
     * findStaleUnpaidOrders: unpaid (Paid__c=false), status NEW, placed strictly before cutoff.
     * Used by nightly cleanup to cancel abandoned orders.
     */
    public List<Order__c> selectStaleUnpaidOrders(Datetime cutoff)
    {
        System.debug('OrderSelector.selectStaleUnpaidOrders cutoff=' + cutoff);
        Boolean paidFlag = false;
        String newStatus = 'NEW';
        List<Order__c> records = [
            SELECT Id, Code__c, Customer__c, OrderDate__c, Paid__c, Status__c, TotalAmount__c
            FROM Order__c
            WHERE Paid__c = :paidFlag
              AND Status__c = :newStatus
              AND OrderDate__c < :cutoff
        ];
        SObjectAccessDecision decision = Security.stripInaccessible(AccessType.READABLE, records);
        return (List<Order__c>) decision.getRecords();
    }

    /**
     * findByMinimumPriority: original Hybris DAO returned every order whose priority was
     * at or above an inclusive lower bound, ordered by priority DESC (highest ships first).
     *
     * SCHEMA GAP: the Order__c object exposes no Priority__c field, so this business rule
     * cannot be satisfied against the current data model. Rather than silently dropping the
     * lookup (which would hide the missing-field problem), the method is preserved and fails
     * fast with a descriptive custom exception. Once a Priority__c field is added to Order__c,
     * the query below can be reinstated to restore the original behaviour.
     *
     * @param minPriority inclusive lower bound on order priority.
     * @return orders at or above minPriority, ordered by priority descending.
     */
    public List<Order__c> selectByMinimumPriority(Decimal minPriority)
    {
        System.debug('OrderSelector.selectByMinimumPriority minPriority=' + minPriority);
        throw new OrderSelectorException(
            'findByMinimumPriority is unsupported: Order__c has no Priority__c field. ' +
            'Add a Priority__c field to Order__c to restore filtering with an inclusive ' +
            'lower bound (minPriority=' + minPriority + ') ordered by priority descending.'
        );
    }
}