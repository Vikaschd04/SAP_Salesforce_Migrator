# Plugins: interceptor or decorator

The single most consequential routing decision in this migration.

## What Magento allows

```php
public function aroundGetGrandTotal(Order $subject, callable $proceed)
{
    if ($this->fullyCoveredByPoints($subject)) {
        return 0.0;          // $proceed is never called
    }
    return $proceed();
}
```

An `around` plugin may **decline to call the original method**. The original never runs.

## What Hybris allows

An interceptor runs *alongside* a persistence operation — `onValidate`, `onPrepare`. It
can inspect, it can modify, it can throw to abort the save. It **cannot replace the
operation**, and there is no `$proceed` to withhold.

So:

| Magento | Hybris | Why |
|---|---|---|
| `before` / `after` | interceptor (`PrepareInterceptor`, `ValidateInterceptor`) | runs alongside; that is what these did |
| `around` that always calls `$proceed` | interceptor | the pass-through is expressible |
| **`around` that can skip `$proceed`** | **decorator bean** | only a decorator can decline to delegate |

## The decorator

A Spring bean that wraps the original, registered in its place:

```xml
<alias name="acmeOrderTotalDecorator" alias="orderTotalStrategy"/>
<bean id="acmeOrderTotalDecorator" class="com.acme.loyalty.decorator.OrderTotalDecorator">
    <property name="delegate" ref="defaultOrderTotalStrategy"/>
</bean>
```

```java
public BigDecimal getGrandTotal(final OrderModel order)
{
    if (fullyCoveredByPoints(order)) {
        return BigDecimal.ZERO;      // the delegate is not called — the whole point
    }
    return delegate.getGrandTotal(order);
}
```

## Why getting it wrong is quiet

Convert a skipping `around` into an interceptor and the generated code **always calls
through**. It compiles, it deploys, nothing in review looks odd, and a business rule that
could short-circuit an order total silently stops being able to. Nobody finds it until
someone notices the totals.
