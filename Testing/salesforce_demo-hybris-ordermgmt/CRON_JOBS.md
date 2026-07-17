# Scheduled Jobs Runbook (Hybris Cronjobs → Salesforce Scheduled Apex)

Hybris schedules background jobs with a cron trigger in Spring XML or ImpEx. Salesforce's `System.schedule` uses the same Quartz-based cron syntax, so translation is a **validated pass-through**, not a rewrite — the job's own logic was translated separately (see the generated `*Scheduler.cls` classes, which implement `Schedulable`).

## Jobs

| Hybris Job | Apex Scheduler | Cron Expression | Active | Notes |
|---|---|---|---|---|
| `OrderCleanupJob` | `OrderCleanupScheduler` | `0 0 2 * * ?` | yes | — |

## Schedule commands (Anonymous Apex)

```apex
System.schedule('OrderCleanupScheduler', '0 0 2 * * ?', new OrderCleanupScheduler());
```

Run via `sf apex run --file schedule.apex --target-org <org>` (also written alongside this runbook), or paste into Setup → Apex → Execute Anonymous Window.

