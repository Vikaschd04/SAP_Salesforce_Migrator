package com.acme.core.service;

import com.acme.core.enums.FulfilmentState;

public interface OrderFulfilmentService
{
	void transition(String orderCode, FulfilmentState target);

	int advanceAllocatedOrders();
}
