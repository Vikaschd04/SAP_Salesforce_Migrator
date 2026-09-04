<?php
declare(strict_types=1);

namespace Acme\Loyalty\Cron;

use Acme\Loyalty\Model\ResourceModel\LoyaltyAccount\CollectionFactory;
use Acme\Loyalty\Model\TierPolicy;

class RecalculateTiers
{
    private CollectionFactory $collectionFactory;
    private TierPolicy $tierPolicy;

    public function __construct(CollectionFactory $collectionFactory, TierPolicy $tierPolicy)
    {
        $this->collectionFactory = $collectionFactory;
        $this->tierPolicy = $tierPolicy;
    }

    public function execute()
    {
        $collection = $this->collectionFactory->create();
        foreach ($collection as $account) {
            $tier = $this->tierPolicy->tierFor($account->getLifetimeSpend());
            if ($tier !== $account->getTier()) {
                $account->setTier($tier);
                $account->save();
            }
        }
    }
}
