package com.acme.core.service;

import de.hybris.platform.core.model.order.OrderModel;
import de.hybris.platform.core.model.user.CustomerModel;

import java.math.BigDecimal;

public interface PricingService
{
	BigDecimal applySpendDiscount(BigDecimal subtotal);

	BigDecimal applyLoyaltyDiscount(BigDecimal subtotal, CustomerModel customer);

	BigDecimal applyPromoCode(BigDecimal subtotal, String promoCode);

	BigDecimal calculateOrderTotal(OrderModel order);
}
