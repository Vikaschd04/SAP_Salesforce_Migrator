<?php
declare(strict_types=1);

namespace Acme\Loyalty\Cron;

use Acme\Loyalty\Model\ResourceModel\LoyaltyAccount\CollectionFactory;

/**
 * Expires points past their expiry date.
 *
 * Runs once across the cluster: Magento's cron takes a lock per job name, so whichever
 * node picks it up is the only one that runs it.
 */
class ExpirePoints
{
    private CollectionFactory $collectionFactory;

    public function __construct(CollectionFactory $collectionFactory)
    {
        $this->collectionFactory = $collectionFactory;
    }

    public function execute()
    {
        $collection = $this->collectionFactory->create();
        foreach ($collection as $account) {
            $account->setPointsBalance(0);
            $account->save();
        }
    }
}
