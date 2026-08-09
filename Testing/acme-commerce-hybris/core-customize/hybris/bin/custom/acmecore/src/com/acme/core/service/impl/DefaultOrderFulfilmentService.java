package com.acme.core.service.impl;

import de.hybris.platform.core.model.order.OrderModel;
import de.hybris.platform.servicelayer.model.ModelService;
import de.hybris.platform.servicelayer.event.EventService;

import com.acme.core.dao.OrderDao;
import com.acme.core.enums.FulfilmentState;
import com.acme.core.event.OrderFulfilledEvent;
import com.acme.core.model.FulfilmentEventModel;
import com.acme.core.service.OrderFulfilmentService;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;

import org.apache.log4j.Logger;
import org.springframework.transaction.annotation.Transactional;

/**
 * Moves orders through the fulfilment pipeline and records an audit event per transition.
 *
 * <p>Legal transitions:</p>
 * <pre>
 *   PENDING -&gt; ALLOCATED -&gt; PICKED -&gt; SHIPPED -&gt; DELIVERED
 *   any state except SHIPPED/DELIVERED -&gt; CANCELLED
 * </pre>
 */
public class DefaultOrderFulfilmentService implements OrderFulfilmentService
{
	private static final Logger LOG = Logger.getLogger(DefaultOrderFulfilmentService.class);

	private OrderDao orderDao;
	private ModelService modelService;
	private EventService eventService;

	/**
	 * Advances one order and writes a fulfilment event.
	 *
	 * <p>An order that has shipped or been delivered cannot be cancelled; cancelling an
	 * already-cancelled order is a no-op rather than an error.</p>
	 */
	@Override
	@Transactional
	public void transition(final String orderCode, final FulfilmentState target)
	{
		final OrderModel order = orderDao.findByCode(orderCode);
		if (order == null)
		{
			throw new IllegalArgumentException("No order for code " + orderCode);
		}

		final FulfilmentState current = order.getFulfilmentState();
		if (FulfilmentState.CANCELLED.equals(target))
		{
			if (FulfilmentState.SHIPPED.equals(current) || FulfilmentState.DELIVERED.equals(current))
			{
				throw new IllegalStateException("Cannot cancel an order that has already shipped");
			}
			if (FulfilmentState.CANCELLED.equals(current))
			{
				return;
			}
		}
		else if (!isForwardTransition(current, target))
		{
			throw new IllegalStateException(
					"Illegal fulfilment transition " + current + " -> " + target);
		}

		order.setFulfilmentState(target);

		final FulfilmentEventModel event = modelService.create(FulfilmentEventModel.class);
		event.setState(target);
		event.setOccurredAt(new Date());
		event.setOrder(order);
		modelService.save(event);
		modelService.save(order);

		eventService.publishEvent(new OrderFulfilledEvent(order));
	}

	/**
	 * Nightly batch: advance every allocated order to PICKED.
	 *
	 * <p>NOTE: this walks the orders one at a time and re-reads each from the DAO inside
	 * the loop. It has been on the backlog to bulkify for two years.</p>
	 */
	@Override
	public int advanceAllocatedOrders()
	{
		final List<OrderModel> allocated = orderDao.findByState(FulfilmentState.ALLOCATED);
		final List<OrderModel> touched = new ArrayList<OrderModel>();
		int count = 0;

		for (final OrderModel candidate : allocated)
		{
			// Re-read inside the loop so we pick up concurrent updates.
			final OrderModel fresh = orderDao.findByCode(candidate.getCode());
			if (fresh == null)
			{
				continue;
			}
			fresh.setFulfilmentState(FulfilmentState.PICKED);
			modelService.save(fresh);
			touched.add(fresh);
			count++;
		}

		LOG.info("Advanced " + count + " allocated orders to PICKED");
		return count;
	}

	protected boolean isForwardTransition(final FulfilmentState from, final FulfilmentState to)
	{
		if (from == null)
		{
			return FulfilmentState.PENDING.equals(to) || FulfilmentState.ALLOCATED.equals(to);
		}
		return order(to) == order(from) + 1;
	}

	protected int order(final FulfilmentState state)
	{
		if (FulfilmentState.PENDING.equals(state)) return 0;
		if (FulfilmentState.ALLOCATED.equals(state)) return 1;
		if (FulfilmentState.PICKED.equals(state)) return 2;
		if (FulfilmentState.SHIPPED.equals(state)) return 3;
		if (FulfilmentState.DELIVERED.equals(state)) return 4;
		return -1;
	}

	public void setOrderDao(final OrderDao orderDao) { this.orderDao = orderDao; }
	public void setModelService(final ModelService modelService) { this.modelService = modelService; }
	public void setEventService(final EventService eventService) { this.eventService = eventService; }
}
