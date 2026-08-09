package com.acme.facades.pricing;

import de.hybris.platform.core.model.order.OrderModel;

import com.acme.core.data.PricingBreakdownData;

public interface PricingFacade
{
	PricingBreakdownData getBreakdown(OrderModel order);
}
