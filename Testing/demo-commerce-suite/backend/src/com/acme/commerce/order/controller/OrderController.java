package com.acme.commerce.order.controller;

import com.acme.commerce.order.enums.OrderStatus;
import com.acme.commerce.order.model.OrderModel;
import com.acme.commerce.order.service.DefaultOrderService;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.List;

/**
 * Read-only REST endpoints for orders, exposed under {@code /orders}.
 *
 * <p>Each handler is thin: it resolves inputs, calls the order service, and maps the result to a
 * small response object. No business rules live in the controller.</p>
 */
@RestController
@RequestMapping(value = "/orders")
public class OrderController
{
	@Autowired
	private DefaultOrderService orderService;

	/**
	 * GET /orders/{code} — returns a single order as a lightweight summary.
	 *
	 * @param code the order code
	 * @return the order summary
	 */
	@RequestMapping(value = "/{code}", method = RequestMethod.GET)
	@ResponseBody
	public OrderSummary getOrder(@PathVariable final String code)
	{
		final OrderModel order = orderService.getOrderByCode(code);
		return toSummary(order);
	}

	/**
	 * GET /orders/status/{status} — lists order summaries in a given status.
	 *
	 * @param status the status name (e.g. "NEW")
	 * @return the matching order summaries
	 */
	@RequestMapping(value = "/status/{status}", method = RequestMethod.GET)
	@ResponseBody
	public List<OrderSummary> getOrdersByStatus(@PathVariable final String status)
	{
		final OrderStatus parsed = OrderStatus.valueOf(status.toUpperCase());
		final List<OrderSummary> summaries = new ArrayList<>();
		for (final OrderModel order : orderService.getOrdersByStatus(parsed))
		{
			summaries.add(toSummary(order));
		}
		return summaries;
	}

	/**
	 * POST /orders/{code}/cancel — cancels an order that has not yet shipped.
	 *
	 * @param code the order code
	 */
	@RequestMapping(value = "/{code}/cancel", method = RequestMethod.POST)
	@ResponseStatus(HttpStatus.NO_CONTENT)
	public void cancelOrder(@PathVariable final String code)
	{
		orderService.cancelOrder(code);
	}

	private OrderSummary toSummary(final OrderModel order)
	{
		final OrderSummary summary = new OrderSummary();
		summary.setCode(order.getCode());
		summary.setStatus(order.getStatus() == null ? null : order.getStatus().getCode());
		summary.setTotalAmount(order.getTotalAmount());
		summary.setExpedited(orderService.isExpedited(order));
		return summary;
	}
}
