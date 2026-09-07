<?php
declare(strict_types=1);

namespace MageMonk\Appointment\Model\ResourceModel;
use Magento\Framework\Model\ResourceModel\Db\Context;

class Appointment extends \Magento\Framework\Model\ResourceModel\Db\AbstractDb
{
    /**
     * @param Context $context
     */
	public function __construct(
		Context $context
	)
	{
		parent::__construct($context);
	}

    /**
     * @return void
     */
	protected function _construct(): void
    {
		$this->_init('magemonk_appointment', 'entity_id');
	}

}
