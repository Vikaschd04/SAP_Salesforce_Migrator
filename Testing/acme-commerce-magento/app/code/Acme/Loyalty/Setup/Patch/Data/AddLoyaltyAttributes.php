<?php
declare(strict_types=1);

namespace Acme\Loyalty\Setup\Patch\Data;

use Magento\Customer\Setup\CustomerSetupFactory;
use Magento\Framework\Setup\ModuleDataSetupInterface;
use Magento\Framework\Setup\Patch\DataPatchInterface;
use Magento\Customer\Model\Customer;

class AddLoyaltyAttributes implements DataPatchInterface
{
    private ModuleDataSetupInterface $setup;
    private CustomerSetupFactory $customerSetupFactory;

    public function __construct(
        ModuleDataSetupInterface $setup,
        CustomerSetupFactory $customerSetupFactory
    ) {
        $this->setup = $setup;
        $this->customerSetupFactory = $customerSetupFactory;
    }

    /**
     * Adds the loyalty attributes to the customer entity. These are EAV rows created
     * at runtime, not columns declared in db_schema.xml.
     */
    public function apply()
    {
        $customerSetup = $this->customerSetupFactory->create(['setup' => $this->setup]);

        $customerSetup->addAttribute(Customer::ENTITY, 'acme_loyalty_tier', [
            'type' => 'varchar',
            'label' => 'Loyalty Tier',
            'input' => 'select',
            'source' => \Acme\Loyalty\Model\Source\Tier::class,
            'required' => false,
            'visible' => true,
            'user_defined' => true,
            'system' => false,
            'sort_order' => 100,
        ]);

        $customerSetup->addAttribute(Customer::ENTITY, 'acme_points_balance', [
            'type' => 'int',
            'label' => 'Points Balance',
            'input' => 'text',
            'required' => false,
            'visible' => true,
            'user_defined' => true,
            'system' => false,
            'sort_order' => 110,
        ]);
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
