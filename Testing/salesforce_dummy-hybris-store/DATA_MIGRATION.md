# Data Migration Runbook (ImpEx → Salesforce)

Generated from the Hybris `.impex` files. Each item type became a CSV of records keyed by an **External ID**, so loads are idempotent upserts (safe to re-run). Load parents before children.

## Objects

| Object | Records | External ID | Modes |
|---|---|---|---|
| `Customer__c` | 2 | `Uid__c` | INSERT_UPDATE |
| `Product__c` | 2 | `Code__c` | INSERT_UPDATE |
| `Order__c` | 2 | `Code__c` | INSERT_UPDATE |

## Load commands

```bash
# Authorise once:  sf org login web
sf data upsert bulk --sobject Customer__c --file data/Customer__c.csv --external-id Uid__c --wait 10
sf data upsert bulk --sobject Product__c --file data/Product__c.csv --external-id Code__c --wait 10
sf data upsert bulk --sobject Order__c --file data/Order__c.csv --external-id Code__c --wait 10
```

## Notes

- Each External ID field must be marked **External ID** and **Unique** on its object (the migrator sets this automatically when it also generates the object metadata).
- Simple `Rel__r.Key__c` columns load a lookup by the parent's External ID; ensure the parent object + that External ID field exist first.
