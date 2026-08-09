package com.acme.commerce.order.service;

import com.acme.commerce.order.enums.LoyaltyTier;
import com.acme.commerce.order.model.CustomerModel;

import org.junit.Before;
import org.junit.Test;

import java.math.BigDecimal;

import static org.junit.Assert.assertEquals;

/**
 * Unit tests for the pricing rules.
 *
 * <p>These are pure-calculation tests: a known input goes in, an exact figure comes out. That
 * makes them the strongest possible evidence of what the old system actually did — which is
 * why the migration replays them against the generated Apex rather than throwing them away.</p>
 */
public class DefaultPromotionServiceTest
{
	private DefaultPromotionService promotionService;

	@Before
	public void setUp()
	{
		promotionService = new DefaultPromotionService();
	}

	@Test
	public void spendDiscountAppliesTenPercentOverThreshold()
	{
		assertEquals(new BigDecimal("180.00"), promotionService.applySpendDiscount(new BigDecimal("200.00")));
	}

	@Test
	public void spendDiscountLeavesSmallOrdersAlone()
	{
		assertEquals(new BigDecimal("99.99"), promotionService.applySpendDiscount(new BigDecimal("99.99")));
	}

	@Test
	public void spendDiscountAppliesExactlyAtTheThreshold()
	{
		assertEquals(new BigDecimal("90.00"), promotionService.applySpendDiscount(new BigDecimal("100.00")));
	}

	@Test
	public void goldCustomersGetTwelvePercentOff()
	{
		final CustomerModel customer = new CustomerModel();
		customer.setLoyaltyTier(LoyaltyTier.GOLD);
		assertEquals(new BigDecimal("88.00"), promotionService.applyLoyaltyDiscount(new BigDecimal("100.00"), customer));
	}

	@Test
	public void silverCustomersGetFivePercentOff()
	{
		final CustomerModel customer = new CustomerModel();
		customer.setLoyaltyTier(LoyaltyTier.SILVER);
		assertEquals(new BigDecimal("95.00"), promotionService.applyLoyaltyDiscount(new BigDecimal("100.00"), customer));
	}

	@Test
	public void customersWithNoTierGetNoLoyaltyDiscount()
	{
		assertEquals(new BigDecimal("100.00"), promotionService.applyLoyaltyDiscount(new BigDecimal("100.00"), null));
	}

	@Test
	public void welcomeCodeTakesTenOffTheSubtotal()
	{
		assertEquals(new BigDecimal("40.00"), promotionService.applyPromoCode(new BigDecimal("50.00"), "WELCOME10"));
	}

	@Test
	public void saveCodeTakesTwentyFiveOffTheSubtotal()
	{
		assertEquals(new BigDecimal("25.00"), promotionService.applyPromoCode(new BigDecimal("50.00"), "SAVE25"));
	}

	@Test
	public void unknownPromoCodesChangeNothing()
	{
		assertEquals(new BigDecimal("50.00"), promotionService.applyPromoCode(new BigDecimal("50.00"), "NOTACODE"));
	}

	@Test
	public void promoCodeNeverPushesATotalBelowZero()
	{
		assertEquals(new BigDecimal("0.00"), promotionService.applyPromoCode(new BigDecimal("5.00"), "SAVE25"));
	}
}
