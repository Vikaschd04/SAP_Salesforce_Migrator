<?php
declare(strict_types=1);

namespace MageMonk\Appointment\Model;

use MageMonk\Appointment\Api\Data\AppointmentInterface as AppointmentInterfaceAlias;
use Magento\Framework\DataObject\IdentityInterface;
use Magento\Framework\Model\AbstractModel;

class Appointment extends AbstractModel implements IdentityInterface, AppointmentInterfaceAlias
{
    const CACHE_TAG = 'magemonk_appointment_appointment';

    protected $_cacheTag = 'magemonk_appointment_appointment';

    protected $_eventPrefix = 'magemonk_appointment_appointment';

    /**
     * @inheritdoc
     */
    protected function _construct(): void
    {
        $this->_init('MageMonk\Appointment\Model\ResourceModel\Appointment');
    }

    /**
     * @inheritdoc
     */
    public function getIdentities(): array
    {
	return [self::CACHE_TAG . '_' . $this->getId()];
    }

    /**
     * @inheritdoc
     */
    public function getDefaultValues(): array
    {
        return [];
    }

    /**
     * @inheritdoc
     */
    public function getEntityId(): ?int
    {
        return $this->_getData(self::ENTITY_ID);
    }

    /**
     * @inheritdoc
     */
    public function setEntityId($entityId): AppointmentInterfaceAlias
    {
        $this->setData(self::ENTITY_ID, $entityId);
        return $this;
    }

    /**
     * @inheritdoc
     */
    public function getName(): ?string
    {
       return $this->_getData(self::NAME);
    }

    /**
     * @inheritdoc
     */
    public function setName($name): AppointmentInterfaceAlias
    {
        $this->setData(self::NAME, $name);
        return $this;
    }

    /**
     * @inheritdoc
     */
    public function getEmail(): ?string
    {
        return $this->_getData(self::EMAIL);
    }

    /**
     * @inheritdoc
     */
    public function setEmail($email): AppointmentInterfaceAlias
    {
        $this->setData(self::EMAIL, $email);
        return $this;
    }

    /**
     * @inheritdoc
     */
    public function getContactNumber(): ?string
    {
        return $this->_getData(self::CONTACT_NUMBER);
    }

    public function setContactNumber($contactNumber): AppointmentInterfaceAlias
    {
        $this->setData(self::CONTACT_NUMBER, $contactNumber);
        return $this;
    }

    /**
     * @inheritdoc
     */
    public function getAddress(): ?string
    {
        return $this->_getData(self::ADDRESS);
    }

    /**
     * @inheritdoc
     */
    public function setAddress($address): AppointmentInterfaceAlias
    {
        $this->setData(self::ADDRESS, $address);
        return $this;
    }

    /**
     * @inheritdoc
     */
    public function getState(): ?string
    {
        return $this->_getData(self::STATE);
    }

    /**
     * @inheritdoc
     */
    public function setState($state): AppointmentInterfaceAlias
    {
        $this->setData(self::STATE, $state);
        return $this;
    }

    /**
     * @inheritdoc
     */
    public function getCity(): ?string
    {
        return $this->_getData(self::CITY);
    }

    /**
     * @inheritdoc
     */
    public function setCity($city): AppointmentInterfaceAlias
    {
        $this->setData(self::CITY, $city);
        return $this;
    }

    /**
     * @inheritdoc
     */
    public function getCountry(): ?string
    {
        return $this->_getData(self::COUNTRY);
    }

    /**
     * @inheritdoc
     */
    public function setCountry($country): AppointmentInterfaceAlias
    {
       $this->setData(self::COUNTRY, $country);
       return $this;
    }

    /**
     * @inheritdoc
     */
    public function getModeOfAppointment(): ?string
    {
        return $this->_getData(self::MODE_OF_APPOINTMENT);
    }

    /**
     * @inheritdoc
     */
    public function setModeOfAppointment($modeOfAppointment): self
    {
        $this->setData(self::MODE_OF_APPOINTMENT, $modeOfAppointment);
        return $this;
    }

    /**
     * @inheritdoc
     */
    public function getModeOfCommunication(): ?string
    {
        return $this->_getData(self::MODE_OF_COMMUNICATION);
    }

    /**
     * @inheritdoc
     */
    public function setModeOfCommunication($modeOfCommunication): self {
        $this->setData(self::MODE_OF_COMMUNICATION, $modeOfCommunication);
        return $this;
    }

    /**
     * @inheritdoc
     */
    public function getStoreId(): ?string
    {
        return $this->_getData(self::STORE_ID);
    }

    /**
     * @inheritdoc
     */
    public function setStoreId($storeId): self
    {
        $this->setData(self::STORE_ID, $storeId);
        return $this;
    }

    /**
     * @inheritdoc
     */
    public function getAppointmentDatetime(): ?string
    {
        return $this->_getData(self::APPOINTMENT_DATETIME);
    }

    /**
     * @inheritdoc
     */
    public function setAppointmentDatetime($appointmentDatetime): self {
        $this->setData(self::APPOINTMENT_DATETIME, $appointmentDatetime);
        return $this;
    }

    /**
     * @inheritdoc
     */
    public function getStatus(): ?string
    {
        return $this->_getData(self::STATUS);
    }

    /**
     * @inheritdoc
     */
    public function setStatus($status): self
    {
        $this->setData(self::STATUS, $status);
        return $this;
    }

    /**
     * @inheritdoc
     */
    public function getCustomerId(): ?int
    {
        return $this->_getData(self::CUSTOMER_ID);
    }

    /**
     * @inheritdoc
     */
    public function setCustomerId($customerId): self
    {
        $this->setData(self::CUSTOMER_ID, $customerId);
        return $this;
    }

    /**
     * @inheritdoc
     */
    public function getComment(): ?string
    {
        return $this->_getData(self::COMMENT);
    }

    /**
     * @inheritdoc
     */
    public function setComment($comment): self
    {
       $this->setData(self::COMMENT, $comment);
       return $this;
    }

    /**
     * @inheritdoc
     */
    public function getCreatedAt(): ?string
    {
        return $this->_getData(self::CREATED_AT);
    }

    /**
     * @inheritdoc
     */
    public function setCreatedAt($createdAt): self
    {
        $this->setData(self::CREATED_AT, $createdAt);
        return $this;
    }

    /**
     * @inheritdoc
     */
    public function getUpdatedAt(): ?string
    {
       return $this->_getData(self::UPDATED_AT);
    }

    /**
     * @inheritdoc
     */
    public function setUpdatedAt($updatedAt): self {
       $this->setData(self::UPDATED_AT, $updatedAt);
       return $this;
    }

    /**
     * @inheritdoc
     */
    public function getPreferredLanguage(): ?string
    {
        return $this->_getData(self::PREFERRED_LANGUAGE);
    }

    /**
     * @inheritdoc
     */
    public function setPreferredLanguage(string $preferredLanguage): AppointmentInterfaceAlias
    {
        $this->setData(self::PREFERRED_LANGUAGE, $preferredLanguage);
        return $this;
    }
}
