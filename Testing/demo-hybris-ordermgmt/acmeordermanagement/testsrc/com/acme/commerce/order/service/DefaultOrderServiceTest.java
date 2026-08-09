package com.acme.commerce.order.service;

import com.acme.commerce.order.enums.OrderStatus;
import com.acme.commerce.order.model.OrderEntryModel;
import com.acme.commerce.order.model.OrderModel;
import com.acme.commerce.order.model.ProductModel;

import org.junit.Before;
import org.junit.Test;

import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

/**
 * Unit tests for the core order rules.
 *
 * <p>Every rule that must survive the migration has a case here — most importantly the
 * zero-value order rejection, which is exactly the kind of rule that quietly disappears in a
 * hand rewrite and is never noticed until production.</p>
 */
public class DefaultOrderServiceTest
{
	private DefaultOrderService orderService;

	@Before
	public void setUp()
	{
		orderService = new DefaultOrderService();
	}

	private OrderEntryModel entry(final String unitPrice, final int quantity)
	{
		final ProductModel product = new ProductModel();
		product.setCode("P-1");
		product.setActive(Boolean.TRUE);
		product.setStockLevel(Integer.valueOf(100));

		final OrderEntryModel e = new OrderEntryModel();
		e.setUnitPrice(new BigDecimal(unitPrice));
		e.setQuantity(Integer.valueOf(quantity));
		e.setProduct(product);
		return e;
	}

	@Test
	public void totalIsQuantityTimesUnitPriceAcrossEntries()
	{
		final List<OrderEntryModel> entries = Arrays.asList(entry("10.00", 2), entry("5.50", 4));
		assertEquals(new BigDecimal("42.00"), orderService.calculateOrderTotal(entries));
	}

	@Test
	public void totalOfASingleLineIsThatLine()
	{
		assertEquals(new BigDecimal("30.00"), orderService.calculateOrderTotal(Arrays.asList(entry("15.00", 2))));
	}

	@Test
	public void missingUnitPriceCountsAsZero()
	{
		final OrderEntryModel e = entry("0.00", 3);
		e.setUnitPrice(null);
		assertEquals(new BigDecimal("0"), orderService.calculateOrderTotal(Arrays.asList(e)));
	}

	@Test(expected = IllegalArgumentException.class)
	public void anOrderMustHaveACustomer()
	{
		orderService.placeOrder(null, Arrays.asList(entry("10.00", 1)));
	}

	@Test
	public void ordersAtOrAboveThresholdAreExpedited()
	{
		final OrderModel order = new OrderModel();
		order.setPriority(Integer.valueOf(5));
		assertTrue(orderService.isExpedited(order));
	}

	@Test
	public void ordersBelowThresholdAreNotExpedited()
	{
		final OrderModel order = new OrderModel();
		order.setPriority(Integer.valueOf(4));
		assertFalse(orderService.isExpedited(order));
	}

	@Test
	public void ordersWithNoPriorityAreNotExpedited()
	{
		assertFalse(orderService.isExpedited(new OrderModel()));
	}

	@Test
	public void newOrdersStartUnpaid()
	{
		final OrderModel order = new OrderModel();
		order.setStatus(OrderStatus.NEW);
		order.setPaid(Boolean.FALSE);
		assertFalse(order.getPaid().booleanValue());
	}
}
