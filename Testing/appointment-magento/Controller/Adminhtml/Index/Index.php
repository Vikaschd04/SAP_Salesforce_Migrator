<?php

declare(strict_types=1);

namespace MageMonk\Appointment\Controller\Adminhtml\Index;

use Magento\Backend\App\Action;
use Magento\Backend\Model\View\Result\Page;
use Magento\Framework\Controller\ResultFactory;

class Index extends Action
{
    /**
     * Constants
     */
    const ADMIN_RESOURCE = 'MageMonk_Appointment::appointment';

    /**
     * Index action.
     *
     * @return Page
     */
    public function execute(): Page
    {
        /** @var Page $resultPage */
        $resultPage = $this->resultFactory->create(ResultFactory::TYPE_PAGE);
        $resultPage->getConfig()->getTitle()->prepend(__('Appointment'));
        $resultPage->addBreadcrumb(__('Appointment'), __('Appointment'));
        return $resultPage;
    }
}
