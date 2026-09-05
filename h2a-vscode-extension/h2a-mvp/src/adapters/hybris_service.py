"""
hybris_service.py — PHP units as Spring services a Hybris developer recognises. [3.2, 3.3]

Split by what is *known* versus what has to be decided, because those want different
machinery and mixing them is how a generator starts inventing:

  deterministic   the package, the imports, the interface, every method signature, the
                  Spring bean, the DAO's FlexibleSearch constants, and the javadoc —
                  which is carried verbatim from the PHP docblock rather than rewritten,
                  since on a dynamically typed source it is often the only statement of
                  what the method is *for*
  a model's job   the method bodies, and only those

**Not decided here.** Which *kind* of target each unit becomes is `plan()`'s job (3.2's
remaining half). Today every unit offered to `build_interface` is rendered as a service,
which is right for a Model and wrong for a Plugin — a Magento plugin should become a
Hybris interceptor or a decorator bean, and the AROUND_PLUGIN hazard already says which.
Rendering a `SubtotalPluginService` is a placeholder for that decision, not the decision.

A signature is not a guess: item 2.12 resolved every type from a declaration or refused,
so a parameter arriving here without a type is one nobody declared. Those do not get an
invented Java type — the method is emitted with the gap marked, and the unit is already
in must-review because triage forces it.

**On `float`.** PHP money is a float, and Java money should be BigDecimal. This maps
`float` to `Double` anyway — faithfully, to what the source declared. Silently promoting
it would change arithmetic the recorded behaviours were measured against, and the
migration would disagree with its own characterization for a reason nobody could see. The
`FLOAT_MONEY` hazard already says the promotion is needed and that it is a decision; that
is the honest place for it.
"""

from __future__ import annotations

import re

from src.adapters.hybris_extension import pascal

#: Resolved IR types → Java. Deliberately the same table the items.xml emitter uses, so a
#: field and the method that returns it cannot disagree about what a decimal is.
_JAVA = {
    "String": "String", "Integer": "Integer", "Long": "Long", "Double": "Double",
    "BigDecimal": "java.math.BigDecimal", "Boolean": "Boolean",
    "Date": "java.util.Date", "DateTime": "java.util.Date", "List": "java.util.List<?>",
    "void": "void",
}

#: A parameter or return nobody declared. Emitted so it cannot be missed and cannot compile
#: by accident — the unit is in must-review regardless (2.12), and this is the marker a
#: developer greps for.
UNRESOLVED = "/* TYPE-UNRESOLVED */ Object"


def java_type(ir_type: str) -> str:
    if not ir_type:
        return UNRESOLVED
    return _JAVA.get(ir_type, pascal(ir_type) if "_" in ir_type else ir_type)


def _camel(name: str) -> str:
    """`applySpendDiscount` is already Java's convention; `apply_spend` is not."""
    parts = re.split(r"_+", name or "")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def service_name(unit_name: str) -> str:
    """`PricingService` stays; `AwardPointsObserver` becomes `AwardPointsObserverService`.

    Appending unconditionally produced `PricingServiceService`, which is the kind of
    detail that makes generated code read as generated.

    The trailing `Interface` is stripped *here* rather than by the caller. `hybris_plan`
    stripped it before asking for a name while the emitters asked with the raw unit name,
    so `LoyaltyAccountInterface` was written into `LoyaltyAccountService.java` as
    `interface LoyaltyAccountInterfaceService` — a file whose name and whose class do not
    match, which Java rejects outright. Two derivations of one name is the bug; this is
    the one. [1.38]
    """
    base = unit_name or ""
    if base.endswith("Interface") and len(base) > len("Interface"):
        base = base[: -len("Interface")]
    n = pascal(base)
    return n if n.endswith("Service") else f"{n}Service"


def _javadoc(doc: str, indent: str = "    ") -> list:
    """The PHP docblock, carried across rather than rewritten.

    A model asked to "summarise this docblock" produces something shorter and less true.
    The original is already in the target's comment syntax — `/** ... */` is the same in
    both languages — so the honest transformation is none at all.
    """
    if not doc:
        return []
    out = []
    for i, ln in enumerate(doc.strip().splitlines()):
        s = ln.strip()
        # Continuation lines align their `*` under the second character of `/**`, which is
        # what every Java formatter does and what makes the block read as one comment.
        out.append(f"{indent}{s}" if i == 0 else f"{indent} {s}")
    return out


