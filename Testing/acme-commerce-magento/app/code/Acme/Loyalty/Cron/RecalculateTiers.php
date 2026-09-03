<?php
declare(strict_types=1);

namespace Acme\Loyalty\Cron;

use Magento\Framework\ObjectManagerInterface;

class RecalculateTiers
{
    private ObjectManagerInterface $objectManager;

    public function __construct(ObjectManagerInterface $objectManager)
    {
        $this->objectManager = $objectManager;
    }

    public function execute(): void
    {
        // Direct ObjectManager use — the dependency is hidden from the constructor.
        $repository = $this->objectManager->get(\Acme\Loyalty\Model\AccountRepository::class);
        foreach ($repository->getAll() as $account) {
            $spend = $account->getData('lifetime_spend');
            $account->setData('tier', $spend >= 5000 ? 'GOLD' : ($spend >= 1000 ? 'SILVER' : 'NONE'));
            $repository->save($account);
        }
    }
}
