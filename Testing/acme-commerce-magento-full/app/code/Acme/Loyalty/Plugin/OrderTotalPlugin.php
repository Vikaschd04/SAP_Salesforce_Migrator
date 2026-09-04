<?php
declare(strict_types=1);

namespace Acme\Loyalty\Plugin;

use Acme\Loyalty\Api\PricingServiceInterface;

/**
 * An `around` plugin that can decline to call the original.
 *
 * When the order already carries a locked total — set by the payment provider at
 * authorisation — recalculating it would produce a figure that disagrees with what the
 * shopper was charged. So this returns the stored value and never proceeds.
 */
class OrderTotalPlugin
{
    private PricingServiceInterface $pricing;

    public function __construct(PricingServiceInterface $pricing)
    {
        $this->pricing = $pricing;
    }

    public function aroundGetGrandTotal($subject, callable $proceed)
    {
        $locked = $subject->getData('acme_total_locked');
        if ($locked !== null && (float) $locked > 0.0) {
            return (float) $locked;
        }
        return $proceed();
    }
}
