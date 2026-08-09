package com.acme.core.interceptor;

import de.hybris.platform.core.model.order.OrderModel;
import de.hybris.platform.servicelayer.interceptor.InterceptorContext;
import de.hybris.platform.servicelayer.interceptor.InterceptorException;
import de.hybris.platform.servicelayer.interceptor.ValidateInterceptor;

import java.math.BigDecimal;

/**
 * Runs on every save of an Order. This is where the invariants live that must hold no
 * matter which code path wrote the order — a service, ImpEx, the backoffice, or a
 * cronjob. Anything enforced only in a service can be bypassed; anything enforced here
 * cannot.
 */
public class OrderValidateInterceptor implements ValidateInterceptor<OrderModel>
{
	@Override
	public void onValidate(final OrderModel order, final InterceptorContext ctx)
			throws InterceptorException
	{
		if (order.getCode() == null || order.getCode().trim().isEmpty())
		{
			throw new InterceptorException("Order code must not be blank");
		}

		if (order.getTotalPrice() != null
				&& BigDecimal.valueOf(order.getTotalPrice().doubleValue())
						.compareTo(BigDecimal.ZERO) <= 0)
		{
			throw new InterceptorException("Order total must be greater than zero");
		}

		if (order.getEntries() == null || order.getEntries().isEmpty())
		{
			throw new InterceptorException("An order must contain at least one entry");
		}

		if (order.getExpeditePriority() != null && order.getExpeditePriority().intValue() < 0)
		{
			throw new InterceptorException("Expedite priority cannot be negative");
		}
	}
}
