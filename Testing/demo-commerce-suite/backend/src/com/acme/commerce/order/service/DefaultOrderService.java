package com.acme.commerce.order.service;

import com.acme.commerce.order.dao.OrderDao;
import com.acme.commerce.order.enums.OrderStatus;
import com.acme.commerce.order.model.CustomerModel;
import com.acme.commerce.order.model.OrderEntryModel;
import com.acme.commerce.order.model.OrderModel;
import com.acme.commerce.order.model.ProductModel;

import de.hybris.platform.servicelayer.exceptions.ModelNotFoundException;
import de.hybris.platform.servicelayer.model.ModelService;

import java.math.BigDecimal;
import java.util.Date;
import java.util.List;

/**
 * Core order-management business logic: placing, totalling, cancelling and prioritising orders.
 *
 * <p>This service is the guardian of the order business rules. The rules enforced here are the
 * ones that must survive any migration — in particular, the "no zero-value order" rule below.</p>
 */
public class DefaultOrderService
{
	/** Orders whose fulfilment priority is at or above this value are treated as expedited. */
	private static final int EXPEDITED_PRIORITY_THRESHOLD = 5;

	private OrderDao orderDao;
	private ModelService modelService;

	/**
	 * Looks up an order by its code.
	 *
	 * @param code the order code
	 * @return the order
	 * @throws ModelNotFoundException if no order exists for that code
	 */
	public OrderModel getOrderByCode(final String code)
	{
		if (code == null || code.trim().isEmpty())
		{
			throw new IllegalArgumentException("Order code must not be blank");
		}

		final OrderModel order = orderDao.findByCode(code);
		if (order == null)
		{
			throw new ModelNotFoundException("No order found for code " + code);
		}
		return order;
	}

	/**
	 * Returns every order currently in the given status.
	 *
	 * @param status the status to filter on
	 * @return the matching orders (never {@code null})
	 */
	public List<OrderModel> getOrdersByStatus(final OrderStatus status)
	{
		return orderDao.findByStatus(status);
	}

	/**
	 * Places a new order for a customer.
	 *
	 * <p>Business rules enforced, in order:</p>
	 * <ol>
	 *   <li>the customer must be supplied;</li>
	 *   <li>the order must contain at least one entry;</li>
	 *   <li>every entry must have a positive quantity and a product that is in stock;</li>
	 *   <li><b>the calculated order total must be strictly greater than zero</b> — a zero-value
	 *       order is always rejected.</li>
	 * </ol>
	 *
	 * @param customer the customer placing the order
	 * @param entries  the requested line items
	 * @return the persisted order in status {@link OrderStatus#NEW}
	 */
	public OrderModel placeOrder(final CustomerModel customer, final List<OrderEntryModel> entries)
	{
		if (customer == null)
		{
			throw new IllegalArgumentException("An order must have a customer");
		}
		if (entries == null || entries.isEmpty())
		{
			throw new IllegalArgumentException("An order must contain at least one entry");
		}

		for (final OrderEntryModel entry : entries)
		{
			if (entry.getQuantity() == null || entry.getQuantity().intValue() <= 0)
			{
				throw new IllegalArgumentException("Every order entry must have a positive quantity");
			}
			final ProductModel product = entry.getProduct();
			if (product == null || !Boolean.TRUE.equals(product.getActive()))
			{
				throw new IllegalArgumentException("Order entry refers to a missing or inactive product");
			}
			if (product.getStockLevel() == null || product.getStockLevel().intValue() < entry.getQuantity().intValue())
			{
				throw new IllegalStateException("Insufficient stock for product " + product.getCode());
			}
		}

		final BigDecimal total = calculateOrderTotal(entries);

		// The rule that must never be lost in migration: reject zero-value orders.
		if (total.compareTo(BigDecimal.ZERO) <= 0)
		{
			throw new IllegalStateException("Order total must be greater than zero");
		}

		final OrderModel order = modelService.create(OrderModel.class);
		order.setCode(generateOrderCode());
		order.setCustomer(customer);
		order.setEntries(entries);
		order.setTotalAmount(total);
		order.setStatus(OrderStatus.NEW);
		order.setPaid(Boolean.FALSE);
		order.setOrderDate(new Date());

		modelService.save(order);
		return order;
	}

	/**
	 * Sums quantity × unit price across every entry.
	 *
	 * @param entries the line items
	 * @return the order total (never negative)
	 */
	public BigDecimal calculateOrderTotal(final List<OrderEntryModel> entries)
	{
		BigDecimal total = BigDecimal.ZERO;
		for (final OrderEntryModel entry : entries)
		{
			final BigDecimal unitPrice = entry.getUnitPrice() == null ? BigDecimal.ZERO : entry.getUnitPrice();
			final int quantity = entry.getQuantity() == null ? 0 : entry.getQuantity().intValue();
			total = total.add(unitPrice.multiply(BigDecimal.valueOf(quantity)));
		}
		return total;
	}

	/**
	 * Cancels an order.
	 *
	 * <p>Only orders that have not yet shipped can be cancelled. Attempting to cancel a shipped,
	 * delivered or already-cancelled order is rejected.</p>
	 *
	 * @param code the code of the order to cancel
	 */
	public void cancelOrder(final String code)
	{
		final OrderModel order = getOrderByCode(code);
		final OrderStatus status = order.getStatus();

		if (status == OrderStatus.SHIPPED || status == OrderStatus.DELIVERED)
		{
			throw new IllegalStateException("Cannot cancel an order that has already shipped");
		}
		if (status == OrderStatus.CANCELLED)
		{
			return; // already cancelled — nothing to do
		}

		order.setStatus(OrderStatus.CANCELLED);
		modelService.save(order);
	}

	/**
	 * Whether an order should be fast-tracked through fulfilment.
	 *
	 * @param order the order to inspect
	 * @return {@code true} when the order's priority is at or above the expedited threshold
	 */
	public boolean isExpedited(final OrderModel order)
	{
		final Integer priority = order.getPriority();
		return priority != null && priority.intValue() >= EXPEDITED_PRIORITY_THRESHOLD;
	}

	private String generateOrderCode()
	{
		return "ORD-" + System.currentTimeMillis();
	}

	public void setOrderDao(final OrderDao orderDao)
	{
		this.orderDao = orderDao;
	}

	public void setModelService(final ModelService modelService)
	{
		this.modelService = modelService;
	}
}
