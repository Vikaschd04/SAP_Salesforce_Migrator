package com.acme.core.process.actions;

import de.hybris.platform.orderprocessing.model.OrderProcessModel;
import de.hybris.platform.processengine.action.AbstractSimpleDecisionAction;
import de.hybris.platform.core.model.order.OrderModel;
import de.hybris.platform.core.model.order.OrderEntryModel;
import org.apache.log4j.Logger;

import java.math.BigDecimal;

/**
 * First step of order fulfilment: is this order safe to process at all?
 *
 * Business rules:
 *  - An order with a zero or negative total is never fulfilled. This has caught
 *    mis-priced promotions twice in production.
 *  - An order with no entries is rejected — an empty order usually means a cart
 *    was cleared mid-checkout.
 *  - Orders above the manual-review threshold (250,000) go to review rather than
 *    straight through, regardless of payment status.
 */
public class CheckOrderAction extends AbstractSimpleDecisionAction<OrderProcessModel>
{
    private static final Logger LOG = Logger.getLogger(CheckOrderAction.class);
    private static final BigDecimal MANUAL_REVIEW_THRESHOLD = new BigDecimal("250000");

    @Override
    public Transition executeAction(final OrderProcessModel process)
    {
        final OrderModel order = process.getOrder();
        if (order == null)
        {
            LOG.error("No order attached to process " + process.getCode());
            return Transition.NOK;
        }

        final BigDecimal total = BigDecimal.valueOf(
                order.getTotalPrice() == null ? 0d : order.getTotalPrice());
        if (total.compareTo(BigDecimal.ZERO) <= 0)
        {
            LOG.warn("Rejecting order " + order.getCode() + " with non-positive total");
            return Transition.NOK;
        }

        if (order.getEntries() == null || order.getEntries().isEmpty())
        {
            LOG.warn("Rejecting order " + order.getCode() + " with no entries");
            return Transition.NOK;
        }

        for (final OrderEntryModel entry : order.getEntries())
        {
            if (entry.getQuantity() == null || entry.getQuantity() <= 0)
            {
                LOG.warn("Rejecting order " + order.getCode() + " — non-positive quantity");
                return Transition.NOK;
            }
        }

        if (total.compareTo(MANUAL_REVIEW_THRESHOLD) > 0)
        {
            order.setStatus(de.hybris.platform.core.enums.OrderStatus.SUSPENDED);
            modelService.save(order);
            LOG.info("Order " + order.getCode() + " held for manual review");
            return Transition.NOK;
        }

        return Transition.OK;
    }
}
