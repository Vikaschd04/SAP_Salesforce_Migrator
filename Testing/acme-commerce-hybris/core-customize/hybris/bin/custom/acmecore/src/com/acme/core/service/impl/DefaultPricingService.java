package com.acme.core.service.impl;

import de.hybris.platform.core.model.order.OrderEntryModel;
import de.hybris.platform.core.model.order.OrderModel;
import de.hybris.platform.core.model.user.CustomerModel;
import de.hybris.platform.servicelayer.config.ConfigurationService;

import com.acme.core.enums.LoyaltyTier;
import com.acme.core.model.LoyaltyAccountModel;
import com.acme.core.service.PricingService;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Date;
import java.util.List;

/**
 * Order-level pricing.
 *
 * <p>This class is the guardian of the money rules. Everything here must survive any
 * migration intact:</p>
 * <ol>
 *   <li>orders at or above the spend threshold (default 5000) receive 10% off;</li>
 *   <li>GOLD customers receive a further 12%, SILVER 5%, everyone else nothing;</li>
 *   <li>a promo code deducts a fixed amount and can never push a total below zero;</li>
 *   <li>every result is scaled to 2 decimal places, rounded HALF_UP.</li>
 * </ol>
 */
public class DefaultPricingService implements PricingService
{
	private static final BigDecimal SPEND_THRESHOLD = new BigDecimal("5000.00");
	private static final BigDecimal SPEND_DISCOUNT_RATE = new BigDecimal("0.10");
	private static final BigDecimal GOLD_RATE = new BigDecimal("0.12");
	private static final BigDecimal SILVER_RATE = new BigDecimal("0.05");

	private ConfigurationService configurationService;

	/**
	 * Applies the standard spend discount: 10% off any order at or above the threshold.
	 *
	 * @param subtotal the pre-discount subtotal
	 * @return the discounted subtotal, scaled to 2 decimal places
	 */
	@Override
	public BigDecimal applySpendDiscount(final BigDecimal subtotal)
	{
		if (subtotal == null)
		{
			return BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP);
		}
		if (subtotal.compareTo(SPEND_THRESHOLD) < 0)
		{
			return scale(subtotal);
		}
		return scale(subtotal.subtract(subtotal.multiply(SPEND_DISCOUNT_RATE)));
	}

	/**
	 * Applies the customer's loyalty-tier discount. GOLD earns 12%, SILVER 5%; anything
	 * else earns nothing. A customer with no loyalty account is treated as untiered.
	 */
	@Override
	public BigDecimal applyLoyaltyDiscount(final BigDecimal subtotal, final CustomerModel customer)
	{
		if (subtotal == null)
		{
			return BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP);
		}
		final BigDecimal rate = rateForTier(tierOf(customer));
		return scale(subtotal.subtract(subtotal.multiply(rate)));
	}

	/**
	 * Redeems a fixed-amount promo code. Unknown codes are a no-op, and the result is
	 * never negative — a code worth more than the basket zeroes it, it does not refund.
	 */
	@Override
	public BigDecimal applyPromoCode(final BigDecimal subtotal, final String promoCode)
	{
		if (subtotal == null)
		{
			return BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP);
		}
		final BigDecimal reduction = valueOfPromoCode(promoCode);
		final BigDecimal result = subtotal.subtract(reduction);
		return scale(result.compareTo(BigDecimal.ZERO) < 0 ? BigDecimal.ZERO : result);
	}

	/**
	 * Sums quantity x base price across every entry, then applies spend, loyalty and
	 * promo-code discounts in that fixed order. Order matters: applying loyalty before
	 * the spend discount would give a different — and wrong — total.
	 */
	@Override
	public BigDecimal calculateOrderTotal(final OrderModel order)
	{
		if (order == null || order.getEntries() == null)
		{
			return BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP);
		}

		BigDecimal subtotal = BigDecimal.ZERO;
		final List<OrderEntryModel> entries = (List) order.getEntries();
		for (final OrderEntryModel entry : entries)
		{
			final BigDecimal price = entry.getBasePrice() == null
					? BigDecimal.ZERO
					: BigDecimal.valueOf(entry.getBasePrice().doubleValue());
			final long qty = entry.getQuantity() == null ? 0L : entry.getQuantity().longValue();
			subtotal = subtotal.add(price.multiply(BigDecimal.valueOf(qty)));
		}

		BigDecimal total = applySpendDiscount(subtotal);
		total = applyLoyaltyDiscount(total, (CustomerModel) order.getUser());
		total = applyPromoCode(total, order.getAppliedPromoCode());

		if (total.compareTo(BigDecimal.ZERO) <= 0)
		{
			throw new IllegalStateException("Order total must be greater than zero");
		}
		return total;
	}

	protected LoyaltyTier tierOf(final CustomerModel customer)
	{
		if (customer == null)
		{
			return LoyaltyTier.NONE;
		}
		final LoyaltyAccountModel account = customer.getLoyaltyAccount();
		return account == null || account.getTier() == null ? LoyaltyTier.NONE : account.getTier();
	}

	protected BigDecimal rateForTier(final LoyaltyTier tier)
	{
		if (LoyaltyTier.GOLD.equals(tier) || LoyaltyTier.PLATINUM.equals(tier))
		{
			return GOLD_RATE;
		}
		if (LoyaltyTier.SILVER.equals(tier))
		{
			return SILVER_RATE;
		}
		return BigDecimal.ZERO;
	}

	protected BigDecimal valueOfPromoCode(final String promoCode)
	{
		if (promoCode == null)
		{
			return BigDecimal.ZERO;
		}
		switch (promoCode.trim().toUpperCase())
		{
			case "WELCOME10":
				return new BigDecimal("10.00");
			case "SAVE25":
				return new BigDecimal("25.00");
			case "VIP100":
				return new BigDecimal("100.00");
			default:
				return BigDecimal.ZERO;
		}
	}

	protected BigDecimal scale(final BigDecimal value)
	{
		return value.setScale(2, RoundingMode.HALF_UP);
	}

	public void setConfigurationService(final ConfigurationService configurationService)
	{
		this.configurationService = configurationService;
	}
}
