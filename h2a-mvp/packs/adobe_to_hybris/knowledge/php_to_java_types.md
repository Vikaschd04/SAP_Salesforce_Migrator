# PHP types into Java, and the ones that have no answer

PHP allows an untyped parameter and a `mixed` return. Java allows neither, so every gap
has to become *some* Java type before the extension compiles. There are exactly two ways
to fill one: find a declaration, or guess.

**A guess compiles.** That is what makes it dangerous — the migration reports success, the
field deploys, and the mismatch appears the first time a real value flows through it.

## Where a declaration can come from

| Authority | Example |
|---|---|
| the signature | `float $subtotal` |
| the docblock | `@param float $subtotal` — PHP made authors write these for years |
| the schema | a `db_schema.xml` column or an EAV attribute of the same name |

Nothing else. Usage is **not** a source: `$x = $this->price * 2` strongly suggests a
number, and "strongly suggests" is what gets a migration into trouble.

| PHP | Java |
|---|---|
| `string` | `String` |
| `int` | `Integer` |
| `float` | `Double` — but see below |
| `bool` | `Boolean` |
| `array` | `List<?>` — the element type is rarely declared |
| `?float` | `Double`; nullability is a separate fact |
| `mixed`, `callable`, `object` | nothing — these go to a human |

## Money

PHP money is a `float`. Java money is `BigDecimal`. A binary float cannot represent `0.10`
exactly, so the legacy system has been carrying a small error for as long as it has been
running.

Migrating to `BigDecimal` makes the new code **more correct** and therefore in
disagreement with the recorded values. Expect characterization replays of money to differ
in the last decimal place, and read that difference as the legacy error rather than a
migration defect. Say so in a comment where it happens.

Every `BigDecimal.divide` must name a scale and a `RoundingMode`: Java throws on a
non-terminating result, and which rounding applies is a business decision, not a default.
