<?php
declare(strict_types=1);

namespace Acme\Loyalty\Observer;

use Acme\Loyalty\Api\LoyaltyAccountRepositoryInterface;
use Magento\Framework\Event\Observer;
use Magento\Framework\Event\ObserverInterface;

/**
 * A refund takes back the points the order earned.
 *
 * Points already spent are not clawed back below zero — the balance floors at zero and
 * the shortfall is written off, because a negative loyalty balance is a support call and
 * the amounts never justify one.
 */
class ReversePointsObserver implements ObserverInterface
{
    private LoyaltyAccountRepositoryInterface $accounts;

    public function __construct(LoyaltyAccountRepositoryInterface $accounts)
    {
        $this->accounts = $accounts;
    }

    public function execute(Observer $observer)
    {
        $creditmemo = $observer->getEvent()->getData('creditmemo');
        if ($creditmemo === null) {
            return;
        }
        $order = $creditmemo->getOrder();
        $code = (string) $order->getData('acme_loyalty_code');
        if ($code === '') {
            return;
        }
        $earned = (int) $order->getData('acme_points_earned');
        $account = $this->accounts->getByCode($code);
        $reversal = min($earned, $account->getPointsBalance());
        $this->accounts->addPoints($code, -$reversal, 'REFUND');
    }
}
