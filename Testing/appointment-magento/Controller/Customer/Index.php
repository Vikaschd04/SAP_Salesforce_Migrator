<?php

declare(strict_types=1);

namespace MageMonk\Appointment\Controller\Customer;

use Magento\Framework\App\ActionInterface;
use Magento\Framework\View\Result\Page;
use Magento\Framework\View\Result\PageFactory;

class Index implements ActionInterface
{

    /**
     * @param PageFactory $resultPageFactory
     */
    public function __construct(
        private readonly PageFactory $resultPageFactory
    ) {
    }

    /**
     * Load the page defined in view/frontend/layout/appointment_customer_index.xml
     *
     * @return Page
     */
    public function execute(): Page
    {
        return $this->resultPageFactory->create();
    }

}


