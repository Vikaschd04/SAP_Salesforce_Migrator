@RestResource(urlMapping='/order/*')
global with sharing class OrderController {

    /** DTO wrapper returned to callers instead of raw sObjects. */
    global class OrderDTO {
        global String code;
        global String status;
        global Decimal totalAmount;
        global String customerId;

        global OrderDTO() {}

        global OrderDTO(Order__c ord) {
            if (ord != null) {
                this.code = ord.Code__c;
                this.status = ord.Status__c;
                this.totalAmount = ord.TotalAmount__c;
                this.customerId = ord.Customer__c;
            }
        }
    }

    /**
     * GET /order/{code}
     * Retrieves a single order by its code. Delegates lookup and returns a DTO.
     */
    @HttpGet
    global static OrderDTO getOrder() {
        RestRequest req = RestContext.request;
        String code = null;
        if (req != null) {
            // Prefer query param, fall back to trailing URI segment.
            if (req.params != null && req.params.containsKey('code')) {
                code = req.params.get('code');
            } else if (String.isNotBlank(req.requestURI)) {
                Integer idx = req.requestURI.lastIndexOf('/');
                if (idx >= 0 && idx < req.requestURI.length() - 1) {
                    code = req.requestURI.substring(idx + 1);
                }
            }
        }
        try {
            Order__c ord = OrderController.findOrderByCode(code);
            System.debug('OrderController.getOrder resolved code=' + code);
            return new OrderDTO(ord);
        } catch (Exception e) {
            System.debug('OrderController.getOrder error: ' + e.getMessage());
            throw new OrderControllerException('Unable to retrieve order for code: ' + code, e);
        }
    }

    /** Bulk-safe single-record lookup helper (no SOQL inside loops). */
    private static Order__c findOrderByCode(String code) {
        if (String.isBlank(code)) {
            return null;
        }
        List<Order__c> orders = [
            SELECT Id, Code__c, Status__c, TotalAmount__c, Customer__c
            FROM Order__c
            WHERE Code__c = :code
            LIMIT 1
        ];
        // Enforce field-level security: strip fields the running user cannot read
        // before the values are ever surfaced through the DTO.
        SObjectAccessDecision decision = Security.stripInaccessible(AccessType.READABLE, orders);
        List<Order__c> accessibleOrders = (List<Order__c>) decision.getRecords();
        return accessibleOrders.isEmpty() ? null : accessibleOrders[0];
    }

    global class OrderControllerException extends Exception {}
}