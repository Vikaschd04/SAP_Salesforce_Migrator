@RestResource(urlMapping='/orders/*')
global with sharing class OrderController {

    public class OrderControllerException extends Exception {}

    // Lightweight DTO returned to clients (never expose sObjects directly)
    global class OrderSummary {
        global String code;
        global String status;
        global Decimal totalAmount;
        global Boolean expedited;
    }

    // Constructor-injection style: swappable service instance (thin controller, delegates all logic)
    @TestVisible
    private static OrderService service = new OrderService();

    /**
     * GET /orders/{code}                -> single OrderSummary
     * GET /orders/status/{status}       -> List<OrderSummary>
     */
    @HttpGet
    global static OrderSummary doGet() {
        RestRequest req = RestContext.request;
        List<String> parts = getPathParts(req);
        // /orders/status/{status} is handled via list return; here handle single code
        if (parts.size() == 1) {
            return getOrder(parts.get(0));
        } else if (parts.size() == 2 && 'status'.equalsIgnoreCase(parts.get(0))) {
            // Marshal list into the response body directly
            List<OrderSummary> summaries = getOrdersByStatus(parts.get(1));
            RestContext.response.responseBody = Blob.valueOf(JSON.serialize(summaries));
            RestContext.response.addHeader('Content-Type', 'application/json');
            return null;
        }
        throw new OrderControllerException('Unsupported GET path');
    }

    /**
     * POST /orders/{code}/cancel -> HTTP 204 NO_CONTENT
     */
    @HttpPost
    global static void doPost() {
        RestRequest req = RestContext.request;
        List<String> parts = getPathParts(req);
        if (parts.size() == 2 && 'cancel'.equalsIgnoreCase(parts.get(1))) {
            cancelOrder(parts.get(0));
            RestContext.response.statusCode = 204;
            return;
        }
        throw new OrderControllerException('Unsupported POST path');
    }

    // ---- Thin controller: resolve inputs and delegate to the Service ----

    @TestVisible
    private static OrderSummary getOrder(String code) {
        if (String.isBlank(code)) {
            return null;
        }
        List<OrderSummary> summaries = service.getOrders(new Set<String>{ code });
        return summaries.isEmpty() ? null : summaries.get(0);
    }

    @TestVisible
    private static List<OrderSummary> getOrdersByStatus(String status) {
        if (String.isBlank(status)) {
            return new List<OrderSummary>();
        }
        return service.getOrdersByStatus(status);
    }

    @TestVisible
    private static void cancelOrder(String code) {
        if (String.isBlank(code)) {
            throw new OrderControllerException('Order code is required');
        }
        try {
            service.cancelOrders(new Set<String>{ code });
        } catch (OrderService.OrderServiceException e) {
            throw new OrderControllerException(e.getMessage());
        }
    }

    private static List<String> getPathParts(RestRequest req) {
        List<String> parts = new List<String>();
        if (req == null || String.isBlank(req.requestURI)) {
            return parts;
        }
        String uri = req.requestURI;
        Integer idx = uri.indexOf('/orders');
        String remainder = (idx >= 0) ? uri.substring(idx + '/orders'.length()) : uri;
        for (String p : remainder.split('/')) {
            if (!String.isBlank(p)) {
                parts.add(p);
            }
        }
        return parts;
    }
}