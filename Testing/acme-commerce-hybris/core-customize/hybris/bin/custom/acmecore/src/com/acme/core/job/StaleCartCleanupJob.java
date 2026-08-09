package com.acme.core.job;

import de.hybris.platform.core.model.order.OrderModel;
import de.hybris.platform.cronjob.enums.CronJobResult;
import de.hybris.platform.cronjob.enums.CronJobStatus;
import de.hybris.platform.cronjob.model.CronJobModel;
import de.hybris.platform.servicelayer.cronjob.AbstractJobPerformable;
import de.hybris.platform.servicelayer.cronjob.PerformResult;
import de.hybris.platform.servicelayer.model.ModelService;

import com.acme.core.dao.OrderDao;

import java.util.Calendar;
import java.util.Date;
import java.util.List;

import org.apache.log4j.Logger;

/**
 * Removes abandoned carts older than the configured age. Scheduled nightly at 02:00 by
 * the cron trigger in essentialdata.
 */
public class StaleCartCleanupJob extends AbstractJobPerformable<CronJobModel>
{
	private static final Logger LOG = Logger.getLogger(StaleCartCleanupJob.class);
	private static final int BATCH = 500;

	private OrderDao orderDao;
	private int staleDays = 30;

	@Override
	public PerformResult perform(final CronJobModel cronJob)
	{
		final Calendar cutoff = Calendar.getInstance();
		cutoff.add(Calendar.DAY_OF_YEAR, -staleDays);

		int removed = 0;
		try
		{
			final List<OrderModel> stale = orderDao.findStaleCarts(cutoff.getTime(), BATCH);
			for (final OrderModel cart : stale)
			{
				if (clearAbortRequestedIfNeeded(cronJob))
				{
					LOG.info("Abort requested; stopping after " + removed + " carts");
					return new PerformResult(CronJobResult.UNKNOWN, CronJobStatus.ABORTED);
				}
				modelService.remove(cart);
				removed++;
			}
		}
		catch (final Exception e)
		{
			LOG.error("Stale cart cleanup failed", e);
			return new PerformResult(CronJobResult.ERROR, CronJobStatus.ABORTED);
		}

		LOG.info("Removed " + removed + " stale carts older than " + staleDays + " days");
		return new PerformResult(CronJobResult.SUCCESS, CronJobStatus.FINISHED);
	}

	@Override
	public boolean isAbortable()
	{
		return true;
	}

	public void setOrderDao(final OrderDao orderDao) { this.orderDao = orderDao; }
	public void setStaleDays(final int staleDays) { this.staleDays = staleDays; }
}
