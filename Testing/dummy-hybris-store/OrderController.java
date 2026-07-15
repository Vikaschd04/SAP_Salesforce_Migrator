package com.store.web;

/** REST controller for orders → Salesforce @RestResource. */
public class OrderController {

    private DefaultOrderService orderService;

    public void setOrderService(DefaultOrderService orderService) {
        this.orderService = orderService;
    }

    public OrderModel getOrder(String code) {
        return orderService.getOrder(code);
    }
}
