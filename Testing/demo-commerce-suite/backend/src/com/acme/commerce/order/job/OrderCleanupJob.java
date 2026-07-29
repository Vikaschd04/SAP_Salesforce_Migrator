package com.acme.commerce.order.job;

import com.acme.commerce.order.dao.OrderDao;
import com.acme.commerce.order.enums.OrderStatus;
import com.acme.commerce.order.model.OrderModel;

import de.hybris.platform.cronjob.enums.CronJobResult;
import de.hybris.platform.cronjob.enums.CronJobStatus;
import de.hybris.platform.servicelayer.cronjob.AbstractJobPerformable;
import de.hybris.platform.servicelayer.cronjob.PerformResult;
import de.hybris.platform.servicelayer.model.ModelService;
import de.hybris.platform.servicelayer.cronjob.CronJobModel;

import org.apache.log4j.Logger;

import java.util.Calendar;
import java.util.Date;
import java.util.List;

/**
 * Nightly housekeeping job: cancels orders that were created but never paid.
 *
 * <p>Any order still {@link OrderStatus#NEW} and unpaid after {@link #STALE_AFTER_DAYS} days is
 * considered abandoned and is moved to {@link OrderStatus#CANCELLED}, freeing reserved stock.</p>
 */
public class OrderCleanupJob extends AbstractJobPerformable<CronJobModel>
{
	private static final Logger LOG = Logger.getLogger(OrderCleanupJob.class);
	private static final int STALE_AFTER_DAYS = 7;

	private OrderDao orderDao;

	@Override
	public PerformResult perform(final CronJobModel cronJob)
	{
		final Date cutoff = daysAgo(STALE_AFTER_DAYS);
		final List<OrderModel> staleOrders = orderDao.findStaleUnpaidOrders(cutoff);

		int cancelled = 0;
		for (final OrderModel order : staleOrders)
		{
			if (clearJobShouldAbort())
			{
				LOG.info("OrderCleanupJob aborted after cancelling " + cancelled + " orders");
				return new PerformResult(CronJobResult.UNKNOWN, CronJobStatus.ABORTED);
			}

			order.setStatus(OrderStatus.CANCELLED);
			modelService.save(order);
			cancelled++;
		}

		LOG.info("OrderCleanupJob cancelled " + cancelled + " stale unpaid orders");
		return new PerformResult(CronJobResult.SUCCESS, CronJobStatus.FINISHED);
	}

	private Date daysAgo(final int days)
	{
		final Calendar calendar = Calendar.getInstance();
		calendar.add(Calendar.DAY_OF_MONTH, -days);
		return calendar.getTime();
	}

	public void setOrderDao(final OrderDao orderDao)
	{
		this.orderDao = orderDao;
	}

	public void setModelService(final ModelService modelService)
	{
		this.modelService = modelService;
	}
}
