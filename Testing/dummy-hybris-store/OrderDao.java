package com.store.order;

import java.util.List;

/** Order data access (FlexibleSearch in real Hybris). */
public interface OrderDao {

    OrderModel findByCode(String code);

    // Ranked by an integer priority — 'priority' is not declared in items.xml,
    // so reconciliation should add Priority__c (inferred Number).
    List<OrderModel> findByPriority(int priority);
}
