<?php
declare(strict_types=1);

namespace Acme\Loyalty\Test\Unit\Model;

use Acme\Core\Helper\Money;
use Acme\Loyalty\Model\PricingService;
use Acme\Loyalty\Model\TierPolicy;
use PHPUnit\Framework\TestCase;

class PricingServiceTest extends TestCase
{
    private PricingService $pricing;

    protected function setUp(): void
    {
        $money = $this->createMock(Money::class);
        $money->method('percentageOf')
            ->willReturnCallback(static fn (float $a, float $p): float => $a * ($p / 100));

        $this->pricing = new PricingService($money, new TierPolicy([
            'BRONZE' => 0, 'SILVER' => 500, 'GOLD' => 2000,
        ]), 200.0, 0.10);
    }

    public function testSpendBelowThresholdGetsNoDiscount(): void
    {
        self::assertSame(100.0, $this->pricing->applySpendDiscount(100.0, 199.99));
    }

    public function testThresholdIsInclusive(): void
    {
        self::assertSame(90.0, $this->pricing->applySpendDiscount(100.0, 200.0));
    }

    public function testGoldTierTakesFivePercent(): void
    {
        self::assertSame(95.0, $this->pricing->applyTierDiscount(100.0, 'GOLD'));
    }

    public function testUnknownTierIsNotAnError(): void
    {
        self::assertSame(100.0, $this->pricing->applyTierDiscount(100.0, 'PLATINUM'));
    }

    public function testPointsAreTruncatedNotRounded(): void
    {
        self::assertSame(10, $this->pricing->pointsFor(10.99));
    }
}
