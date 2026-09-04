<?php
declare(strict_types=1);

namespace Acme\Fulfilment\Console\Command;

use Acme\Fulfilment\Api\FulfilmentServiceInterface;
use Symfony\Component\Console\Command\Command;
use Symfony\Component\Console\Input\InputArgument;
use Symfony\Component\Console\Input\InputInterface;
use Symfony\Component\Console\Output\OutputInterface;

/**
 * `bin/magento acme:fulfilment:replay <order>` — replays a warehouse feed by hand when
 * the nightly import has dropped events. Operations run this, not the application.
 */
class ReplayEvents extends Command
{
    private FulfilmentServiceInterface $fulfilment;

    public function __construct(FulfilmentServiceInterface $fulfilment, ?string $name = null)
    {
        parent::__construct($name);
        $this->fulfilment = $fulfilment;
    }

    protected function configure()
    {
        $this->setName('acme:fulfilment:replay')
            ->setDescription('Replay fulfilment events for an order')
            ->addArgument('order', InputArgument::REQUIRED, 'Order increment id');
    }

    protected function execute(InputInterface $input, OutputInterface $output)
    {
        $order = (string) $input->getArgument('order');
        foreach (['ALLOCATED', 'PICKED', 'SHIPPED'] as $state) {
            $this->fulfilment->transition($order, $state);
            $output->writeln(sprintf('<info>%s -> %s</info>', $order, $state));
        }
        return Command::SUCCESS;
    }
}
