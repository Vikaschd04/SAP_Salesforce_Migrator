<?php
declare(strict_types=1);

namespace Acme\Loyalty\Model\ResourceModel;

use Magento\Framework\Model\ResourceModel\Db\AbstractDb;

class LoyaltyAccount extends AbstractDb
{
    protected function _construct()
    {
        $this->_init('acme_loyalty_account', 'entity_id');
    }

    /**
     * Points are incremented in SQL rather than read-modify-write, because two orders
     * placed in the same second would otherwise each read the old balance and the second
     * would overwrite the first's award. Losing points is a support ticket; the fix is
     * to never hold the value in PHP.
     */
    public function incrementPoints(int $accountId, int $delta): void
    {
        $connection = $this->getConnection();
        $connection->update(
            $this->getMainTable(),
            ['points_balance' => new \Zend_Db_Expr('points_balance + ' . (int) $delta)],
            ['entity_id = ?' => $accountId]
        );
    }
}
