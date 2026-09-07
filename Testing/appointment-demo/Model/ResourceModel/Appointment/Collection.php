<?php
declare(strict_types=1);

namespace MageMonk\Appointment\Model\ResourceModel\Appointment;

class Collection extends \Magento\Framework\Model\ResourceModel\Db\Collection\AbstractCollection
{
	protected $_idFieldName = 'entity_id';
	protected $_eventPrefix = 'magemonk_appointment_collection';
	protected $_eventObject = 'appointment_collection';

	/**
	 * Define resource model
	 *
	 * @return void
	 */
	protected function _construct()
	{
		$this->_init('MageMonk\Appointment\Model\Appointment', 'MageMonk\Appointment\Model\ResourceModel\Appointment');
	}

}

