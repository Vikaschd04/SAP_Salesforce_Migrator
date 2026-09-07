<?php

declare(strict_types=1);

namespace MageMonk\Appointment\Block;

use Magento\Customer\Model\Customer;
use Magento\Directory\Block\Data as DirectoryData;
use Magento\Framework\View\Element\Template as TemplateAlias;
use Magento\Framework\View\Element\Template\Context;
use Magento\Customer\Model\Session as CustomerSession;
use Magento\Inventory\Model\ResourceModel\Source\CollectionFactory as SourceCollectionFactory;

use MageMonk\Appointment\Model\AppointmentFactory;

class Data extends TemplateAlias
{
    /**
     * Initialization
     *
     * @param Context $context
     * @param CustomerSession $customerSession
     * @param SourceCollectionFactory $sourceCollectionFactory
     * @param AppointmentFactory $appointmentFactory
     * @param DirectoryData $directoryBlock
     * @param array $data
     */
    public function __construct(
        Context $context,
        protected readonly CustomerSession $customerSession,
        private readonly SourceCollectionFactory  $sourceCollectionFactory,
        private readonly AppointmentFactory $appointmentFactory,
        private readonly DirectoryData $directoryBlock,
        array $data = []
    ) {
        parent::__construct($context, $data);
    }

    /**
     * Get current customer information
     *
     * @return Customer
     */
    public function getCustomer(): Customer
    {
        return $this->customerSession->getCustomer();
    }

    /**
     * Get stores information
     *
     * @return array
     */
    public function getStores(): array
    {
        return $this->sourceCollectionFactory->create()
             ->addFieldToSelect('*')
             ->getData();
    }

    /**
     * @return array|null
     */
    public function getAppointments(): ?array
    {
       $customerId = $this->getCustomer()->getId();
        return $this->appointmentFactory->create()
             ->getCollection()
             ->addFieldToSelect('*')
             ->addFieldToFilter('customer_id', $customerId)
             ->getData();
    }

    /**
     * Get state and country values
     *
     * @return string
     */
    public function getCountries(): string
    {
        return $this->directoryBlock->getCountryHtmlSelect();
    }

    /**
     * Get state and region values
     *
     * @return string
     */
    public function getRegion(): string
    {
        return $this->directoryBlock->getRegionHtmlSelect();
    }
}
