<?php
declare(strict_types=1);

namespace Acme\Loyalty\Setup\Patch\Data;

use Magento\Customer\Model\Customer;
use Magento\Customer\Setup\CustomerSetupFactory;
use Magento\Framework\Setup\ModuleDataSetupInterface;
use Magento\Framework\Setup\Patch\DataPatchInterface;

/**
 * EAV attributes on the platform's Customer entity. These exist only in the database
 * after this patch runs — nothing in the codebase declares them, which is why a static
 * read of the module cannot see the whole entity.
 */
class AddLoyaltyAttributes implements DataPatchInterface
{
    private ModuleDataSetupInterface $moduleDataSetup;
    private CustomerSetupFactory $customerSetupFactory;

    public function __construct(
        ModuleDataSetupInterface $moduleDataSetup,
        CustomerSetupFactory $customerSetupFactory
    ) {
        $this->moduleDataSetup = $moduleDataSetup;
        $this->customerSetupFactory = $customerSetupFactory;
    }

    public function apply()
    {
        $setup = $this->customerSetupFactory->create(['setup' => $this->moduleDataSetup]);

        $setup->addAttribute(Customer::ENTITY, 'acme_loyalty_tier', [
            'type' => 'varchar',
            'label' => 'Loyalty tier',
            'input' => 'text',
            'required' => false,
            'visible' => true,
            'user_defined' => true,
            'system' => false,
        ]);

        $setup->addAttribute(Customer::ENTITY, 'acme_points_balance', [
            'type' => 'int',
            'label' => 'Points balance',
            'input' => 'text',
            'required' => false,
            'visible' => true,
            'user_defined' => true,
            'system' => false,
        ]);

        return $this;
    }

    public static function getDependencies()
    {
        return [];
    }

    public function getAliases()
    {
        return [];
    }
}
