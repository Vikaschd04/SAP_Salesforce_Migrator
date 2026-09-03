# FlexibleSearch — how a Hybris query is written

FlexibleSearch is SAP's query language. It looks like SQL and is not: it queries **item
types**, not tables, and the platform resolves the type to its deployment table.

```java
private static final String BY_CODE =
        "SELECT {i:pk} FROM {AcmeLoyaltyAccount AS i} WHERE {i:code} = ?code";

final FlexibleSearchQuery query = new FlexibleSearchQuery(BY_CODE);
query.addQueryParameter("code", code);
query.setCount(1);
final List<AcmeLoyaltyAccountModel> results =
        flexibleSearchService.<AcmeLoyaltyAccountModel>search(query).getResult();
```

Rules that are not negotiable:

- **Braces name the type and the attribute.** `{AcmeLoyaltyAccount AS i}` is the type,
  `{i:code}` is its attribute. A bare table name will not resolve.
- **Bind every parameter.** `addQueryParameter` is the only correct way. String
  concatenation into a FlexibleSearch is how injection arrives on this platform.
- **Bound the result.** `setCount(n)` for a find-one. An unbounded query against a live
  catalogue loads the catalogue.
- **Never inside a loop.** One query per iteration is one query per order line. Collect
  the keys, query once with `IN (?keys)`, and index the result in a Map.

## Coming from Magento

A Magento collection load (`$collection->addFieldToFilter(...)`) or a repository call
becomes a DAO method. The DAO is the only place a query belongs — a service that queries
directly is the pattern Hybris codebases are refactored *away* from.
