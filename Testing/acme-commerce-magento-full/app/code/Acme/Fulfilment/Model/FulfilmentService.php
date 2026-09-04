<?php
declare(strict_types=1);

namespace Acme\Fulfilment\Model;

use Acme\Fulfilment\Api\FulfilmentServiceInterface;
use Magento\Framework\Exception\LocalizedException;

/**
 * The fulfilment state machine.
 *
 * Transitions are one-way and skipping is not allowed: an order cannot go from ALLOCATED
 * straight to DELIVERED, because the warehouse's own scan events are what move it and a
 * gap means a scan was missed. CANCELLED is reachable from anywhere before SHIPPED.
 */
class FulfilmentService implements FulfilmentServiceInterface
{
    private const ORDER = ['PENDING', 'ALLOCATED', 'PICKED', 'SHIPPED', 'DELIVERED'];

    private ResourceModel\FulfilmentEvent $resource;

    public function __construct(ResourceModel\FulfilmentEvent $resource)
    {
        $this->resource = $resource;
    }

    public function transition(string $orderIncrementId, string $targetState): void
    {
        $current = $this->currentState($orderIncrementId);

        if ($targetState === 'CANCELLED') {
            if ($this->indexOf($current) >= $this->indexOf('SHIPPED')) {
                throw new LocalizedException(__('A shipped order cannot be cancelled'));
            }
            $this->resource->append($orderIncrementId, 'CANCELLED');
            return;
        }

        if ($this->indexOf($targetState) !== $this->indexOf($current) + 1) {
            throw new LocalizedException(
                __('Illegal transition from %1 to %2', $current, $targetState)
            );
        }

        $this->resource->append($orderIncrementId, $targetState);
    }

    public function currentState(string $orderIncrementId): string
    {
        return $this->resource->latestState($orderIncrementId) ?? 'PENDING';
    }

    private function indexOf(string $state): int
    {
        $i = array_search($state, self::ORDER, true);
        return $i === false ? -1 : (int) $i;
    }
}
