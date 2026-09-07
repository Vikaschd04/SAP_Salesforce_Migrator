<?php

declare(strict_types=1);

namespace MageMonk\Appointment\Api;

use Magento\Framework\Api\SearchCriteriaInterface;
use MageMonk\Appointment\Api\Data\AppointmentInterface;
use Magento\Framework\Exception\NoSuchEntityException;
use MageMonk\Appointment\Api\Data\AppointmentSearchResultInterface;

interface AppointmentRepositoryInterface
{
    /**
     * Get by id
     *
     * @param int $id
     * @return AppointmentInterface
     * @throws NoSuchEntityException
     */
    public function getById(int $id): AppointmentInterface;

    /**
     * Save
     *
     * @param AppointmentInterface $appointment
     * @return AppointmentInterface
     */
    public function save(AppointmentInterface $appointment): AppointmentInterface;

    /**
     * Delete
     *
     * @param AppointmentInterface $appointment
     * @return void
     */
    public function delete(AppointmentInterface $appointment): void;

    /**
     * Get list
     *
     * @param SearchCriteriaInterface $searchCriteria
     * @return AppointmentSearchResultInterface
     */
    public function getList(SearchCriteriaInterface $searchCriteria): AppointmentSearchResultInterface;
}
