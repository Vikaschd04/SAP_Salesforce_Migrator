# Cron: from crontab.xml to a JobPerformable

```java
public class ExpirePointsJobPerformable extends AbstractJobPerformable<CronJobModel>
{
    @Override
    public PerformResult perform(final CronJobModel cronJob)
    {
        // work
        return new PerformResult(CronJobResult.SUCCESS, CronJobStatus.FINISHED);
    }

    @Override
    public boolean isAbortable() { return true; }
}
```

The class does the work. The **schedule is data**, in ImpEx:

```
INSERT_UPDATE ServicelayerJob;code[unique=true];springId
;ExpirePointsJob;expirePointsJobPerformable

INSERT_UPDATE CronJob;code[unique=true];job(code);sessionLanguage(isocode)
;ExpirePointsCronJob;ExpirePointsJob;en

INSERT_UPDATE Trigger;cronJob(code)[unique=true];cronExpression
;ExpirePointsCronJob;0 0 2 * * ?
```

The `springId` must name a bean that exists. Without it the ImpEx imports cleanly and the
job fails the first time it runs — later and quieter than a build failure.

## Two differences from Magento that change behaviour

**Cron syntax.** Magento uses 5-field Unix cron; Hybris triggers use 6-field Quartz.
Quartz adds a leading seconds field, and numbers days of the week from **1** where Unix
uses **0**. `30 3 * * 0` (Sunday) becomes `0 30 3 ? * 1`. Off by one moves a weekly job to
Saturday, and nothing fails.

**Cluster behaviour.** A Magento cron job runs **once** across the cluster — whichever node
takes the lock. A Hybris cronjob runs on **every node** unless the trigger sets node
affinity. A nightly points expiry runs four times on a four-node cluster, and the second
run sees the state the first left.
