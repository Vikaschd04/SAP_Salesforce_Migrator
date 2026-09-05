"""Things the platform calls, rather than things your code calls. [1.34, 3.4]

Three Magento constructs land here, and all three are *invoked by the framework* rather
than by a caller you can see. That is what makes them easy to convert wrongly: the
signature ports cleanly and the invocation semantics do not.

**Plugins.** Magento wraps a method with `before` / `around` / `after`. Hybris has two
different answers and picking the wrong one loses behaviour silently:

- an **interceptor** runs alongside a model operation and cannot replace it. It cannot
  decline to proceed. Cheap, idiomatic, and wrong for any plugin that might not call
  `$proceed`.
- a **decorator** implements the same interface, holds the original, and decides whether
  to call it. It can express everything an interceptor can, and skipping too.

`hybris_plan` makes that call from `di.xml`, which says which plugins may skip. This
module writes whichever it chose.

**Observers.** A Magento observer is called synchronously, in `sortOrder`, and it mutates
the event payload in place so later observers see the change. Hybris `EventService`
publishes **asynchronously and unordered** by default. A literal port compiles, registers,
fires — and runs after the code that was waiting for it, in an order nobody chose. That is
not a caveat to add later; it is the first thing the generated class says.

Bodies are left as TODO, exactly as `hybris_service` leaves them: signatures, wiring and
documentation are *derived*, logic is *generated and reviewed*, and the output keeps those
two things distinguishable.
"""

from __future__ import annotations

import re

from src.adapters import java_bodies
from src.adapters.hybris_extension import pascal
from src.adapters.hybris_service import _javadoc, _public_methods, service_name

#: Magento plugin prefixes and what each one is doing to the wrapped call.
_PREFIXES = ("before", "around", "after")


def wrapped_method(name: str) -> str:
    """`beforeCollect` → `collect`. The method the plugin is wrapping."""
    for pre in _PREFIXES:
        if name.startswith(pre) and len(name) > len(pre):
            rest = name[len(pre):]
            return rest[:1].lower() + rest[1:]
    return name


def _prefix_of(name: str) -> str:
    for pre in _PREFIXES:
        if name.startswith(pre) and len(name) > len(pre):
            return pre
    return ""


def _target_type(unit, wiring: dict) -> str:
    """The Magento class this plugin was declared against, from `di.xml`."""
    fqn = (getattr(unit, "extra", None) or {}).get("fqn", "")
    for p in ((wiring or {}).get("plugins") or []):
        ptype = p.get("type", "")
        if ptype == fqn or ptype.endswith(f"\\{unit.name}"):
            # `on` is the `<type name="...">` the plugin was declared inside — the class
            # Magento wraps, and therefore the thing a decorator has to implement.
            return p.get("on", "") or ""
    return ""


def _short(fqn: str) -> str:
    return (fqn or "").replace("\\", ".").split(".")[-1]


# ── decorator ─────────────────────────────────────────────────────────────────

