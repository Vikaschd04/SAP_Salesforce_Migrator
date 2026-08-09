package com.acme.core.event;

import de.hybris.platform.core.model.order.OrderModel;
import de.hybris.platform.core.model.user.CustomerModel;
import de.hybris.platform.servicelayer.event.impl.AbstractEventListener;
import de.hybris.platform.servicelayer.model.ModelService;
import de.hybris.platform.commerceservices.event.OrderPlacedEvent;

import com.acme.core.model.LoyaltyAccountModel;

import java.math.BigDecimal;

import org.apache.log4j.Logger;

/**
 * Awards loyalty points when an order is placed: one point per whole unit of currency,
 * doubled for GOLD and PLATINUM members.
 */
public class OrderPlacedEventListener extends AbstractEventListener<OrderPlacedEvent>
{
	private static final Logger LOG = Logger.getLogger(OrderPlacedEventListener.class);

	private ModelService modelService;

	@Override
	protected void onEvent(final OrderPlacedEvent event)
	{
		final OrderModel order = event.getProcess().getOrder();
		if (order == null || !(order.getUser() instanceof CustomerModel))
		{
			return;
		}

		final CustomerModel customer = (CustomerModel) order.getUser();
		final LoyaltyAccountModel account = customer.getLoyaltyAccount();
		if (account == null)
		{
			LOG.debug("No loyalty account for " + customer.getUid() + "; no points awarded");
			return;
		}

		final BigDecimal total = order.getTotalPrice() == null
				? BigDecimal.ZERO
				: BigDecimal.valueOf(order.getTotalPrice().doubleValue());

		int points = total.intValue();
		if (isDoublePoints(account)) { points = points * 2; }

		final int balance = account.getPointsBalance() == null ? 0 : account.getPointsBalance().intValue();
		account.setPointsBalance(Integer.valueOf(balance + points));
		order.setLoyaltyPointsEarned(Integer.valueOf(points));

		modelService.save(account);
		modelService.save(order);
	}

	protected boolean isDoublePoints(final LoyaltyAccountModel account)
	{
		return account.getTier() != null
				&& ("GOLD".equals(account.getTier().getCode()) || "PLATINUM".equals(account.getTier().getCode()));
	}

	public void setModelService(final ModelService modelService) { this.modelService = modelService; }
}
