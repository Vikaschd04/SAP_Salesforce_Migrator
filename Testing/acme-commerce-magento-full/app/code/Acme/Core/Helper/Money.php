<?php
declare(strict_types=1);

namespace Acme\Core\Helper;

use Acme\Core\Api\StoreConfigInterface;

/**
 * Every monetary rounding in the suite goes through here.
 *
 * The rule Acme finance signed off: round half up, at the store's configured scale, and
 * round only once at the end of a calculation. Rounding intermediate values compounds a
 * half-cent per step and the totals stop reconciling with the payment provider.
 */
class Money
{
    private StoreConfigInterface $config;

    public function __construct(StoreConfigInterface $config)
    {
        $this->config = $config;
    }

    public function round(float $amount, ?int $storeId = null): float
    {
        $scale = $this->config->currencyScale($storeId);
        return round($amount, $scale, PHP_ROUND_HALF_UP);
    }

    public function percentageOf(float $amount, float $percent): float
    {
        return $amount * ($percent / 100.0);
    }

    /**
     * Splits an amount across n lines so the parts sum exactly to the whole. The last
     * line absorbs the remainder; without this a 3-way split of 10.00 loses a cent.
     */
    public function allocate(float $amount, int $parts, ?int $storeId = null): array
    {
        if ($parts < 1) {
            return [];
        }
        $each = $this->round($amount / $parts, $storeId);
        $out = array_fill(0, $parts - 1, $each);
        $out[] = $this->round($amount - ($each * ($parts - 1)), $storeId);
        return $out;
    }
}
