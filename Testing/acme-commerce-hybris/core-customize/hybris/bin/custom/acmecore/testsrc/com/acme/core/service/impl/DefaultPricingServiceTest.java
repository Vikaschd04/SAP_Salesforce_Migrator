package com.acme.core.service.impl;

import de.hybris.bootstrap.annotations.UnitTest;
import de.hybris.platform.core.model.user.CustomerModel;

import com.acme.core.enums.LoyaltyTier;
import com.acme.core.model.LoyaltyAccountModel;

import org.junit.Before;
import org.junit.Test;
import org.junit.experimental.categories.Category;

import java.math.BigDecimal;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

/**
 * Pure-calculation tests for the money rules. Every figure asserted here was agreed with
 * finance and has been green in CI for years — which is what makes this suite the best
 * available evidence of how the legacy system actually behaved.
 */
@UnitTest
public class DefaultPricingServiceTest
{
	private DefaultPricingService pricingService;

	@Before
	public void setUp()
	{
		pricingService = new DefaultPricingService();
	}

	private CustomerModel customerWithTier(final LoyaltyTier tier)
	{
		final LoyaltyAccountModel account = new LoyaltyAccountModel();
		account.setTier(tier);
		final CustomerModel customer = new CustomerModel();
		customer.setLoyaltyAccount(account);
		return customer;
	}

	@Test
	public void spendDiscountAppliesTenPercentAtTheThreshold()
	{
		assertEquals(new BigDecimal("4500.00"), pricingService.applySpendDiscount(new BigDecimal("5000.00")));
	}

	@Test
	public void spendDiscountAppliesTenPercentAboveTheThreshold()
	{
		assertEquals(new BigDecimal("7200.00"), pricingService.applySpendDiscount(new BigDecimal("8000.00")));
	}

	@Test
	public void spendDiscountLeavesSmallerOrdersAlone()
	{
		assertEquals(new BigDecimal("4999.99"), pricingService.applySpendDiscount(new BigDecimal("4999.99")));
	}

	@Test
	public void goldCustomersGetTwelvePercentOff()
	{
		assertEquals(new BigDecimal("88.00"),
				pricingService.applyLoyaltyDiscount(new BigDecimal("100.00"), customerWithTier(LoyaltyTier.GOLD)));
	}

	@Test
	public void platinumCustomersGetTheGoldRate()
	{
		assertEquals(new BigDecimal("88.00"),
				pricingService.applyLoyaltyDiscount(new BigDecimal("100.00"), customerWithTier(LoyaltyTier.PLATINUM)));
	}

	@Test
	public void silverCustomersGetFivePercentOff()
	{
		assertEquals(new BigDecimal("95.00"),
				pricingService.applyLoyaltyDiscount(new BigDecimal("100.00"), customerWithTier(LoyaltyTier.SILVER)));
	}

	@Test
	public void bronzeCustomersGetNothing()
	{
		assertEquals(new BigDecimal("100.00"),
				pricingService.applyLoyaltyDiscount(new BigDecimal("100.00"), customerWithTier(LoyaltyTier.BRONZE)));
	}

	@Test
	public void anonymousCustomersGetNoLoyaltyDiscount()
	{
		assertEquals(new BigDecimal("100.00"),
				pricingService.applyLoyaltyDiscount(new BigDecimal("100.00"), null));
	}

	@Test
	public void welcomeCodeTakesTenOff()
	{
		assertEquals(new BigDecimal("40.00"), pricingService.applyPromoCode(new BigDecimal("50.00"), "WELCOME10"));
	}

	@Test
	public void saveCodeTakesTwentyFiveOff()
	{
		assertEquals(new BigDecimal("25.00"), pricingService.applyPromoCode(new BigDecimal("50.00"), "SAVE25"));
	}

	@Test
	public void vipCodeTakesOneHundredOff()
	{
		assertEquals(new BigDecimal("400.00"), pricingService.applyPromoCode(new BigDecimal("500.00"), "VIP100"));
	}

	@Test
	public void promoCodesAreCaseInsensitive()
	{
		assertEquals(new BigDecimal("40.00"), pricingService.applyPromoCode(new BigDecimal("50.00"), "welcome10"));
	}

	@Test
	public void unknownPromoCodesChangeNothing()
	{
		assertEquals(new BigDecimal("50.00"), pricingService.applyPromoCode(new BigDecimal("50.00"), "NOTACODE"));
	}

	@Test
	public void aPromoCodeNeverPushesATotalBelowZero()
	{
		assertEquals(new BigDecimal("0.00"), pricingService.applyPromoCode(new BigDecimal("5.00"), "SAVE25"));
	}

	@Test
	public void goldIsTreatedAsADiscountedTier()
	{
		assertTrue(pricingService.rateForTier(LoyaltyTier.GOLD).compareTo(BigDecimal.ZERO) > 0);
	}
}
