package com.acme.core.dao;

import de.hybris.platform.core.model.order.OrderModel;
import de.hybris.platform.core.model.user.CustomerModel;

import com.acme.core.enums.FulfilmentState;

import java.util.Date;
import java.util.List;

/**
 * Data access for orders. All FlexibleSearch for the Order type belongs here — the
 * service layer must never issue queries directly.
 */
public interface OrderDao
{
	OrderModel findByCode(String code);

	List<OrderModel> findByState(FulfilmentState state);

	List<OrderModel> findByCustomer(CustomerModel customer);

	List<OrderModel> findPlacedBetween(Date from, Date to);

	List<OrderModel> findStaleCarts(Date olderThan, int max);
}
