<?php
declare(strict_types=1);

namespace Acme\Loyalty\Api\Data;

interface LoyaltyAccountInterface
{
    public const CODE = 'code';
    public const TIER = 'tier';
    public const POINTS_BALANCE = 'points_balance';

    public function getCode(): string;

    public function setCode(string $code): self;

    public function getTier(): string;

    public function setTier(string $tier): self;

    public function getPointsBalance(): int;

    public function setPointsBalance(int $points): self;

    public function getLifetimeSpend(): float;
}
