<?php
declare(strict_types=1);

namespace Acme\Loyalty\Model;

use Acme\Core\Helper\Money;
use Acme\Loyalty\Api\PricingServiceInterface;

/**
 * The order of subtraction here is the business rule, not an implementation detail.
 *
 * Spend discount first, then tier, then any promo code — because each is calculated on
 * the *running* subtotal, so reordering them changes what the shopper pays. Finance
 * signed off this sequence against the 2024 promotion terms.
 */
class PricingService implements PricingServiceInterface
{
    private Money $money;
    private TierPolicy $tierPolicy;
    private float $discountThreshold;
    private float $spendDiscountRate;

    public function __construct(
        Money $money,
        TierPolicy $tierPolicy,
        float $discountThreshold = 200.0,
        float $spendDiscountRate = 0.10
    ) {
        $this->money = $money;
        $this->tierPolicy = $tierPolicy;
        $this->discountThreshold = $discountThreshold;
        $this->spendDiscountRate = $spendDiscountRate;
    }

    /**
     * A shopper past the lifetime-spend threshold gets a flat rate off. The threshold is
     * inclusive: exactly 200 qualifies, which is what the terms say and what the tests
     * pin.
     */
    public function applySpendDiscount(float $subtotal, float $lifetimeSpend, ?int $storeId = null): float
    {
        if ($lifetimeSpend < $this->discountThreshold) {
            return $subtotal;
        }
        $discount = $this->money->percentageOf($subtotal, $this->spendDiscountRate * 100);
        return $subtotal - $discount;
    }

    public function applyTierDiscount(float $subtotal, string $tier, ?int $storeId = null): float
    {
        $percent = $this->tierPolicy->discountPercentFor($tier);
        if ($percent <= 0.0) {
            return $subtotal;
        }
        return $subtotal - $this->money->percentageOf($subtotal, $percent);
    }

    /**
     * One point per whole unit of spend. Truncated, never rounded: awarding a point for
     * 0.6 of a unit is the kind of generosity that compounds across a million orders.
     */
    public function pointsFor(float $orderTotal): int
    {
        return (int) floor($orderTotal);
    }
}
