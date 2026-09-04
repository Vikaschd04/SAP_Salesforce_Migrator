<?php
declare(strict_types=1);

namespace Acme\Loyalty\Observer;

use Acme\Loyalty\Model\TierPolicy;
use Magento\Framework\Event\Observer;
use Magento\Framework\Event\ObserverInterface;

class TierCheckObserver implements ObserverInterface
{
    private TierPolicy $tierPolicy;

    public function __construct(TierPolicy $tierPolicy)
    {
        $this->tierPolicy = $tierPolicy;
    }

    public function execute(Observer $observer)
    {
        $quote = $observer->getEvent()->getData('quote');
        if ($quote === null) {
            return;
        }
        $spend = (float) $quote->getData('acme_lifetime_spend');
        $quote->setData('acme_loyalty_tier', $this->tierPolicy->tierFor($spend));
    }
}
