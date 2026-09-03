<?php
declare(strict_types=1);

namespace Acme\Loyalty\Plugin;

use Magento\Sales\Model\Order;

class OrderTotalPlugin
{
    /**
     * An `around` plugin. When the order is already fully covered by loyalty points
     * the original method is NOT called at all — $proceed is skipped and a fixed
     * value is returned in its place.
     */
    public function aroundGetGrandTotal(Order $subject, callable $proceed)
    {
        if ((int) $subject->getData('acme_points_applied') > 0
            && (float) $subject->getData('acme_points_value') >= (float) $subject->getData('subtotal')) {
            return 0.0;
        }
        return $proceed();
    }

    public function afterGetCustomerNote(Order $subject, $result)
    {
        $tier = $subject->getData('acme_loyalty_tier');
        return $tier ? trim($result . ' [' . $tier . ']') : $result;
    }
}
