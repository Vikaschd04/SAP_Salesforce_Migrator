package com.acme.facades.pricing.impl;

import de.hybris.platform.core.model.order.OrderModel;
import de.hybris.platform.servicelayer.dto.converter.Converter;

import com.acme.core.data.PricingBreakdownData;
import com.acme.core.service.PricingService;
import com.acme.facades.pricing.PricingFacade;

public class DefaultPricingFacade implements PricingFacade
{
	private PricingService pricingService;
	private Converter<OrderModel, PricingBreakdownData> pricingBreakdownConverter;

	@Override
	public PricingBreakdownData getBreakdown(final OrderModel order)
	{
		if (order == null)
		{
			throw new IllegalArgumentException("Order is required");
		}
		return pricingBreakdownConverter.convert(order);
	}

	public void setPricingService(final PricingService s) { this.pricingService = s; }
	public void setPricingBreakdownConverter(final Converter<OrderModel, PricingBreakdownData> c)
	{
		this.pricingBreakdownConverter = c;
	}
}
