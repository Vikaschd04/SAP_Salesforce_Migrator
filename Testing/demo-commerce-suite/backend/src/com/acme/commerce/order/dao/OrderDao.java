package com.acme.commerce.order.dao;

import com.acme.commerce.order.enums.OrderStatus;
import com.acme.commerce.order.model.OrderModel;

import de.hybris.platform.servicelayer.search.FlexibleSearchQuery;
import de.hybris.platform.servicelayer.search.FlexibleSearchService;
import de.hybris.platform.servicelayer.search.SearchResult;

import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Data-access object for {@link OrderModel}.
 *
 * <p>Every lookup is expressed as a parameterised FlexibleSearch query — inputs are always
 * bound as parameters, never concatenated into the query string. This is a straight
 * read layer: no business logic lives here.</p>
 */
public class OrderDao
{
	private FlexibleSearchService flexibleSearchService;

	/**
	 * Finds the single order that owns a given business code.
	 *
	 * @param code the unique order code (e.g. "ORD-1001")
	 * @return the matching order, or {@code null} when no order has that code
	 */
	public OrderModel findByCode(final String code)
	{
		final String qs = "SELECT {pk} FROM {Order} WHERE {code} = ?code";
		final FlexibleSearchQuery query = new FlexibleSearchQuery(qs);
		query.addQueryParameter("code", code);

		final SearchResult<OrderModel> result = flexibleSearchService.search(query);
		final List<OrderModel> orders = result.getResult();
		return orders.isEmpty() ? null : orders.get(0);
	}

	/**
	 * Returns every order currently in the given status, newest first.
	 *
	 * @param status the status to filter on
	 * @return orders in that status, ordered by order date descending (never {@code null})
	 */
	public List<OrderModel> findByStatus(final OrderStatus status)
	{
		final String qs = "SELECT {pk} FROM {Order} WHERE {status} = ?status ORDER BY {orderDate} DESC";
		final FlexibleSearchQuery query = new FlexibleSearchQuery(qs);
		query.addQueryParameter("status", status);

		return flexibleSearchService.<OrderModel> search(query).getResult();
	}

	/**
	 * Finds unpaid orders that are still {@link OrderStatus#NEW} and were placed before the cutoff.
	 * Used by the nightly cleanup job to cancel abandoned orders.
	 *
	 * @param cutoff orders placed strictly before this date are considered stale
	 * @return the stale, unpaid, still-new orders (never {@code null})
	 */
	public List<OrderModel> findStaleUnpaidOrders(final Date cutoff)
	{
		final String qs = "SELECT {pk} FROM {Order} "
				+ "WHERE {paid} = ?paid AND {status} = ?status AND {orderDate} < ?cutoff";

		final Map<String, Object> params = new HashMap<>();
		params.put("paid", Boolean.FALSE);
		params.put("status", OrderStatus.NEW);
		params.put("cutoff", cutoff);

		final FlexibleSearchQuery query = new FlexibleSearchQuery(qs, params);
		return flexibleSearchService.<OrderModel> search(query).getResult();
	}

	/**
	 * Returns orders at or above a given fulfilment priority. Higher numbers ship first.
	 *
	 * @param minPriority the inclusive lower bound on priority
	 * @return matching orders, highest priority first (never {@code null})
	 */
	public List<OrderModel> findByMinimumPriority(final int minPriority)
	{
		final String qs = "SELECT {pk} FROM {Order} WHERE {priority} >= ?minPriority ORDER BY {priority} DESC";
		final FlexibleSearchQuery query = new FlexibleSearchQuery(qs);
		query.addQueryParameter("minPriority", Integer.valueOf(minPriority));

		return flexibleSearchService.<OrderModel> search(query).getResult();
	}

	public void setFlexibleSearchService(final FlexibleSearchService flexibleSearchService)
	{
		this.flexibleSearchService = flexibleSearchService;
	}
}
