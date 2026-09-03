<?php
declare(strict_types=1);

namespace Acme\Loyalty\Observer;

use Magento\Framework\Event\Observer;
use Magento\Framework\Event\ObserverInterface;
use Magento\Framework\App\ResourceConnection;

class TierCheckObserver implements ObserverInterface
{
    private ResourceConnection $resource;

    public function __construct(ResourceConnection $resource)
    {
        $this->resource = $resource;
    }

    public function execute(Observer $observer)
    {
        $quote = $observer->getEvent()->getData('quote');
        $items = $quote === null ? [] : $quote->getAllVisibleItems();

        // A query per item: fine on a page with three products, not on a bulk import.
        foreach ($items as $item) {
            $connection = $this->resource->getConnection();
            $select = $connection->select()
                ->from('acme_loyalty_account')
                ->where('customer_id = ?', (int) $item->getData('customer_id'));
            $connection->fetchRow($select);
        }
    }
}
