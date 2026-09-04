<?php
declare(strict_types=1);

namespace Acme\Core\Model;

use Acme\Core\Api\StoreConfigInterface;
use Magento\Framework\App\Config\ScopeConfigInterface;
use Magento\Store\Model\ScopeInterface;

class StoreConfig implements StoreConfigInterface
{
    private ScopeConfigInterface $scopeConfig;
    private string $configPathPrefix;

    public function __construct(
        ScopeConfigInterface $scopeConfig,
        string $configPathPrefix = 'acme_core'
    ) {
        $this->scopeConfig = $scopeConfig;
        $this->configPathPrefix = $configPathPrefix;
    }

    public function isEnabled(?int $storeId = null): bool
    {
        return $this->scopeConfig->isSetFlag(
            $this->configPathPrefix . '/general/enabled',
            ScopeInterface::SCOPE_STORE,
            $storeId
        );
    }

    /**
     * Decimal places for money. Two everywhere Acme trades today, but it is configuration
     * rather than a constant because JPY has none and the Gulf stores have three.
     */
    public function currencyScale(?int $storeId = null): int
    {
        $raw = $this->value('general/currency_scale', $storeId);
        return $raw === null ? 2 : (int) $raw;
    }

    public function value(string $path, ?int $storeId = null): ?string
    {
        $value = $this->scopeConfig->getValue(
            $this->configPathPrefix . '/' . $path,
            ScopeInterface::SCOPE_STORE,
            $storeId
        );
        return $value === null ? null : (string) $value;
    }
}
