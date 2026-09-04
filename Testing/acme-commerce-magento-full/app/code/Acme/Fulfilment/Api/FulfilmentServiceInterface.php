<?php
declare(strict_types=1);

namespace Acme\Fulfilment\Api;

interface FulfilmentServiceInterface
{
    /**
     * @throws \Magento\Framework\Exception\LocalizedException when the transition is illegal
     */
    public function transition(string $orderIncrementId, string $targetState): void;

    public function currentState(string $orderIncrementId): string;
}
