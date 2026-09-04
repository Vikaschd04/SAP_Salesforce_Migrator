<?php
declare(strict_types=1);

namespace Acme\Fulfilment\Model\ResourceModel;

use Magento\Framework\Model\ResourceModel\Db\AbstractDb;

class FulfilmentEvent extends AbstractDb
{
    protected function _construct()
    {
        $this->_init('acme_fulfilment_event', 'event_id');
    }

    public function append(string $orderIncrementId, string $state, ?string $warehouse = null): void
    {
        $this->getConnection()->insert($this->getMainTable(), [
            'order_increment_id' => $orderIncrementId,
            'state' => $state,
            'warehouse_code' => $warehouse,
        ]);
    }

    public function latestState(string $orderIncrementId): ?string
    {
        $connection = $this->getConnection();
        $select = $connection->select()
            ->from($this->getMainTable(), ['state'])
            ->where('order_increment_id = ?', $orderIncrementId)
            ->order('occurred_at DESC')
            ->limit(1);
        $state = $connection->fetchOne($select);
        return $state === false ? null : (string) $state;
    }
}
