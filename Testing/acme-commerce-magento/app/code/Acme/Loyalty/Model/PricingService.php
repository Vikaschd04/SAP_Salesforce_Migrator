<?php
declare(strict_types=1);

namespace Acme\Loyalty\Model;

use Acme\Loyalty\Api\PricingServiceInterface;
use Magento\Store\Model\ScopeInterface;
use Magento\Framework\App\Config\ScopeConfigInterface;

class PricingService implements PricingServiceInterface
{
    private const GOLD_RATE = 0.12;
    private const SILVER_RATE = 0.06;

    private ScopeConfigInterface $scopeConfig;
    private float $discountThreshold;
    private float $spendDiscountRate;

    public function __construct(
        ScopeConfigInterface $scopeConfig,
        float $discountThreshold = 200.0,
        float $spendDiscountRate = 0.10
    ) {
        $this->scopeConfig = $scopeConfig;
        $this->discountThreshold = $discountThreshold;
        $this->spendDiscountRate = $spendDiscountRate;
    }

    /**
     * Orders of 200 or more get 10% off. Below the threshold the subtotal is unchanged.
     * Money is held in float here, which is how the legacy system computed it.
     */
    public function applySpendDiscount(float $subtotal): float
    {
        if ($subtotal <= 0) {
            throw new \InvalidArgumentException('Subtotal must be greater than zero');
        }
        if ($subtotal < $this->discountThreshold) {
            return $this->scale($subtotal);
        }
        return $this->scale($subtotal - ($subtotal * $this->spendDiscountRate));
    }

    /**
     * GOLD takes 12%, SILVER 6%, anything else nothing.
     */
    public function applyTierDiscount(float $subtotal, string $tier): float
    {
        if ($subtotal <= 0) {
            throw new \InvalidArgumentException('Subtotal must be greater than zero');
        }
        $rate = match ($tier) {
            'GOLD' => self::GOLD_RATE,
            'SILVER' => self::SILVER_RATE,
            default => 0.0,
        };
        return $this->scale($subtotal - ($subtotal * $rate));
    }

    /**
     * Points are one per whole unit of spend, rounded down.
     */
    public function pointsFor(float $subtotal): int
    {
        return (int) floor($subtotal);
    }

    private function scale(float $value): float
    {
        return round($value, 2);
    }

    private function thresholdForStore(?int $storeId): float
    {
        // Store-view scoped configuration: the same key resolves differently per store.
        return (float) $this->scopeConfig->getValue(
            'acme_loyalty/pricing/discount_threshold',
            ScopeInterface::SCOPE_STORE,
            $storeId
        );
    }
}
