# Adobe Commerce → SAP Hybris — knowledge corpus

Retrieved lexically and injected into the comprehension, generation and critic prompts.
Each document covers one thing the pair gets wrong, and says what the wrong version looks
like — because a model that has read "use a decorator" still writes an interceptor unless
it has read *why an interceptor silently always calls through*.

| Document | Covers |
|---|---|
| `flexiblesearch.md` | how a Hybris query is written, bound and bounded |
| `interceptor_vs_decorator.md` | the `around`-plugin routing decision, and why the wrong one is quiet |
| `items_and_models.md` | items.xml, platform-generated models, and extending a type SAP owns |
| `cronjobs.md` | JobPerformable, the ImpEx schedule, Quartz vs Unix cron, cluster behaviour |
| `php_to_java_types.md` | resolving types from declarations, and money |
