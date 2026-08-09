package com.acme.occ.controllers;

import de.hybris.platform.core.model.order.OrderModel;
import de.hybris.platform.webservicescommons.errors.exceptions.WebserviceValidationException;

import com.acme.core.data.PricingBreakdownData;
import com.acme.core.dao.OrderDao;
import com.acme.facades.pricing.PricingFacade;

import javax.annotation.Resource;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * OCC endpoints for the price panel.
 */
@RestController
@RequestMapping(value = "/{baseSiteId}/pricing")
public class PricingController
{
	@Resource(name = "acmePricingFacade")
	private PricingFacade pricingFacade;

	@Resource(name = "acmeOrderDao")
	private OrderDao orderDao;

	@RequestMapping(value = "/orders/{code}/breakdown", method = RequestMethod.GET,
			produces = MediaType.APPLICATION_JSON_VALUE)
	@ResponseBody
	public PricingBreakdownData getBreakdown(@PathVariable final String code)
	{
		final OrderModel order = orderDao.findByCode(code);
		if (order == null)
		{
			throw new WebserviceValidationException("No order for code " + code);
		}
		return pricingFacade.getBreakdown(order);
	}

	@RequestMapping(value = "/quote", method = RequestMethod.GET,
			produces = MediaType.APPLICATION_JSON_VALUE)
	@ResponseBody
	public PricingBreakdownData quote(@RequestParam final String orderCode,
			@RequestParam(required = false) final String promoCode)
	{
		final OrderModel order = orderDao.findByCode(orderCode);
		if (order == null)
		{
			throw new WebserviceValidationException("No order for code " + orderCode);
		}
		if (promoCode != null)
		{
			order.setAppliedPromoCode(promoCode);
		}
		return pricingFacade.getBreakdown(order);
	}
}
