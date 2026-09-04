<?php
declare(strict_types=1);

namespace Acme\Loyalty\Api;

interface PricingServiceInterface
{
    public function applySpendDiscount(float $subtotal, float $lifetimeSpend, ?int $storeId = null): float;

    public function applyTierDiscount(float $subtotal, string $tier, ?int $storeId = null): float;

    public function pointsFor(float $orderTotal): int;
}