def build_decorator(unit, package: str, wiring: dict | None = None,
                    emitted_services: set | None = None,
                    bodies: dict | None = None) -> str:
    """A decorator: holds the original and decides whether to call it. [1.34]

    Only where there *is* an original to hold. Magento lets a plugin wrap a method on any
    class, including its own model classes; Hybris has no equivalent for a platform
    model's method. When the wrapped type is not something this migration emitted, the
    class is written without an `implements` clause and says why — declaring
    `implements OrderService` for an interface nobody wrote produces a file that names a
    type that will never exist, which the static checker rightly rejects.
    """
    name = f"{pascal(unit.name)}Decorator"
    raw = _target_type(unit, wiring or {})
    target = _short(raw)
    iface = service_name(target) if target else ""
    wrappable = bool(iface) and iface in (emitted_services or set())

    out = [f"package {package}.decorators;", ""]
    if wrappable:
        # It sits in `.decorators` and implements a type in `.service`. Same omission the
        # DAOs had in 1.37: the name resolves, the file does not compile. [1.45]
        out += [f"import {package}.service.{iface};", ""]
    out += ["/**",
           f" * Migrated from the Adobe Commerce plugin {unit.name}"
           f" ({getattr(unit, 'file', '')}).",
           " *"]
    if wrappable:
        out += [f" * Declared in di.xml against {raw}, which this migration emits as",
                f" * {iface} — so that is what this decorates.",
                " *"]
    elif target:
        out += [f" * Declared in di.xml against {raw}.",
                " *",
                " * THIS ONE HAS NO DIRECT EQUIVALENT AND CANNOT BE WIRED AS WRITTEN.",
                " *",
                f" * `{raw}` is not a type this migration emits — it is a platform class.",
                " * Magento lets a plugin wrap a method on any class, including the",
                " * platform's own models. Hybris does not: an interceptor can run",
                " * alongside a model's *persistence*, but nothing can replace a method on",
                " * a platform model, and this plugin needs to replace one because it can",
                " * decline to proceed.",
                " *",
                " * So the logic below has to find a different home — the service that",
                " * calls this operation, or the callers themselves. That is a design",
                " * decision, and it is stated here rather than resolved by generating a",
                " * class that implements an interface nobody will ever write.",
                " *"]
    else:
        out += [" * The di.xml entry naming what this plugin wraps was not readable, so",
                " * what it decorates is unknown. Resolve it before wiring: a decorator",
                " * that wraps nothing is never injected anywhere, and nothing will",
                " * report that it is doing nothing.",
                " *"]
    out += [" * A decorator rather than an interceptor because this plugin can decline to",
            " * call the original. An interceptor runs alongside an operation and cannot",
            " * replace it, so it cannot express skipping at all.",
            " *"]
    if wrappable:
        out += [f" * TO FINISH: declare `implements {iface}` and implement every method on",
                " * it, delegating the ones this plugin does not touch. The methods below",
                " * are the *plugin's* — they are where its behaviour was — and they do not",
                " * match the wrapped interface's signatures, so the clause is left off",
                " * rather than emitted as a claim the class does not meet.",
                " *"]
    out += [" */"]
    if wrappable:
        # Typed delegate, but *no* `implements` clause. A Hybris decorator must implement
        # the whole interface, and the methods here are the plugin's — `beforeCollect`,
        # `aroundGetGrandTotal` — not the wrapped type's. Declaring `implements` produced
        # a class that did not override anything and would not compile, which turned a
        # piece of honest scaffolding into a build failure. The clause is left off and the
        # remaining work is stated. [1.45]
        out += [f"public class {name}", "{",
                f"    private {iface} delegate;", ""]
    else:
        out += [f"public class {name}", "{", ""]

    for m in _public_methods(unit):
        mname = getattr(m, "name", "")
        pre = _prefix_of(mname)
        wrapped = wrapped_method(mname)
        out += _javadoc(getattr(m, "doc", ""))
        if pre == "before":
            out.append(f"    // `{mname}` adjusted the arguments and then let the call "
                       "proceed.")
        elif pre == "after":
            out.append(f"    // `{mname}` adjusted the *result* of the call.")
        elif pre == "around":
            out.append(f"    // `{mname}` wrapped the call and could return without "
                       "making it.")
        # No `@Override`: there is no `implements` clause for it to refer to, and there
        # cannot be until the wrapped interface is implemented in full. [1.45]
        out += [f"    public Object {wrapped}(final Object... args)", "    {"]
        generated = (bodies or {}).get(mname)
        if generated is not None and not java_bodies.is_stub(generated):
            # Keyed on the *source* method name: the emitter renames `getTotal` to
            # `beforeGetTotal` to match the platform's hook convention, and the model was
            # asked about `getTotal`. [1.48]
            out.append(f"        // Generated from {unit.name}::{mname}. Reviewed as"
                       " generated logic, not derived — see PROVENANCE.md.")
            if wrappable:
                out.append(f"        // Delegation is still yours to decide:"
                           f" delegate.{wrapped}(args)")
            out += java_bodies.indent(generated)
        else:
            out += [f"        // TODO migrate: {unit.name}::{mname}",
                    ("        // Decide explicitly whether this path delegates:"
                     if wrappable else
                     "        // There is no delegate — see the class comment."),
                    (f"        //     return delegate.{wrapped}(args);" if wrappable else
                     "        // This logic needs a home on the target; it has none yet."),
                    "        throw new UnsupportedOperationException("
                    f'"Not migrated yet: {mname}");']
        out += ["    }", ""]

    if wrappable:
        out += [f"    public void setDelegate(final {iface} delegate)", "    {",
                "        this.delegate = delegate;", "    }"]
    out += ["}", ""]
    return "\n".join(out)


# ── interceptor ───────────────────────────────────────────────────────────────

