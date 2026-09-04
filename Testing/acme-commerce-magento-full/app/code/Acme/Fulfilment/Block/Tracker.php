<?php
declare(strict_types=1);

namespace Acme\Fulfilment\Block;

use Acme\Fulfilment\Api\FulfilmentServiceInterface;
use Magento\Framework\View\Element\Template;

class Tracker extends Template
{
    private FulfilmentServiceInterface $fulfilment;

    public function __construct(
        Template\Context $context,
        FulfilmentServiceInterface $fulfilment,
        array $data = []
    ) {
        parent::__construct($context, $data);
        $this->fulfilment = $fulfilment;
    }

    public function getCurrentState(): string
    {
        return $this->fulfilment->currentState((string) $this->getData('order_increment_id'));
    }

    public function getSteps(): array
    {
        return ['PENDING', 'ALLOCATED', 'PICKED', 'SHIPPED', 'DELIVERED'];
    }
}
