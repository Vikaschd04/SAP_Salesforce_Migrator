<?php
declare(strict_types=1);

namespace Acme\Core\Api;

/**
 * Store-scoped configuration, read through one place so the scope resolution rules
 * live in a single implementation rather than at every call site.
 */
interface StoreConfigInterface
{
    public function isEnabled(?int $storeId = null): bool;

    public function currencyScale(?int $storeId = null): int;

    public function value(string $path, ?int $storeId = null): ?string;
}