#: Magento prefix → the Hybris interceptor that runs at the same moment. `after` has no
#: exact counterpart: Magento's `after` sees the *return value*, and an interceptor sees
#: the model. Mapped to Prepare with that difference stated rather than hidden.
_INTERCEPTOR_FOR = {
    "before": ("PrepareInterceptor", "onPrepare",
               "runs before the model is written, and may modify it"),
    "after": ("PrepareInterceptor", "onPrepare",
              "runs before the model is written — Magento's `after` saw the method's "
              "return value, which an interceptor never sees, so anything derived from "
              "that return value has to be recomputed from the model here"),
    "around": ("ValidateInterceptor", "onValidate",
               "runs before the model is written and may reject it by throwing"),
}


def build_interceptor(unit, package: str, wiring: dict | None = None) -> str:
    """An interceptor: runs alongside a model operation, and cannot replace it. [1.34]"""
    name = f"{pascal(unit.name)}Interceptor"
    target = _short(_target_type(unit, wiring or {})) or "TODO_ItemType"

    methods = _public_methods(unit)
    kinds = {_prefix_of(getattr(m, "name", "")) for m in methods}
    kind, hook, when = _INTERCEPTOR_FOR.get(
        next((k for k in ("around", "before", "after") if k in kinds), "before"),
        _INTERCEPTOR_FOR["before"])

    out = [f"package {package}.interceptors;", "",
           "import de.hybris.platform.servicelayer.interceptor.InterceptorContext;",
           "import de.hybris.platform.servicelayer.interceptor.InterceptorException;",
           f"import de.hybris.platform.servicelayer.interceptor.{kind};", "", "/**",
           f" * Migrated from the Adobe Commerce plugin {unit.name}"
           f" ({getattr(unit, 'file', '')}).",
           " *",
           f" * An interceptor rather than a decorator because this plugin always calls",
           " * the original — di.xml shows no path that skips it — so the cheaper and more",
           " * idiomatic form expresses it exactly.",
           " *",
           f" * {kind} {when}.",
           " *",
           " * Registered against a *type*, not a method: an interceptor fires for every",
           " * save of this item type, wherever that save came from. The Magento plugin",
           " * fired only for the method it wrapped, so this runs strictly more often.",
           " * Anything conditional in the original has to become an explicit condition",
           " * here.",
           " */",
           f"public class {name} implements {kind}", "{", ""]

    for m in methods:
        out += _javadoc(getattr(m, "doc", ""))
        out.append(f"    // from {unit.name}::{getattr(m, 'name', '')}")

    out += ["    @Override",
            f"    public void {hook}(final Object model, final InterceptorContext ctx)",
            "            throws InterceptorException", "    {",
            f"        // TODO migrate: {unit.name}",
            "        throw new UnsupportedOperationException("
            f'"Not migrated yet: {unit.name}");',
            "    }", "}", ""]
    return "\n".join(out)


# ── event listener ────────────────────────────────────────────────────────────

_EVENT_CLASS = re.compile(r"[^A-Za-z0-9]+")


def event_class_for(event_name: str) -> str:
    """`sales_order_place_after` → `SalesOrderPlaceAfterEvent`."""
    parts = [p for p in _EVENT_CLASS.split(event_name or "") if p]
    return "".join(pascal(p) for p in parts) + "Event" if parts else "TODO_Event"


def build_event(event_name: str, package: str) -> str:
    """The event class itself. Magento events are name-keyed; Hybris events are types.

    Magento dispatches on a *string*, so an observer binds to `sales_order_place_after`
    and any code anywhere can raise it. Hybris dispatches on a *class*. There is no way
    to keep the string binding, so the event becomes a type — which means every publisher
    has to be found and changed too, and a publisher that is missed simply never fires.
    """
    cls = event_class_for(event_name)
    return "\n".join([
        f"package {package}.events;", "",
        "import de.hybris.platform.servicelayer.event.events.AbstractEvent;", "", "/**",
        f" * The Adobe Commerce event `{event_name}`, as a Hybris event type.",
        " *",
        " * Magento dispatched this by *name*, so any code could raise it without",
        " * declaring anything. Hybris dispatches by type. Every place that raised",
        f" * `{event_name}` has to publish this class instead — one that is missed does",
        " * not fail, it just never fires again.",
        " */",
        f"public class {cls} extends AbstractEvent", "{",
        "    private final Object payload;", "",
        f"    public {cls}(final Object payload)", "    {",
        "        this.payload = payload;", "    }", "",
        "    public Object getPayload()", "    {",
        "        return payload;", "    }", "}", ""])


