package com.acme.core.session;

import java.io.Serializable;
import java.math.BigDecimal;

/**
 * Session-scoped checkout state. Holds the promo code the shopper typed and a running
 * total between requests.
 */
public class CheckoutContext implements Serializable
{
	private static final long serialVersionUID = 1L;

	private String appliedPromoCode;
	private BigDecimal runningTotal = BigDecimal.ZERO;
	private String deliveryWarehouse;

	public String getAppliedPromoCode() { return appliedPromoCode; }
	public void setAppliedPromoCode(final String code) { this.appliedPromoCode = code; }
	public BigDecimal getRunningTotal() { return runningTotal; }
	public void setRunningTotal(final BigDecimal total) { this.runningTotal = total; }
	public String getDeliveryWarehouse() { return deliveryWarehouse; }
	public void setDeliveryWarehouse(final String w) { this.deliveryWarehouse = w; }

	public void reset()
	{
		appliedPromoCode = null;
		runningTotal = BigDecimal.ZERO;
		deliveryWarehouse = null;
	}
}
