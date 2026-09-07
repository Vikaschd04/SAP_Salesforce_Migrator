<?php
declare(strict_types=1);

namespace MageMonk\Appointment\Model\Resolver;

use Magento\Framework\Exception\LocalizedException;
use Magento\Framework\GraphQl\Config\Element\Field;
use Magento\Framework\GraphQl\Query\ResolverInterface;
use Magento\Framework\GraphQl\Schema\Type\ResolveInfo;
use Magento\Framework\GraphQl\Exception\GraphQlInputException;
use MageMonk\Appointment\Model\AppointmentFactory;
use Magento\Framework\GraphQl\Query\Resolver\ContextInterface;
use MageMonk\Appointment\Model\ResourceModel\Appointment as AppointmentResource;

class SaveAppointment implements ResolverInterface
{
    /**
     * Initialization
     *
     * @param AppointmentFactory $appointmentFactory
     */
    public function __construct(
        private readonly AppointmentFactory $appointmentFactory,
        private readonly AppointmentResource $appointmentResource,
    ) {
    }

    /**
     * Save Appointments
     *
     * @param Field $field
     * @param ContextInterface $context
     * @param ResolveInfo $info
     * @param array|null $value
     * @param array|null $args
     * @throws GraphQlInputException
     */
    public function resolve(Field $field, $context, ResolveInfo $info, array $value = null, array $args = null)
    {
        try {
            $appointment = $this->appointmentFactory->create();
            $appointmentData = [
                "name" => $args['input']['name'],
                "email"      => $args['input']['email'],
                "contact_number"  => $args['input']['contact_number'],
                "mode_of_appointment"   => $args['input']['mode_of_appointment'],
                "store_id"   => $args['input']['store_id'],
                "address" => $args['input']['address'],
                "country_id"      => $args['input']['country_id'],
                "region"  => $args['input']['region'],
                "city"   => $args['input']['city'],
                "appointment_datetime"   =>  $args['input']['appointment_datetime'],
                "preferred_language" => $args['input']['preferred_language'],
            ];
            $appointment->setData($appointmentData);
            $this->appointmentResource->save($appointment);
            return ['message' => "Appointment created successfully"];

        } catch (LocalizedException $e) {
            throw new GraphQlInputException(__($e->getMessage()));
        } catch (\Exception $e) {
        }
    }
}
