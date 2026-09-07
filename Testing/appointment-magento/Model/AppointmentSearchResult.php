<?php
declare(strict_types=1);

namespace MageMonk\Appointment\Model;

use Magento\Framework\Api\SearchResults;
use MageMonk\Appointment\Api\Data\AppointmentSearchResultInterface;

class AppointmentSearchResult extends SearchResults implements AppointmentSearchResultInterface
{

}
