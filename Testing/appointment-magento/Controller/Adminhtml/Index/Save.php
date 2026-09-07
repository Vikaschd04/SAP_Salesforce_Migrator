<?php

declare(strict_types=1);

namespace MageMonk\Appointment\Controller\Adminhtml\Index;

use Magento\Framework\App\Action\HttpPostActionInterface;
use Magento\Framework\App\CsrfAwareActionInterface;
use Magento\Framework\App\Request\InvalidRequestException;
use Magento\Framework\App\RequestInterface;
use Magento\Framework\Controller\ResultFactory;
use MageMonk\Appointment\Model\AppointmentFactory;
use Magento\Framework\Message\ManagerInterface;
use MageMonk\Appointment\Model\ResourceModel\AppointmentFactory as AppointmentResource;


class Save implements HttpPostActionInterface, CsrfAwareActionInterface
{

    /**
     * Initialization
     *
     * @param RequestInterface $request
     * @param ResultFactory $resultFactory
     * @param AppointmentFactory $appointmentFactory
     * @param ManagerInterface $messageManager
     * @param AppointmentResource $appointmentResource
     */
    public function __construct(
        private readonly RequestInterface $request,
        private readonly ResultFactory $resultFactory,
        private readonly AppointmentFactory $appointmentFactory,
        private readonly ManagerInterface $messageManager,
        private readonly AppointmentResource $appointmentResource
    ) {
    }

    public function execute()
    {
        $resultRedirect = $this->resultFactory->create(ResultFactory::TYPE_REDIRECT);
        $postData = $this->request->getParams();
        $appointmentResource = $this->appointmentResource->create();
        try {
            $appointment = $this->appointmentFactory->create();
            $appointment->setData($postData);
            $appointmentResource->save($appointment);
            $this->messageManager->addSuccessMessage( __('Appointment has been successfully saved.') );
        } catch (\Exception $e) {
            $this->messageManager->addErrorMessage(nl2br($e->getMessage()));
        }

        return $resultRedirect->setPath("*/*/");
    }

    /**
     * @inheirtDoc
     */
    public function createCsrfValidationException(RequestInterface $request): ?InvalidRequestException
    {
        return null;
    }

    /**
     * @inheirtDoc
     */
    public function validateForCsrf(RequestInterface $request): ?bool
    {
        return true;
    }
}
