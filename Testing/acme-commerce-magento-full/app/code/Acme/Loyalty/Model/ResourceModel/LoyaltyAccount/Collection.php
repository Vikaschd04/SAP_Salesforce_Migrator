<?php
declare(strict_types=1);

namespace Acme\Loyalty\Model\ResourceModel\LoyaltyAccount;

use Magento\Framework\Model\ResourceModel\Db\Collection\AbstractCollection;

class Collection extends AbstractCollection
{
    protected function _construct()
    {
        $this->_init(
            \Acme\Loyalty\Model\LoyaltyAccount::class,
            \Acme\Loyalty\Model\ResourceModel\LoyaltyAccount::class
        );
    }

    public function addTierFilter(string $tier): self
    {
        $this->addFieldToFilter('tier', $tier);
        return $this;
    }

    public function addSpendAbove(float $amount): self
    {
        $this->addFieldToFilter('lifetime_spend', ['gteq' => $amount]);
        return $this;
    }
}
