<?php

declare(strict_types=1);

namespace MageMonk\Appointment\Api\Data;

/**
 * Appointment interface.
 * @api
 */
interface AppointmentInterface
{
    /**#@+
     * Constants defined for keys of the data array. Identical to the name of the getter in snake case
     */
    const ENTITY_ID = 'entity_id';
    const NAME = 'name';
    const EMAIL = 'email';
    const CONTACT_NUMBER = 'contact_number';
    const ADDRESS = 'address';
    const STATE = 'state';
    const CITY = 'city';
    const COUNTRY = 'country';
    const MODE_OF_APPOINTMENT = 'mode_of_appointment';
    const MODE_OF_COMMUNICATION = 'mode_of_communication';
    const STORE_ID = 'store_id';
    const APPOINTMENT_DATETIME = 'appointment_datetime';
    const PREFERRED_LANGUAGE = 'preferred_language';
    const STATUS = 'status';
    const CUSTOMER_ID = 'customer_id';
    const COMMENT = 'comment';
    const CREATED_AT = 'created_at';
    const UPDATED_AT = 'updated_at';
    /**#@-*/

    /**
     * Get appointment id
     *
     * @return int|null
     */
    public function getEntityId(): ?int;

    /**
     * Set appointment id
     *
     * @param int $entityId
     * @return $this
     */
    public function setEntityId(int $entityId): self;

    /**
     * Get name
     *
     * @return string|null
     */
    public function getName(): ?string;

    /**
     * Set name
     *
     * @param string $name
     * @return $this
     */
    public function setName(string $name): self;

    /**
     * Get email
     *
     * @return string|null
     */
    public function getEmail(): ?string;

    /**
     * Set email
     *
     * @param string $email
     * @return $this
     */
    public function setEmail(string $email): self;

    /**
     * Get contact number
     *
     * @return string|null
     */
    public function getContactNumber(): ?string;

    /**
     * Set contact number
     *
     * @param string $contactNumber
     * @return $this
     */
    public function setContactNumber(string $contactNumber): self;

    /**
     * Get address
     *
     * @return string|null
     */
    public function getAddress(): ?string;

    /**
     * Set address
     *
     * @param string $address
     * @return $this
     */
    public function setAddress(string $address): self;

    /**
     * Get state
     *
     * @return string|null
     */
    public function getState(): ?string;

    /**
     * Set state
     *
     * @param string $state
     * @return $this
     */
    public function setState(string $state): self;

    /**
     * Get city
     *
     * @return string|null
     */
    public function getCity(): ?string;

    /**
     * Set city
     *
     * @param string $city
     * @return $this
     */
    public function setCity(string $city): self;

    /**
     * Get country
     *
     * @return string|null
     */
    public function getCountry(): ?string;

    /**
     * Set country
     *
     * @param string $country
     * @return $this
     */
    public function setCountry(string $country): self;

    /**
     * Get mode of appointment
     *
     * @return string|null
     */
    public function getModeOfAppointment(): ?string;

    /**
     * Set mode of appointment
     *
     * @param string $modeOfAppointment
     * @return $this
     */
    public function setModeOfAppointment(string $modeOfAppointment): self;

    /**
     * Get mode of communication
     *
     * @return string|null
     */
    public function getModeOfCommunication(): ?string;

    /**
     * Set mode of communication
     *
     * @param string $modeOfCommunication
     * @return $this
     */
    public function setModeOfCommunication(string $modeOfCommunication): self;

    /**
     * Get store id
     *
     * @return string|null
     */
    public function getStoreId(): ?string;

    /**
     * Set store id
     *
     * @param string $storeId
     * @return $this
     */
    public function setStoreId(string $storeId): self;

    /**
     * Get appointment datetime
     *
     * @return string|null
     */
    public function getAppointmentDatetime(): ?string;

    /**
     * Set appointment datetime
     *
     * @param string $appointmentDatetime
     * @return $this
     */
    public function setAppointmentDatetime(string $appointmentDatetime): self;

    /**
     * Get preferred language
     *
     * @return string|null
     */
    public function getPreferredLanguage(): ?string;

    /**
     * Set preferred language
     *
     * @param string $preferredLanguage
     * @return $this
     */
    public function setPreferredLanguage(string $preferredLanguage): self;

    /**
     * Get status
     *
     * @return string|null
     */
    public function getStatus(): ?string;

    /**
     * Set status
     *
     * @param string $status
     * @return $this
     */
    public function setStatus(string $status): self;

    /**
     * Get Comment
     *
     * @return string|null
     */
    public function getComment(): ?string;

    /**
     * Set comment
     *
     * @param string $comment
     * @return $this
     */
    public function setComment(string $comment): self;

     /**
     * Get customer id
     *
     * @return int|null
     */
    public function getCustomerId(): ?int;

    /**
     * Set customer id
     *
     * @param int $customerId
     * @return $this
     */
    public function setCustomerId(int $customerId): self;

    /**
     * Get created at time
     *
     * @return string|null
     */
    public function getCreatedAt(): ?string;

    /**
     * Set created at time
     *
     * @param string $createdAt
     * @return $this
     */
    public function setCreatedAt(string $createdAt): self;

    /**
     * Get updated at time
     *
     * @return string|null
     */
    public function getUpdatedAt(): ?string;

    /**
     * Set updated at time
     *
     * @param string $updatedAt
     * @return $this
     */
    public function setUpdatedAt(string $updatedAt): self;

}
