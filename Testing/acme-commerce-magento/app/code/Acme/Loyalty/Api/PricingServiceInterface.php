<?php
declare(strict_types=1);

namespace Acme\Loyalty\Api;

interface PricingServiceInterface
{
    /**
     * Apply the spend-based discount. Orders at or above the threshold get 10% off.
     */
    public function applySpendDiscount(float $subtotal): float;

    /**
     * Apply the tier discount for a loyalty tier: GOLD 12%, SILVER 6%, otherwise none.
     */
    public function applyTierDiscount(float $subtotal, string $tier): float;
}