def _signature(m, types: dict, renames: dict | None = None,
               source_names: set | None = None, models: set | None = None) -> tuple:
    """`(java_signature, unresolved_names)` for one method."""
    unresolved = []

    ret_ir = types.get(f"{m.name}()", "")
    ret = _rename(java_type(ret_ir), renames, source_names, models)
    if ret == UNRESOLVED:
        unresolved.append("return")

    params = []
    for p in getattr(m, "parameters", None) or []:
        ir_t = types.get(f"{m.name}(${p.get('name', '')})", "")
        jt = _rename(java_type(ir_t), renames, source_names, models)
        if jt == UNRESOLVED:
            unresolved.append(p.get("name", "?"))
        params.append(f"{jt} {_camel(p.get('name', 'arg'))}")

    return f"{ret} {_camel(m.name)}({', '.join(params)})", unresolved


def _rename(java: str, renames: dict | None, source_names: set | None = None,
            models: set | None = None) -> str:
    """A signature naming another *source* class must name what that class became. [1.38]

    `LoyaltyAccountRepository::getByCode()` returns a `LoyaltyAccountInterface`, which
    this migration converts into `LoyaltyAccountService`. Emitted unchanged the signature
    named a PHP interface that no longer exists anywhere, and the file did not compile —
    invisible to the static rung, which had `LoyaltyAccountInterface` in its known set
    because the *source* declared it.

    Anything that is neither a migrated type nor a type the target platform has becomes
    `UNRESOLVED`, which renders as `Object` with a comment saying a decision is owed.
    Passing it through instead put *Magento framework* classes into Java signatures —
    `Redirect`, `RequestInterface`, `ResolveInfo` — types that will never exist on Hybris.
    On a real third-party module that was 28 unresolvable references across 8 files, and
    the emitter had produced every one of them confidently. A type the migration cannot
    map is a decision for a person, and the generated code should say so rather than
    name something imaginary. [1.40]
    """
    mapped = (renames or {}).get(java)
    if mapped:
        return mapped
    # A name the *source* declares means the source's class, whatever Java happens to
    # call something similar. `Collection` is `java.util.Collection` in the JDK list and
    # `Model\ResourceModel\WhitelistEntry\Collection` in the module being migrated —
    # and it was resolving to the JDK one, producing `Collection getCollection()` with no
    # import and no such type. If it were converted it would be in `renames`; reaching
    # here means it was not. [1.45]
    if java in (source_names or set()):
        return UNRESOLVED
    return java if _is_available(java, models) else UNRESOLVED


def _is_available(java: str, models: set | None = None) -> bool:
    """Will this type exist on the target once the extension is built?"""
    if not java or java == UNRESOLVED:
        return False
    bare = java.split("<")[0].rsplit(".", 1)[-1]
    if java in _JAVA.values() or bare in _JAVA:
        return False if bare not in _JAVA and java not in _JAVA.values() else True
    from src.adapters.java_static_check import PLATFORM_TYPES, _JDK

    if bare in PLATFORM_TYPES or bare in _JDK:
        return True
    # `endswith("Model")` was standing in for "the platform generates this from
    # items.xml". It also matched `AbstractModel`, `ResourceModel` and every other
    # Magento framework class ending the same way, which then reached the output as Java
    # types nothing declares. Only the models this migration actually generates count,
    # and the caller knows which those are. [1.45]
    if models is not None:
        return bare in models
    return bare.endswith("Model")


def _types_for(unit, resolutions: list) -> dict:
    """`{"method()": ir_type, "method($p)": ir_type}` for one unit, from 2.12's output."""
    prefix = f"{unit.name}::"
    return {r["where"][len(prefix):]: r["type"]
            for r in resolutions if r["where"].startswith(prefix)}


def _public_methods(unit) -> list:
    return [m for m in (getattr(unit, "methods", None) or [])
            if getattr(m, "visibility", "public") == "public"
            and not m.name.startswith("__")]


