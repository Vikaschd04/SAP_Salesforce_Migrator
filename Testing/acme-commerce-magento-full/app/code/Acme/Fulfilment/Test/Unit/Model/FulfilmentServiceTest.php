<?php
declare(strict_types=1);

namespace Acme\Fulfilment\Test\Unit\Model;

use Acme\Fulfilment\Model\FulfilmentService;
use Acme\Fulfilment\Model\ResourceModel\FulfilmentEvent;
use Magento\Framework\Exception\LocalizedException;
use PHPUnit\Framework\TestCase;

class FulfilmentServiceTest extends TestCase
{
    public function testAStepForwardIsAllowed(): void
    {
        $resource = $this->createMock(FulfilmentEvent::class);
        $resource->method('latestState')->willReturn('PENDING');
        $resource->expects(self::once())->method('append')->with('X1', 'ALLOCATED');

        (new FulfilmentService($resource))->transition('X1', 'ALLOCATED');
    }

    public function testSkippingAStateIsRejected(): void
    {
        $resource = $this->createMock(FulfilmentEvent::class);
        $resource->method('latestState')->willReturn('ALLOCATED');

        $this->expectException(LocalizedException::class);
        (new FulfilmentService($resource))->transition('X1', 'DELIVERED');
    }

    public function testAShippedOrderCannotBeCancelled(): void
    {
        $resource = $this->createMock(FulfilmentEvent::class);
        $resource->method('latestState')->willReturn('SHIPPED');

        $this->expectException(LocalizedException::class);
        (new FulfilmentService($resource))->transition('X1', 'CANCELLED');
    }
}
