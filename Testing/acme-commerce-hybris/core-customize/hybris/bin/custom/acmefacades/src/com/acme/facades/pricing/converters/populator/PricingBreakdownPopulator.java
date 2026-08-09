package com.acme.facades.pricing.converters.populator;

import de.hybris.platform.converters.Populator;
import de.hybris.platform.core.model.order.OrderModel;
import de.hybris.platform.core.model.order.OrderEntryModel;
import de.hybris.platform.core.model.user.CustomerModel;
import de.hybris.platform.servicelayer.dto.converter.ConversionException;

import com.acme.core.data.PricingBreakdownData;
import com.acme.core.service.PricingService;

import java.math.BigDecimal;
import java.util.List;

/**
 * Explains how a total was reached, step by step, for the storefront's price panel.
 *
 * <p>The subtraction order here mirrors {@code DefaultPricingService.calculateOrderTotal}
 * exactly. If the two ever disagree the shopper is shown a breakdown that does not add up
 * to what they are charged, which is the sort of bug that reaches Twitter.</p>
 */
public class PricingBreakdownPopulator implements Populator<OrderModel, PricingBreakdownData>
{
	private PricingService pricingService;

	@Override
	public void populate(final OrderModel source, final PricingBreakdownData target)
			throws ConversionException
	{
		BigDecimal subtotal = BigDecimal.ZERO;
		final List<OrderEntryModel> entries = (List) source.getEntries();
		if (entries != null)
		{
			for (final OrderEntryModel entry : entries)
			{
				final BigDecimal price = entry.getBasePrice() == null
						? BigDecimal.ZERO
						: BigDecimal.valueOf(entry.getBasePrice().doubleValue());
				final long qty = entry.getQuantity() == null ? 0L : entry.getQuantity().longValue();
				subtotal = subtotal.add(price.multiply(BigDecimal.valueOf(qty)));
			}
		}
		target.setSubtotal(subtotal);

		final BigDecimal afterSpend = pricingService.applySpendDiscount(subtotal);
		target.setSpendDiscount(subtotal.subtract(afterSpend));

		final BigDecimal afterLoyalty =
				pricingService.applyLoyaltyDiscount(afterSpend, (CustomerModel) source.getUser());
		target.setLoyaltyDiscount(afterSpend.subtract(afterLoyalty));

		final BigDecimal afterPromo =
				pricingService.applyPromoCode(afterLoyalty, source.getAppliedPromoCode());
		target.setPromoDiscount(afterLoyalty.subtract(afterPromo));

		target.setAppliedPromoCode(source.getAppliedPromoCode());
		target.setTotal(afterPromo);
	}

	public void setPricingService(final PricingService pricingService)
	{
		this.pricingService = pricingService;
	}
}