def build_interface(unit, package: str, resolutions: list,
                    renames: dict | None = None, name: str | None = None,
                    source_names: set | None = None,
                    models: set | None = None) -> str:
    """The service contract. Every signature is derived; none is invented. [3.2]

    `name` is the planner's own target name, and passing it is the point: the file is
    written as `<target_name>.java` while this used to re-derive the class name from the
    unit. 1.38 made the two derivations agree; they came apart again the moment the
    planner qualified a name to tell two same-named classes apart, and Java rejects a
    public type whose name does not match its file. One derivation, handed down. [1.40]
    """
    name = name or service_name(unit.name)
    types = _types_for(unit, resolutions)
    out = [f"package {package}.service;", ""]

    doc = (getattr(unit, "extra", None) or {}).get("doc", "")
    out += _javadoc(doc, "") or [
        "/**", f" * Migrated from the Adobe Commerce class {unit.name}.", " */"]
    out += [f"public interface {name}", "{"]

    for m in _public_methods(unit):
        sig, unresolved = _signature(m, types, renames, source_names, models)
        out += [""]
        out += _javadoc(getattr(m, "doc", ""))
        if unresolved:
            out.append(f"    // TYPE-UNRESOLVED: {', '.join(unresolved)} — no declaration "
                       "in the source resolved this. Decide before implementing.")
        out.append(f"    {sig};")

    out += ["}", ""]
    return "\n".join(out)


def build_implementation(unit, package: str, resolutions: list,
                         renames: dict | None = None, name: str | None = None,
                    source_names: set | None = None,
                    models: set | None = None) -> str:
    """The Spring service. Signatures derived; bodies left for the Builder. [3.2]

    See `build_interface` on `name`: the planner owns it, and re-deriving it here is what
    put `class DefaultIndexService` inside `DefaultAdminhtmlIndexService.java`. [1.40]
    """
    iface = name or service_name(unit.name)
    name = f"Default{iface}"
    types = _types_for(unit, resolutions)

    # Every migrated type this class names, not just its own interface. The
    # implementation sits in `.service.impl` and the types it returns sit in `.service`,
    # so one import is not enough — and the missing ones are invisible until a compiler
    # looks, because the *names* all resolve. [1.38]
    referenced = {iface}
    for m in _public_methods(unit):
        sig, _ = _signature(m, types, renames, source_names, models)
        for word in re.findall(r"\b[A-Z]\w*\b", sig):
            if word in (renames or {}).values():
                referenced.add(word)

    out = [f"package {package}.service.impl;", ""]
    out += [f"import {package}.service.{n};" for n in sorted(referenced)]
    out += ["",
           "/**",
           f" * Migrated from the Adobe Commerce class {unit.name}"
           f" ({getattr(unit, 'file', '')}).",
           " *",
           " * Method bodies are not translated here — the signatures, the wiring and the",
           " * documentation are derived from the source; the logic is generated and",
           " * reviewed separately, so that what was *known* and what was *decided* stay",
           " * distinguishable in the output.",
           " */",
           f"public class {name} implements {iface}", "{"]

    for m in _public_methods(unit):
        sig, unresolved = _signature(m, types, renames, source_names, models)
        ret = sig.split(" ", 1)[0]
        out += ["", "    @Override"]
        if unresolved:
            out.append(f"    // TYPE-UNRESOLVED: {', '.join(unresolved)}")
        out += [f"    public {sig}", "    {",
                f"        // TODO migrate: {unit.name}::{m.name}"]
        if ret != "void":
            out.append("        throw new UnsupportedOperationException("
                       f'"Not migrated yet: {m.name}");')
        out.append("    }")

    out += ["}", ""]
    return "\n".join(out)


def build_spring_beans(units: list, package: str, extension: str) -> str:
    """`<extension>-spring.xml` wiring every emitted service. [3.2]"""
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<beans xmlns="http://www.springframework.org/schema/beans"',
           '       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
           '       xsi:schemaLocation="http://www.springframework.org/schema/beans',
           '       http://www.springframework.org/schema/beans/spring-beans.xsd">', ""]
    for u in units:
        iface = service_name(u.name)
        bean = iface[:1].lower() + iface[1:]
        out += [f'    <alias name="default{iface}" alias="{bean}"/>',
                f'    <bean id="default{iface}"',
                f'          class="{package}.service.impl.Default{iface}"/>', ""]
    out += ["</beans>", ""]
    return "\n".join(out)


# ── 3.3 · DAO with FlexibleSearch ─────────────────────────────────────────────

