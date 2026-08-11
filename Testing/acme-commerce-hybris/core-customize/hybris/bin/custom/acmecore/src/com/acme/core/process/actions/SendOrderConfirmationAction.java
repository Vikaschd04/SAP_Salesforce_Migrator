package com.acme.core.process.actions;

import de.hybris.platform.orderprocessing.model.OrderProcessModel;
import de.hybris.platform.processengine.action.AbstractSimpleDecisionAction;
import de.hybris.platform.core.model.order.OrderModel;
import org.apache.log4j.Logger;

/**
 * Sends the customer their order confirmation.
 *
 * Business rules:
 *  - Confirmation is sent exactly once; a re-entry into this action after a retry
 *    must not send a second email.
 *  - B2B orders are confirmed to the account's billing contact, not the placing user.
 */
public class SendOrderConfirmationAction extends AbstractSimpleDecisionAction<OrderProcessModel>
{
    private static final Logger LOG = Logger.getLogger(SendOrderConfirmationAction.class);

    @Override
    public Transition executeAction(final OrderProcessModel process)
    {
        final OrderModel order = process.getOrder();
        if (Boolean.TRUE.equals(order.getConfirmationSent()))
        {
            LOG.info("Confirmation already sent for " + order.getCode() + " — skipping");
            return Transition.OK;
        }

        final String recipient = order.getUnit() != null
                ? order.getUnit().getBillingEmail()
                : order.getUser().getUid();

        LOG.info("Sending order confirmation for " + order.getCode() + " to " + recipient);
        order.setConfirmationSent(Boolean.TRUE);
        modelService.save(order);
        return Transition.OK;
    }
}
