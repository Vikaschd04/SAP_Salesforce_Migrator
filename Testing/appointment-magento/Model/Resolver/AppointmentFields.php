<?php

declare(strict_types=1);

namespace MageMonk\Appointment\Model\Resolver;

use Magento\Framework\GraphQl\Config\Element\Field;
use Magento\Framework\GraphQl\Query\ResolverInterface;
use Magento\Framework\GraphQl\Schema\Type\ResolveInfo;
use MageMonk\Appointment\Model\ResourceModel\Appointment as AppointmentResourceModel;

class AppointmentFields implements ResolverInterface
{
    /**
     * Initialization
     *
     * @param AppointmentResourceModel $appointmentModel
     */
    public function __construct(
        private readonly AppointmentResourceModel $appointmentModel
    ) {
    }

     /**
     * @inheritdoc
     */
    public function resolve(
        Field $field,
        $context,
        ResolveInfo $info,
        array $value = null,
        array $args = null
    ) {
        $fields = $this->appointmentModel->getFields();
        $appointmentFields = [];
        foreach($fields as $key=>$field) {
            $appointmentFields[$key]['id'] = $key;
            $appointmentFields[$key]['column_name'] = $field['COLUMN_NAME'];
            $appointmentFields[$key]['data_type'] = $field['DATA_TYPE'];
        }
        return ['items' => $appointmentFields];
    }

}