#: Where the platform build puts the model classes it generates from `items.xml` —
#: `<packageroot>.model`, which `extensioninfo.xml` declares as `packageroot`. Named here
#: because two emitters and the stub tree all have to agree on it. [1.37]
MODEL_PACKAGE = "model"


def build_dao_interface(data_type, package: str) -> str:
    """The DAO's contract. [3.3]

    The implementation declared `implements <Item>Dao` from the start and this did not
    exist, so every generated DAO named an interface nothing emitted — a Hybris build
    fails on that. Found by the static check in 3.10, which is the first thing that ever
    read the generated Java rather than the code that wrote it.
    """
    item = pascal(getattr(data_type, "code", ""))
    attrs = list(getattr(data_type, "attributes", None) or [])
    unique = [a.get("name", "") for a in attrs if a.get("unique")]
    finders = unique or [a.get("name", "") for a in attrs[:1]]

    # The model class is generated by the platform build into `<packageroot>.model`,
    # which is a different package from this one — so it has to be imported. It was not,
    # and the static rung could not see that: it resolves a *name* against a known set,
    # and the name was known. `javac` rejects every method that returns one. [1.37]
    out = [f"package {package}.daos;", "",
           f"import {package}.{MODEL_PACKAGE}.{item}Model;", "", "/**",
           f" * Queries for {item}, migrated from the Adobe Commerce table"
           f" `{getattr(data_type, 'code', '')}`.", " */",
           f"public interface {item}Dao", "{"]
    for q in finders:
        out += ["", f"    {item}Model findBy{pascal(q)}(final String {_camel(q)});"]
    out += ["}", ""]
    return "\n".join(out)


def build_dao(data_type, package: str) -> str:
    """A DAO shaped the way a Hybris developer writes one. [3.3]

    The queries are constants, parameterised, and bounded — every one of which is a habit
    the Hybris radar's own rules exist to enforce on the way *in*. Emitting a DAO that
    trips our own hazard rules would be an odd thing to do, so `setCount(1)` is there:
    QUERY_NO_LIMIT would otherwise fire on our own output.
    """
    item = pascal(getattr(data_type, "code", ""))
    name = f"{item}Dao"
    attrs = [a.get("name", "") for a in (getattr(data_type, "attributes", None) or [])]
    unique = [a.get("name", "") for a in (getattr(data_type, "attributes", None) or [])
              if a.get("unique")]

    out = [f"package {package}.daos.impl;", "",
           f"import {package}.daos.{item}Dao;",
           f"import {package}.{MODEL_PACKAGE}.{item}Model;",
           "import java.util.List;",
           "import de.hybris.platform.servicelayer.search.FlexibleSearchQuery;",
           "import de.hybris.platform.servicelayer.search.FlexibleSearchService;", "",
           "/**",
           f" * Queries for {item}, migrated from the Adobe Commerce table"
           f" `{getattr(data_type, 'code', '')}`.",
           " */",
           f"public class Default{name} implements {name}", "{", ""]

    for q in unique or attrs[:1]:
        const = re.sub(r"(?<!^)(?=[A-Z])", "_", pascal(q)).upper()
        out += [f'    private static final String BY_{const} =',
                f'            "SELECT {{i:pk}} FROM {{{item} AS i}} WHERE {{i:{q}}} = ?{_camel(q)}";',
                ""]

    out += ["    private FlexibleSearchService flexibleSearchService;", ""]

    for q in unique or attrs[:1]:
        const = re.sub(r"(?<!^)(?=[A-Z])", "_", pascal(q)).upper()
        out += [f"    public {item}Model findBy{pascal(q)}(final String {_camel(q)})",
                "    {",
                f"        final FlexibleSearchQuery query = new FlexibleSearchQuery(BY_{const});",
                f'        query.addQueryParameter("{_camel(q)}", {_camel(q)});',
                "        query.setCount(1);",
                f"        final List<{item}Model> results ="
                f" flexibleSearchService.<{item}Model>search(query).getResult();",
                "        return results.isEmpty() ? null : results.get(0);",
                "    }", ""]

    out += ["    public void setFlexibleSearchService("
            "final FlexibleSearchService flexibleSearchService)",
            "    {", "        this.flexibleSearchService = flexibleSearchService;",
            "    }", "}", ""]
    return "\n".join(out)
