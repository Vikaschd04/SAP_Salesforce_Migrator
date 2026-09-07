<?php

declare(strict_types=1);

namespace MageMonk\Appointment\Controller\Index;

use Magento\Framework\App\Action\HttpPostActionInterface;
use Magento\Framework\App\Request\InvalidRequestException;
use Magento\Framework\App\RequestInterface;
use Magento\Framework\Controller\Result\Redirect;
use Magento\Framework\Controller\ResultFactory;
use Magento\Framework\App\CsrfAwareActionInterface;
use Magento\Framework\Message\ManagerInterface;
use Magento\Framework\App\Response\RedirectInterface;

use MageMonk\Appointment\Model\AppointmentFactory;
use MageMonk\Appointment\Model\ResourceModel\Appointment as AppointmentResource;

class Create implements CsrfAwareActionInterface, HttpPostActionInterface
{
    /**
     * Initialization
     *
     * @param ResultFactory $resultFactory
     * @param ManagerInterface $messageManager
     * @param RedirectInterface $redirect
     * @param RequestInterface $request
     * @param AppointmentFactory $appointmentFactory
     * @param AppointmentResource $appointmentResource
     */
    public function __construct(
        private readonly ResultFactory  $resultFactory,
        private readonly ManagerInterface $messageManager,
        private readonly RedirectInterface $redirect,
        private readonly RequestInterface $request,
        private readonly AppointmentFactory $appointmentFactory,
        private readonly AppointmentResource $appointmentResource
    ) {
    }

    /**
     * @return Redirect
     */
    public function execute(): Redirect
    {
        $resultRedirect = $this->resultFactory->create(ResultFactory::TYPE_REDIRECT);
        $resultRedirect->setUrl($this->redirect->getRefererUrl());
        $postData = $this->request->getParams();
        $this->setAppointment($postData);

        return  $resultRedirect;
    }

    /**
     * @param $postData
     * @return void
     */
    private function setAppointment($postData): void
    {
        $appointment = $this->appointmentFactory->create();
        try {
            $appointment->setData($postData);
            $this->appointmentResource->save($appointment);
            $this->messageManager->addSuccessMessage( __('Your Appointment has been successfully submitted.') );
        } catch (\Exception $e) {
            $this->messageManager->addErrorMessage(__('We were unable to submit your request. Please try again!'));
        }
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
