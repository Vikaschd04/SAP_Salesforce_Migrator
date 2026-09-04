<?php
declare(strict_types=1);

namespace Acme\Loyalty\Model;

/**
 * Which tier a lifetime spend earns.
 *
 * The thresholds are configuration, not constants: marketing changes them at least once
 * a year and a deploy should not be needed for it.
 */
class TierPolicy
{
    public const NONE = 'NONE';

    private array $tiers;

    public function __construct(array $tiers = [])
    {
        $this->tiers = $tiers;
        arsort($this->tiers);
    }

    public function tierFor(float $lifetimeSpend): string
    {
        foreach ($this->tiers as $tier => $threshold) {
            if ($lifetimeSpend >= (float) $threshold) {
                return (string) $tier;
            }
        }
        return self::NONE;
    }

    /** Discount percentage attached to a tier. Zero for an unknown tier, never an error. */
    public function discountPercentFor(string $tier): float
    {
        $map = ['BRONZE' => 0.0, 'SILVER' => 2.5, 'GOLD' => 5.0];
        return $map[$tier] ?? 0.0;
    }
}
