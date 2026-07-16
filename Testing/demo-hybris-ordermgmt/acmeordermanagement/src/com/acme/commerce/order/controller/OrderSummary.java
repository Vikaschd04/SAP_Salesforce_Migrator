package com.acme.commerce.order.controller;

import java.math.BigDecimal;

/**
 * Lightweight, serialisable view of an order returned by {@link OrderController}.
 * Exposes only the fields a client needs, keeping the domain model off the wire.
 */
public class OrderSummary
{
	private String code;
	private String status;
	private BigDecimal totalAmount;
	private boolean expedited;

	public String getCode()
	{
		return code;
	}

	public void setCode(final String code)
	{
		this.code = code;
	}

	public String getStatus()
	{
		return status;
	}

	public void setStatus(final String status)
	{
		this.status = status;
	}

	public BigDecimal getTotalAmount()
	{
		return totalAmount;
	}

	public void setTotalAmount(final BigDecimal totalAmount)
	{
		this.totalAmount = totalAmount;
	}

	public boolean isExpedited()
	{
		return expedited;
	}

	public void setExpedited(final boolean expedited)
	{
		this.expedited = expedited;
	}
}
