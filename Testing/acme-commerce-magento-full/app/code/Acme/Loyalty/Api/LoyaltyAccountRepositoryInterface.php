<?php
declare(strict_types=1);

namespace Acme\Loyalty\Api;

use Acme\Loyalty\Api\Data\LoyaltyAccountInterface;

interface LoyaltyAccountRepositoryInterface
{
    /**
     * @throws \Magento\Framework\Exception\NoSuchEntityException
     */
    public function getByCode(string $code): LoyaltyAccountInterface;

    public function getForCurrentCustomer(): LoyaltyAccountInterface;

    public function addPoints(string $code, int $points, string $reason): LoyaltyAccountInterface;

    public function save(LoyaltyAccountInterface $account): LoyaltyAccountInterface;
}
