<?php
declare(strict_types=1);

namespace Acme\Loyalty\Plugin;

use Acme\Loyalty\Api\PricingServiceInterface;

/**
 * Adjusts the arguments and always proceeds — a `before` plugin in Magento's terms.
 */
class SubtotalPlugin
{
    private PricingServiceInterface $pricing;

    public function __construct(PricingServiceInterface $pricing)
    {
        $this->pricing = $pricing;
    }

    public function beforeCollect($subject, $quote, $shippingAssignment, $total)
    {
        return [$quote, $shippingAssignment, $total];
    }
}
