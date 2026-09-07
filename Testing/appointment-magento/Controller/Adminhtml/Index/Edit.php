<?php

declare(strict_types=1);

namespace MageMonk\Appointment\Controller\Adminhtml\Index;

use Magento\Framework\Controller\ResultFactory;
use Magento\Backend\App\Action;
use Magento\Framework\View\Result\Page;

class Edit extends Action
{
    /**
     * @return Page
     */
    public function execute(): Page
    {
        return $this->resultFactory->create(ResultFactory::TYPE_PAGE);
    }
}
