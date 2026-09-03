<?php
declare(strict_types=1);

namespace Acme\Loyalty\Observer;

use Magento\Framework\Event\Observer;
use Magento\Framework\Event\ObserverInterface;
use Acme\Loyalty\Api\PricingServiceInterface;

class AwardPointsObserver implements ObserverInterface
{
    private PricingServiceInterface $pricing;

    public function __construct(PricingServiceInterface $pricing)
    {
        $this->pricing = $pricing;
    }

    /**
     * Awards one point per whole unit of spend, and writes the result back onto the
     * order carried by the event — the observer mutates the payload in place, and
     * later observers on the same event see the change.
     */
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