def build_event_listener(unit, package: str, event_name: str = "") -> str:
    """`AbstractEventListener<T>` for a Magento observer. [1.34]"""
    name = f"{pascal(unit.name)}Listener"
    # An unmatched observer used to extend `TODO_Event`, a type that does not exist —
    # so a *finding* became a compile error, and the reviewer's attention went to the
    # wrong place. It extends the platform's own base event instead, and the class
    # comment says the binding is unknown. [1.45]
    cls = event_class_for(event_name) if event_name else "AbstractEvent"

    out = [f"package {package}.listeners;", "",
           "import de.hybris.platform.servicelayer.event.impl.AbstractEventListener;", ""]
    if event_name:
        out += [f"import {package}.events.{cls};", ""]
    else:
        out += ["import de.hybris.platform.servicelayer.event.events.AbstractEvent;", ""]
    out += ["/**",
            f" * Migrated from the Adobe Commerce observer {unit.name}"
            f" ({getattr(unit, 'file', '')}).",
            " *"]
    if event_name:
        out.append(f" * Bound to `{event_name}` in events.xml.")
        out.append(" *")
    else:
        out += [" * NO EVENT BINDING WAS FOUND for this observer in events.xml, so what",
                " * publishes it is unknown and the base event type stands in. Bind it to a",
                " * real event before wiring: a listener on the base type receives every",
                " * event the platform raises.",
                " *"]
    out += [" * TWO THINGS CHANGED, AND NEITHER FAILS LOUDLY:",
            " *",
            " * 1. Magento called observers synchronously, so the code that dispatched the",
            " *    event waited for this to finish. Hybris EventService publishes",
            " *    asynchronously by default: the dispatcher no longer waits, and anything",
            " *    downstream that assumed this had already run will read stale state.",
            " *    Make the publication synchronous, or stop depending on the ordering.",
            " *",
            " * 2. Magento ran observers in `sortOrder`, and each one saw the previous",
            " *    one's changes because the payload was mutated in place. Hybris gives no",
            " *    ordering guarantee between listeners on the same event. If this",
            " *    observer depended on running after another, that dependency is gone",
            " *    and nothing will report it.",
            " */",
            f"public class {name} extends AbstractEventListener<{cls}>", "{", "",
            "    @Override",
            f"    protected void onEvent(final {cls} event)", "    {"]
    for m in _public_methods(unit):
        out.append(f"        // TODO migrate: {unit.name}::{getattr(m, 'name', '')}")
    out += ["        throw new UnsupportedOperationException("
            f'"Not migrated yet: {unit.name}");',
            "    }", "}", ""]
    return "\n".join(out)


# ── spring wiring ─────────────────────────────────────────────────────────────

def spring_fragments(rows: list, package: str) -> list:
    """Bean definitions for everything this module emits.

    Each `row` is `{kind, name, unit, type_code, event}`. Emitted as fragments rather
    than a document so `hybris_emit` keeps owning the file.
    """
    out: list[str] = []
    for r in rows or []:
        kind, name = r.get("kind"), r.get("name", "")
        bean = name[:1].lower() + name[1:]
        if kind == "decorator":
            out += [f'    <!-- {name}: wraps the original and decides whether to call it. -->',
                    f'    <bean id="{bean}" class="{package}.decorators.{name}">',
                    f'        <property name="delegate" ref="TODO_originalBean"/>',
                    "    </bean>", ""]
        elif kind == "interceptor":
            out += [f'    <bean id="{bean}" class="{package}.interceptors.{name}"/>',
                    f'    <bean id="{bean}Mapping"',
                    '          class="de.hybris.platform.servicelayer.interceptor.impl'
                    '.InterceptorMapping">',
                    f'        <property name="interceptor" ref="{bean}"/>',
                    f'        <property name="typeCode" value="{r.get("type_code") or "TODO_ItemType"}"/>',
                    "    </bean>", ""]
        elif kind == "event-listener":
            out += [f'    <!-- Fires on {r.get("event") or "TODO_Event"}. Asynchronous and'
                    " unordered unless made otherwise. -->",
                    f'    <bean id="{bean}" class="{package}.listeners.{name}"'
                    ' parent="abstractEventListener"/>', ""]
    return out
