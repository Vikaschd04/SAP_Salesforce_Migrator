<?php

declare(strict_types=1);

namespace  MageMonk\Appointment\Block\Adminhtml\Appointment\Edit;

use Magento\Framework\UrlInterface;
use Magento\Framework\Registry;
use Magento\Backend\Block\Widget\Context;

/**
 * Class GenericButton
 */
class GenericButton
{

    /**
     * Initialization
     *
     * @param Context $context
     * @param Registry $registry
     * @param UrlInterface $urlBuilder
     */
    public function __construct(
       Context $context,
       private readonly Registry $registry,
       private readonly UrlInterface $urlBuilder
    ) {
    }

    /**
     * Return the synonyms group id.
     *
     * @return int|null
     */
    public function getId(): ?int
    {
        $appointment = $this->registry->registry('appointment');
        return $appointment ? $appointment->getId() : null;
    }

    /**
     * Generate url by route and parameters
     *
     * @param string $route
     * @param array $params
     * @return  string
     */
    public function getUrl(string $route = '', array $params = []): string
    {
        return $this->urlBuilder->getUrl($route, $params);
    }
}
