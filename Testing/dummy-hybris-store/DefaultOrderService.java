package com.store.order;

import java.math.BigDecimal;
import java.util.List;

/**
 * Order service. Depends on OrderDao (same domain) AND CustomerDao (Customer
 * domain) — a cross-domain dependency, so Customer is translated first and its
 * Selector signature is injected here.
 */
public class DefaultOrderService {

    private OrderDao orderDao;
    private CustomerDao customerDao;

    public void setOrderDao(OrderDao orderDao) { this.orderDao = orderDao; }
    public void setCustomerDao(CustomerDao customerDao) { this.customerDao = customerDao; }

    /** Business rule: an order total must be greater than zero. */
    public OrderModel getOrder(String code) {
        OrderModel order = orderDao.findByCode(code);
        if (order != null && order.getTotalAmount().compareTo(BigDecimal.ZERO) <= 0) {
            throw new IllegalStateException("Order total must be positive");
        }
        return order;
    }

    /** Business rule: orders with a priority greater than 5 are expedited. */
    public boolean isExpedited(OrderModel order) {
        return order.getPriority() > 5;
    }

    /** Business rule: a customer must exist before an order can be placed for them. */
    public OrderModel placeOrder(String customerUid, List<OrderModel> lines) {
        CustomerModel customer = customerDao.findByUid(customerUid);
        if (customer == null) {
            throw new IllegalArgumentException("Unknown customer: " + customerUid);
        }
        return orderDao.findByCode(lines.get(0).getCode());
    }
}
