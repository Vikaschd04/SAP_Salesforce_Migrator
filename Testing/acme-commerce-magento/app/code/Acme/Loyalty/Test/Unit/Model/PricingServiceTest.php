<?php
declare(strict_types=1);

namespace Acme\Loyalty\Test\Unit\Model;

use Acme\Loyalty\Model\PricingService;
use Magento\Framework\App\Config\ScopeConfigInterface;
use PHPUnit\Framework\TestCase;

class PricingServiceTest extends TestCase
{
    private PricingService $service;

    protected function setUp(): void
    {
        $scopeConfig = $this->createMock(ScopeConfigInterface::class);
        $this->service = new PricingService($scopeConfig, 200.0, 0.10);
    }

    public function testSpendDiscountAppliesTenPercentOverThreshold(): void
    {
        $this->assertEquals(180.00, $this->service->applySpendDiscount(200.00));
    }

    public function testSpendDiscountDoesNotApplyBelowThreshold(): void
    {
        $this->assertEquals(199.99, $this->service->applySpendDiscount(199.99));
    }

    public function testGoldCustomersGetTwelvePercentOff(): void
    {
        $this->assertEquals(88.00, $this->service->applyTierDiscount(100.00, 'GOLD'));
    }

    public function testSilverCustomersGetSixPercentOff(): void
    {
        $this->assertEquals(94.00, $this->service->applyTierDiscount(100.00, 'SILVER'));
    }

    public function testUnknownTierGetsNoDiscount(): void
    {
        $this->assertEquals(100.00, $this->service->applyTierDiscount(100.00, 'BRONZE'));
    }

    public function testPointsAreOnePerWholeUnitRoundedDown(): void
    {
        $this->assertEquals(199, $this->service->pointsFor(199.99));
    }

    public function testNegativeSubtotalIsRejected(): void
    {
        $this->expectException(\InvalidArgumentException::class);
        $this->service->applySpendDiscount(-1.00);
    }
}
