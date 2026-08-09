package com.acme.core.dao.impl;

import de.hybris.platform.core.model.order.OrderModel;
import de.hybris.platform.core.model.user.CustomerModel;
import de.hybris.platform.servicelayer.search.FlexibleSearchQuery;
import de.hybris.platform.servicelayer.search.FlexibleSearchService;
import de.hybris.platform.servicelayer.search.SearchResult;

import com.acme.core.dao.OrderDao;
import com.acme.core.enums.FulfilmentState;

import java.util.Collections;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.apache.log4j.Logger;

/**
 * FlexibleSearch-backed implementation of {@link OrderDao}.
 */
public class DefaultOrderDao implements OrderDao
{
	private static final Logger LOG = Logger.getLogger(DefaultOrderDao.class);

	private static final String BY_CODE = "SELECT {o:pk} FROM {Order AS o} WHERE {o:code} = ?code";
	private static final String BY_STATE = "SELECT {o:pk} FROM {Order AS o} WHERE {o:fulfilmentState} = ?state";
	private static final String BY_CUSTOMER = "SELECT {o:pk} FROM {Order AS o} WHERE {o:user} = ?customer ORDER BY {o:creationtime} DESC";
	private static final String PLACED_BETWEEN =
			"SELECT {o:pk} FROM {Order AS o} WHERE {o:date} >= ?from AND {o:date} <= ?to";
	private static final String STALE_CARTS =
			"SELECT {c:pk} FROM {Cart AS c} WHERE {c:modifiedtime} < ?olderThan";

	private FlexibleSearchService flexibleSearchService;

	@Override
	public OrderModel findByCode(final String code)
	{
		if (code == null || code.trim().isEmpty())
		{
			throw new IllegalArgumentException("Order code must not be blank");
		}
		final FlexibleSearchQuery query = new FlexibleSearchQuery(BY_CODE);
		query.addQueryParameter("code", code);
		final SearchResult<OrderModel> result = flexibleSearchService.search(query);
		return result.getCount() == 0 ? null : result.getResult().get(0);
	}

	@Override
	public List<OrderModel> findByState(final FulfilmentState state)
	{
		final FlexibleSearchQuery query = new FlexibleSearchQuery(BY_STATE);
		query.addQueryParameter("state", state);
		return flexibleSearchService.<OrderModel> search(query).getResult();
	}

	@Override
	public List<OrderModel> findByCustomer(final CustomerModel customer)
	{
		if (customer == null)
		{
			return Collections.emptyList();
		}
		final FlexibleSearchQuery query = new FlexibleSearchQuery(BY_CUSTOMER);
		query.addQueryParameter("customer", customer);
		return flexibleSearchService.<OrderModel> search(query).getResult();
	}

	@Override
	public List<OrderModel> findPlacedBetween(final Date from, final Date to)
	{
		final Map<String, Object> params = new HashMap<String, Object>();
		params.put("from", from);
		params.put("to", to);
		final FlexibleSearchQuery query = new FlexibleSearchQuery(PLACED_BETWEEN, params);
		return flexibleSearchService.<OrderModel> search(query).getResult();
	}

	@Override
	public List<OrderModel> findStaleCarts(final Date olderThan, final int max)
	{
		final FlexibleSearchQuery query = new FlexibleSearchQuery(STALE_CARTS);
		query.addQueryParameter("olderThan", olderThan);
		query.setCount(max);
		LOG.debug("Looking for carts older than " + olderThan);
		return flexibleSearchService.<OrderModel> search(query).getResult();
	}

	public void setFlexibleSearchService(final FlexibleSearchService flexibleSearchService)
	{
		this.flexibleSearchService = flexibleSearchService;
	}
}
