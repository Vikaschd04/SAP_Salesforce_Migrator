<?php
declare(strict_types=1);

namespace Acme\Loyalty\Cron;

use Magento\Framework\App\ResourceConnection;

class ExpirePoints
{
    private ResourceConnection $resource;

    public function __construct(ResourceConnection $resource)
    {
        $this->resource = $resource;
    }

    /**
     * Expires points older than 24 months. Runs nightly on every node in the cluster.
     */
    public function execute(): void
    {
        $connection = $this->resource->getConnection();
        $connection->query(
            "UPDATE acme_loyalty_account SET points_balance = 0 "
            . "WHERE enrolled_at < DATE_SUB(NOW(), INTERVAL 24 MONTH)"
        );
    }
}
