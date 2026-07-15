package com.store.promotion;

import java.math.BigDecimal;

/**
 * Promotion / discount pricing. This is exactly the kind of logic the Planner
 * should flag as a better fit for a native Salesforce product (CPQ) than for
 * hand-written Apex.
 */
public class DefaultPromotionService {

    /** Business rule: orders over 100 get a 10% discount. */
    public BigDecimal applyDiscount(BigDecimal orderTotal) {
        if (orderTotal.compareTo(new BigDecimal("100")) > 0) {
            return orderTotal.multiply(new BigDecimal("0.90"));
        }
        return orderTotal;
    }

    /** Business rule: a promo code of BOGO halves the total. */
    public BigDecimal applyPromoCode(BigDecimal orderTotal, String promoCode) {
        if ("BOGO".equals(promoCode)) {
            return orderTotal.multiply(new BigDecimal("0.50"));
        }
        return orderTotal;
    }
}
