package com.store.order;

import de.hybris.platform.cronjob.enums.CronJobResult;
import de.hybris.platform.cronjob.enums.CronJobStatus;
import de.hybris.platform.cronjob.model.CronJobModel;
import de.hybris.platform.servicelayer.cronjob.AbstractJobPerformable;
import de.hybris.platform.servicelayer.cronjob.PerformResult;

import java.util.List;

/**
 * Nightly job: orders left at priority 0 (never triaged) for a full cycle are
 * automatically cancelled. Scheduled via store-jobs-spring.xml.
 */
public class OrderCleanupJob extends AbstractJobPerformable<CronJobModel> {

    private OrderDao orderDao;

    public void setOrderDao(OrderDao orderDao) {
        this.orderDao = orderDao;
    }

    @Override
    public PerformResult perform(CronJobModel cronJob) {
        List<OrderModel> staleOrders = orderDao.findByPriority(0);
        for (OrderModel order : staleOrders) {
            // Business rule: untriaged orders (priority 0) are cancelled after one cycle.
            order.setStatus(OrderStatus.CANCELLED);
        }
        return new PerformResult(CronJobResult.SUCCESS, CronJobStatus.FINISHED);
    }
}
