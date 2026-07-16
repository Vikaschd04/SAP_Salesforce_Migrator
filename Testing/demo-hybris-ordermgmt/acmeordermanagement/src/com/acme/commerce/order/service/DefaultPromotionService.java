package com.acme.commerce.order.service;

import com.acme.commerce.order.enums.LoyaltyTier;
import com.acme.commerce.order.model.CustomerModel;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * Calculates order-level discounts and promotional pricing.
 *
 * <p>This is classic commerce pricing logic — tiered thresholds, loyalty multipliers and
 * promo codes. On Salesforce this responsibility is owned by a configure-price-quote (CPQ)
 * product rather than hand-written code, which is why it is separated out here.</p>
 */
public class DefaultPromotionService
{
	private static final BigDecimal SPEND_THRESHOLD = new BigDecimal("100.00");
	private static final BigDecimal SPEND_DISCOUNT_RATE = new BigDecimal("0.10");
	private static final BigDecimal SILVER_RATE = new BigDecimal("0.05");
	private static final BigDecimal GOLD_RATE = new BigDecimal("0.12");

	/**
	 * Applies the standard spend-based discount: 10% off any order over the spend threshold.
	 *
	 * @param subtotal the pre-discount order subtotal
	 * @return the discounted subtotal, scaled to 2 decimal places
	 */
	public BigDecimal applySpendDiscount(final BigDecimal subtotal)
	{
		if (subtotal == null || subtotal.compareTo(SPEND_THRESHOLD) < 0)
		{
			return scale(subtotal == null ? BigDecimal.ZERO : subtotal);
		}
		final BigDecimal discount = subtotal.multiply(SPEND_DISCOUNT_RATE);
		return scale(subtotal.subtract(discount));
	}

	/**
	 * Applies a customer's loyalty-tier discount on top of a subtotal.
	 *
	 * @param subtotal the order subtotal
	 * @param customer the customer, whose loyalty tier drives the rate
	 * @return the discounted subtotal, scaled to 2 decimal places
	 */
	public BigDecimal applyLoyaltyDiscount(final BigDecimal subtotal, final CustomerModel customer)
	{
		if (subtotal == null)
		{
			return BigDecimal.ZERO;
		}
		final BigDecimal rate = rateForTier(customer == null ? null : customer.getLoyaltyTier());
		final BigDecimal discount = subtotal.multiply(rate);
		return scale(subtotal.subtract(discount));
	}

	/**
	 * Redeems a fixed-amount promo code against a subtotal. Unknown codes are a no-op.
	 *
	 * @param subtotal the order subtotal
	 * @param promoCode the code entered by the customer
	 * @return the subtotal after redemption, never below zero, scaled to 2 decimal places
	 */
	public BigDecimal applyPromoCode(final BigDecimal subtotal, final String promoCode)
	{
		if (subtotal == null)
		{
			return BigDecimal.ZERO;
		}
		final BigDecimal reduction = valueOfPromoCode(promoCode);
		final BigDecimal result = subtotal.subtract(reduction);
		return scale(result.compareTo(BigDecimal.ZERO) < 0 ? BigDecimal.ZERO : result);
	}

	private BigDecimal rateForTier(final LoyaltyTier tier)
	{
		if (tier == LoyaltyTier.GOLD)
		{
			return GOLD_RATE;
		}
		if (tier == LoyaltyTier.SILVER)
		{
			return SILVER_RATE;
		}
		return BigDecimal.ZERO;
	}

	private BigDecimal valueOfPromoCode(final String promoCode)
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
			default:
				return BigDecimal.ZERO;
		}
	}

	private BigDecimal scale(final BigDecimal value)
	{
		return value.setScale(2, RoundingMode.HALF_UP);
	}
}
