<?php
declare(strict_types=1);

namespace Acme\Loyalty\Observer;

use Acme\Loyalty\Api\PricingServiceInterface;
use Magento\Framework\Event\Observer;
use Magento\Framework\Event\ObserverInterface;

/**
 * Awards points and writes the result back onto the order carried by the event.
 *
 * The observer mutates the payload in place, and the observer registered after it on the
 * same event reads the changed value. That ordering is load-bearing.
 */
class AwardPointsObserver implements ObserverInterface
{
    private PricingServiceInterface $pricing;

    public function __construct(PricingServiceInterface $pricing)
    {
        $this->pricing = $pricing;
    }

    public function execute(Observer $observer)
    {
        $order = $observer->getEvent()->getData('order');
        if ($order === null) {
            return;
        }
        $points = $this->pricing->pointsFor((float) $order->getData('grand_total'));
        $order->setData('acme_points_earned', $points);
    }
}
