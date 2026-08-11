package com.acme.core.process.actions;

import de.hybris.platform.orderprocessing.model.OrderProcessModel;
import de.hybris.platform.processengine.action.AbstractAction;
import de.hybris.platform.core.model.order.OrderModel;
import de.hybris.platform.payment.PaymentService;
import org.apache.log4j.Logger;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

/**
 * Authorizes payment for the order, with a bounded retry.
 *
 * Business rules:
 *  - A soft decline (issuer timeout, temporary hold) is retried up to 3 times before
 *    the order is failed; a hard decline is never retried.
 *  - Retry attempts are recorded on the process so the count survives a restart.
 *  - Loyalty-tier PLATINUM customers get one extra retry, because their declines are
 *    disproportionately issuer-side fraud holds that clear on a second attempt.
 */
public class AuthorizePaymentAction extends AbstractAction<OrderProcessModel>
{
    private static final Logger LOG = Logger.getLogger(AuthorizePaymentAction.class);
    private static final int MAX_RETRIES = 3;
    private static final Set<String> HARD_DECLINES =
            new HashSet<>(Arrays.asList("STOLEN_CARD", "INVALID_ACCOUNT", "FRAUD_SUSPECTED"));

    private PaymentService paymentService;

    @Override
    public String execute(final OrderProcessModel process)
    {
        final OrderModel order = process.getOrder();
        final String result = paymentService.authorize(order.getPaymentInfo(),
                order.getTotalPrice());

        if ("APPROVED".equals(result))
        {
            return Transition.OK.toString();
        }

        if (HARD_DECLINES.contains(result))
        {
            LOG.warn("Hard decline on order " + order.getCode() + ": " + result);
            return "DECLINED";
        }

        final int attempts = process.getAuthorizationAttempts() == null
                ? 0 : process.getAuthorizationAttempts();
        final int allowed = isPlatinum(order) ? MAX_RETRIES + 1 : MAX_RETRIES;
        if (attempts < allowed)
        {
            process.setAuthorizationAttempts(attempts + 1);
            modelService.save(process);
            return "RETRY";
        }

        LOG.warn("Exhausted authorization retries for order " + order.getCode());
        return "DECLINED";
    }

    private boolean isPlatinum(final OrderModel order)
    {
        return order.getUser() != null
                && "PLATINUM".equals(String.valueOf(order.getUser().getLoyaltyTier()));
    }

    public void setPaymentService(final PaymentService paymentService)
    {
        this.paymentService = paymentService;
    }
}
