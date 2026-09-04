<?php
declare(strict_types=1);

namespace Acme\Loyalty\Model;

use Acme\Loyalty\Api\Data\LoyaltyAccountInterface;
use Acme\Loyalty\Api\LoyaltyAccountRepositoryInterface;
use Acme\Loyalty\Model\ResourceModel\LoyaltyAccount as LoyaltyAccountResource;
use Magento\Framework\Exception\NoSuchEntityException;

class LoyaltyAccountRepository implements LoyaltyAccountRepositoryInterface
{
    private LoyaltyAccountFactory $accountFactory;
    private LoyaltyAccountResource $resource;
    private \Magento\Customer\Model\Session $customerSession;

    public function __construct(
        LoyaltyAccountFactory $accountFactory,
        LoyaltyAccountResource $resource,
        \Magento\Customer\Model\Session $customerSession
    ) {
        $this->accountFactory = $accountFactory;
        $this->resource = $resource;
        $this->customerSession = $customerSession;
    }

    public function getByCode(string $code): LoyaltyAccountInterface
    {
        $account = $this->accountFactory->create();
        $this->resource->load($account, $code, 'code');
        if (!$account->getId()) {
            throw new NoSuchEntityException(__('No loyalty account with code %1', $code));
        }
        return $account;
    }

    /**
     * Reads the logged-in customer from the session. This is the only method here that
     * depends on there *being* a session, which is why webapi.xml exposes it under
     * `self` rather than an ACL resource.
     */
    public function getForCurrentCustomer(): LoyaltyAccountInterface
    {
        $customerId = (int) $this->customerSession->getCustomerId();
        $account = $this->accountFactory->create();
        $this->resource->load($account, $customerId, 'customer_id');
        if (!$account->getId()) {
            throw new NoSuchEntityException(__('No loyalty account for the current customer'));
        }
        return $account;
    }

    public function addPoints(string $code, int $points, string $reason): LoyaltyAccountInterface
    {
        $account = $this->getByCode($code);
        $this->resource->incrementPoints((int) $account->getId(), $points);
        $this->resource->load($account, (int) $account->getId());
        return $account;
    }

    public function save(LoyaltyAccountInterface $account): LoyaltyAccountInterface
    {
        $this->resource->save($account);
        return $account;
    }
}
