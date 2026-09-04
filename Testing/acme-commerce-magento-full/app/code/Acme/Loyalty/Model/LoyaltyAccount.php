<?php
declare(strict_types=1);

namespace Acme\Loyalty\Model;

use Acme\Loyalty\Api\Data\LoyaltyAccountInterface;
use Magento\Framework\Model\AbstractModel;

class LoyaltyAccount extends AbstractModel implements LoyaltyAccountInterface
{
    protected function _construct()
    {
        $this->_init(\Acme\Loyalty\Model\ResourceModel\LoyaltyAccount::class);
    }

    public function getCode(): string
    {
        return (string) $this->getData(self::CODE);
    }

    public function setCode(string $code): LoyaltyAccountInterface
    {
        $this->setData(self::CODE, $code);
        return $this;
    }

    public function getTier(): string
    {
        return (string) $this->getData(self::TIER);
    }

    public function setTier(string $tier): LoyaltyAccountInterface
    {
        $this->setData(self::TIER, $tier);
        return $this;
    }

    public function getPointsBalance(): int
    {
        return (int) $this->getData(self::POINTS_BALANCE);
    }

    public function setPointsBalance(int $points): LoyaltyAccountInterface
    {
        $this->setData(self::POINTS_BALANCE, $points);
        return $this;
    }

    public function getLifetimeSpend(): float
    {
        return (float) $this->getData('lifetime_spend');
    }
}
