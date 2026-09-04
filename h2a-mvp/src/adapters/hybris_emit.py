"""
hybris_emit.py — assembling one extension from every part. [3.1–3.6]

The pieces were built and tested separately; this is where they have to agree. Assembly is
where a generator's mistakes stop being local: a service that references a DAO interface
nobody emitted, a Spring bean pointing at a class in the wrong package, a job whose
performable is named one thing in Java and another in ImpEx. None of those are visible
while testing an emitter on its own, and all of them are fatal to a build.

So this does two things beyond writing files. It routes each planned target to the emitter
its **kind** calls for — a decorator is not a service and must not be written as one — and
it hands the whole result to the static checker, which is the only thing that reads the
output rather than the code producing it.

Kinds with no emitter yet return a `manual` row rather than nothing. A target that is
planned and then silently not written is exactly the shape of loss the completeness ledger
exists to make impossible, and assembly is the easiest place in the system to introduce it.
"""

from __future__ import annotations

from pathlib import Path

from src.adapters import hybris_data, hybris_extension, hybris_hooks, hybris_service
from src.adapters.hybris_plan import (DAO, DATA, DECORATOR, EVENT_LISTENER,
                                      INTERCEPTOR, JOB, SERVICE)

#: Kinds assembly writes today — services and DAOs through the target loop, jobs through
#: their own path, because a job is joined to a crontab entry the target list does not
#: carry. Everything else is planned, reported, and left to a human with the reason.
#:
#: `DATA` is here without an emitter of its own: a Magento data patch *is* the data model,
#: and `build_items_xml` already wrote its EAV attributes onto the platform type they
#: extend. Listing it as unwritten claimed a loss that had not happened — the mirror of
#: the failure this set exists to prevent. [1.34]
EMITTABLE = {SERVICE, DAO, JOB, DATA, DECORATOR, INTERCEPTOR, EVENT_LISTENER}


def _pkg_dir(root: Path, package: str, *parts: str) -> Path:
    return root.joinpath(*package.split("."), *parts)


def emit_extension(output_dir: str, *, name: str, package: str, source_model,
                   targets: list) -> dict:
    """Write the whole extension. Returns `{created, manual, static}`.

    `static` is the checker's verdict on what was actually written, which is the closest
    thing to a compiler available without a licensed platform.
    """
    created = list(hybris_extension.build_extension(
        output_dir, name=name, package=package, data_model=source_model.data_model))

    root = Path(output_dir) / "hybris" / "bin" / "custom" / name
    src = root / "src"
    resources = root / "resources"
    resolutions = (getattr(source_model, "extra", None) or {}).get("type_resolutions", [])
    units_by_name = {u.name: u for u in (getattr(source_model, "units", None) or [])}

    def write(path: Path, body: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        created.append(str(path))

    # What each source class became, so a signature naming one names its migrated form.
    # Built from the plan rather than guessed, and including the `Interface` twin that
    # `_merge` folded away — the repository's methods return that twin by name. [1.38]
    renames: dict = {}
    for t_row in targets or []:
        for c in t_row.get("source_classes", []):
            src_name = c.get("class_name")
            if src_name and t_row.get("target_name"):
                renames[src_name] = t_row["target_name"]

    services, manual = [], []
    #: source class name -> the path this migration actually wrote for it, relative to
    #: the extension root. The ledger named files by convention (`<target>.java`) and so
    #: reported `AddLoyaltyAttributes.java` for a data patch whose content went into
    #: items.xml — the right outcome under an invented filename. The emitter is the only
    #: thing that knows. [1.35]
    emitted_as: dict = {}

    for t in targets or []:
        kind = t.get("kind")
        sources = [units_by_name[c["class_name"]] for c in t.get("source_classes", [])
                   if c.get("class_name") in units_by_name]
        if kind != SERVICE or not sources:
            # Jobs and DAOs are written, just not here — they are joined to a crontab
            # entry and to the data model respectively, neither of which the target list
            # carries. Listing them as manual would understate what the run produced,
            # which is the same kind of lie as overstating it.
            if kind == DATA:
                # A data patch *is* the data model; its attributes were written onto the
                # types they extend, inside items.xml.
                for c in t.get("source_classes", []):
                    if c.get("class_name"):
                        emitted_as[c["class_name"]] = f"resources/{name}-items.xml"
                continue
            if kind not in EMITTABLE:
                manual.append({
                    "target": t.get("target_name", ""), "kind": kind,
                    "sources": [c.get("class_name")
                                for c in t.get("source_classes", [])],
                    "reason": f"no emitter for `{kind}` yet — planned and not written, "
                              "deliberately: a target that is planned and then silently "
                              "absent is the loss this ledger exists to prevent",
                })
            continue

        # The implementation carries the logic; when an interface and its implementation
        # merged into one target, the interface's own methods are already part of it.
        unit = max(sources, key=lambda u: len(getattr(u, "methods", None) or []))
        write(_pkg_dir(src, package, "service", f"{t['target_name']}.java"),
              hybris_service.build_interface(unit, package, resolutions, renames))
        write(_pkg_dir(src, package, "service", "impl",
                       f"Default{t['target_name']}.java"),
              hybris_service.build_implementation(unit, package, resolutions, renames))
        services.append(unit)
        for c in t.get("source_classes", []):
            if c.get("class_name"):
                emitted_as[c["class_name"]] = (
                    f"src/{package.replace('.', '/')}/service/{t['target_name']}.java")

    # DAOs come from the data model rather than from source units: a Magento
    # ResourceModel is optional, and the tables exist either way.
    for dt in getattr(source_model.data_model, "types", None) or []:
        if getattr(dt, "deployment", "") == "eav":
            continue                      # attributes on a platform type need no DAO
        item = hybris_extension.pascal(getattr(dt, "code", ""))
        write(_pkg_dir(src, package, "daos", f"{item}Dao.java"),
              hybris_service.build_dao_interface(dt, package))
        write(_pkg_dir(src, package, "daos", "impl", f"Default{item}Dao.java"),
              hybris_service.build_dao(dt, package))

    # A job has two names in the source — the PHP class the planner routed, and the
    # crontab entry that schedules it. Emitting from the crontab alone produced
    # `AcmeLoyaltyExpirePointsJobPerformable` while the planner had named
    # `ExpirePointsJobPerformable`: two names for one thing, and the ImpEx then wired a
    # springId nothing defined.
    jobs = _jobs_by_target(source_model, targets)
    for performable, job in sorted(jobs.items()):
        write(_pkg_dir(src, package, "jobs", f"{performable}.java"),
              hybris_data.build_job_performable(job, package, class_name=performable))
        for t_row in targets or []:
            if t_row.get("target_name") != performable:
                continue
            for c in t_row.get("source_classes", []):
                if c.get("class_name"):
                    emitted_as[c["class_name"]] = (
                        f"src/{package.replace('.', '/')}/jobs/{performable}.java")

    di = (getattr(source_model, "extra", None) or {}).get("di", {})
    arguments = di.get("arguments", [])

    # Plugins and observers: invoked by the platform rather than by a caller you can see,
    # which is what makes them easy to convert wrongly. `hybris_plan` already decided
    # decorator vs interceptor from di.xml; this writes whichever it chose. [1.34]
    observers = (getattr(source_model, "extra", None) or {}).get("observers", []) or []
    event_of = {}
    for o in observers:
        inst = (o.get("instance") or "").replace("\\", ".").split(".")[-1]
        if inst:
            event_of.setdefault(inst, o.get("event", ""))

    hooks: list = []
    seen_events: set = set()
    for t_row in targets or []:
        kind = t_row.get("kind")
        if kind not in (DECORATOR, INTERCEPTOR, EVENT_LISTENER):
            continue
        sources = [units_by_name[c["class_name"]] for c in t_row.get("source_classes", [])
                   if c.get("class_name") in units_by_name]
        if not sources:
            continue
        unit = sources[0]
        target_name = t_row.get("target_name", "")
        if kind == DECORATOR:
            write(_pkg_dir(src, package, "decorators", f"{target_name}.java"),
                  hybris_hooks.build_decorator(
                      unit, package, di,
                      {hybris_service.service_name(u.name) for u in services}))
            hooks.append({"kind": kind, "name": target_name})
            emitted_as[unit.name] = (
                f"src/{package.replace('.', '/')}/decorators/{target_name}.java")
        elif kind == INTERCEPTOR:
            write(_pkg_dir(src, package, "interceptors", f"{target_name}.java"),
                  hybris_hooks.build_interceptor(unit, package, di))
            hooks.append({"kind": kind, "name": target_name,
                          "type_code": hybris_hooks._short(
                              hybris_hooks._target_type(unit, di))})
            emitted_as[unit.name] = (
                f"src/{package.replace('.', '/')}/interceptors/{target_name}.java")
        else:
            event = event_of.get(unit.name, "")
            if event and event not in seen_events:
                seen_events.add(event)
                write(_pkg_dir(src, package, "events",
                               f"{hybris_hooks.event_class_for(event)}.java"),
                      hybris_hooks.build_event(event, package))
            write(_pkg_dir(src, package, "listeners", f"{target_name}.java"),
                  hybris_hooks.build_event_listener(unit, package, event))
            hooks.append({"kind": kind, "name": target_name, "event": event})
            emitted_as[unit.name] = (
                f"src/{package.replace('.', '/')}/listeners/{target_name}.java")

    write(root / "project.properties", hybris_data.build_properties(arguments, name))
    write(resources / f"{name}-seed.impex",
          hybris_data.build_seed_impex(name, source_model.data_model.types))
    if jobs:
        write(resources / f"{name}-jobs.impex",
              hybris_data.build_cron_impex(jobs, package, name))

    # Rewritten last, because it has to name every service actually written rather than
    # every service that was planned.
    write(resources / f"{name}-spring.xml",
          _spring(services, arguments, package, name, jobs=jobs, hooks=hooks))

    from src import assurance
    from src.adapters.java_static_check import check_tree

    static = check_tree(str(root))
    # Java resolving is not the whole story. A Spring bean can name a class nobody wrote,
    # and an ImpEx can name a bean nobody defined — neither is visible to a Java parser,
    # and the second deploys cleanly and fails when the cronjob first runs.
    static["issues"] = list(static["issues"]) + cross_reference_issues(root)
    if static["issues"]:
        static["rung"] = assurance.NONE
    else:
        # Parsing and resolving is the floor, not the ceiling. A real compiler against a
        # declared stand-in for the platform catches what a parser cannot — signatures,
        # overrides, generics, and a type used without being imported, which is how this
        # rung found that every generated DAO named its model class and imported none of
        # them. Skipped silently where no compiler exists: that is a fact about the
        # machine, not about the output, and the static rung still stands. [1.37]
        from src.adapters.hybris_stubs import MODEL_SUBPACKAGE, compile_tree

        items_path = resources / f"{name}-items.xml"
        compiled = compile_tree(
            root,
            items_xml=items_path.read_text(encoding="utf-8") if items_path.exists() else "",
            model_package=f"{package}.{MODEL_SUBPACKAGE}")
        if compiled["ran"]:
            static = {**static, "rung": compiled["rung"],
                      "issues": list(compiled["issues"]),
                      "message": compiled["message"], "compiler": True}
    return {"created": sorted(set(created)), "manual": manual, "static": static,
            "emitted_as": emitted_as}


def _spring(units: list, arguments: list, package: str, extension: str,
            jobs: dict | None = None, hooks: list | None = None) -> str:
    """Bean definitions, with the migrated configuration wired onto them. [3.2, 3.5]"""
    return _spring_with_properties(
        units, hybris_data.build_bean_properties(arguments, extension), package,
        extension, jobs or {}, hooks or [])


def _spring_with_properties(units: list, props: dict, package: str, extension: str,
                            jobs: dict | None = None, hooks: list | None = None) -> str:
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<beans xmlns="http://www.springframework.org/schema/beans"',
           '       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
           '       xsi:schemaLocation="http://www.springframework.org/schema/beans',
           '       http://www.springframework.org/schema/beans/spring-beans.xsd">', ""]
    for u in units:
        iface = hybris_service.service_name(u.name)
        cls = f"Default{iface}"                 # the class
        bean = cls[:1].lower() + cls[1:]        # the bean id — conventionally lowercased
        alias = iface[:1].lower() + iface[1:]
        out += [f'    <alias name="{bean}" alias="{alias}"/>']
        values = props.get(bean, [])
        if values:
            out.append(f'    <bean id="{bean}"')
            out.append(f'          class="{package}.service.impl.{cls}">')
            for prop, key in sorted(values):
                # Migrated configuration, read from project.properties by the same name
                # it was written under. A value inlined here would drift from the file.
                out.append(f'        <property name="{prop}" value="${{{key}}}"/>')
            out.append("    </bean>")
        else:
            out += [f'    <bean id="{bean}"',
                    f'          class="{package}.service.impl.{cls}"/>']
        out.append("")
    # A JobPerformable is reached by springId from ImpEx, so it needs a bean of its own.
    # Without one the import succeeds and the cronjob cannot resolve what to run.
    for performable in sorted(jobs or {}):
        out += [f'    <bean id="{_bean_id(performable)}"',
                f'          class="{package}.jobs.{performable}"',
                '          parent="abstractJobPerformable"/>', ""]

    # Decorators, interceptors and listeners. A listener that is never declared here
    # compiles, deploys and never fires — the failure has no error to attach itself to.
    # [1.34]
    out += hybris_hooks.spring_fragments(hooks or [], package)

    out += ["</beans>", ""]
    return "\n".join(out)


def _jobs_by_target(source_model, targets: list) -> dict:
    """`{performable_class: ScheduledJob}` — the two halves of a job, joined.

    Matched on the class the crontab entry names, which is the only fact both halves
    share. A job with no planned target keeps its own derived name rather than vanishing.
    """
    planned = {}
    for t in targets or []:
        if t.get("kind") != JOB:
            continue
        for c in t.get("source_classes", []):
            planned[c.get("class_name", "")] = t.get("target_name", "")

    out = {}
    for job in getattr(source_model, "jobs", None) or []:
        cls = (job.implemented_by or "").split("::")[0].rsplit("\\", 1)[-1]
        name = planned.get(cls) or f"{hybris_extension.pascal(job.name)}JobPerformable"
        out[name] = job
    return out


def _bean_id(class_name: str) -> str:
    return class_name[:1].lower() + class_name[1:]


#: Packages the platform provides. A bean naming one of these is correctly wired, not
#: missing — see `cross_reference_issues`. [1.34]
_PLATFORM_PACKAGES = ("de.hybris.", "org.springframework.", "java.", "javax.")


def cross_reference_issues(root) -> list:
    """Spring beans and ImpEx rows that name something nothing emits. [3.10]

    The gap the Java checker structurally cannot see — it reads Java, and these are
    references *between* artifacts. It found a real one the first time this extension was
    assembled: every job's ImpEx named a springId and no bean defined it, so the cronjob
    would have deployed and failed to resolve its performable at run time. Later and
    quieter than a build failure, which is what makes it worth a rule.
    """
    import re

    root = Path(root)
    java_classes = {p.stem for p in root.rglob("*.java")}
    spring = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                       for p in root.rglob("*-spring.xml"))
    impex = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                      for p in root.rglob("*.impex"))

    bean_ids = set(re.findall(r'<bean\s+id="([^"]+)"', spring))
    bean_ids |= set(re.findall(r'alias="([^"]+)"', spring))

    issues = []
    for cls in sorted(set(re.findall(r'class="([\w.]+)"', spring))):
        # Platform classes are supplied by SAP Commerce, not by this migration, and
        # referring to one is how you wire anything at all — an InterceptorMapping is a
        # platform bean by definition. Flagging them made the rule fire on correct
        # wiring, and a critical finding that is usually wrong is a rule people learn to
        # scroll past. [1.34]
        if cls.startswith(_PLATFORM_PACKAGES):
            continue
        if cls.rsplit(".", 1)[-1] not in java_classes:
            issues.append({
                "rule": "bean_class_missing", "file": "spring.xml", "line": 0,
                "severity": "critical",
                "message": f"bean class `{cls}` is not a class this migration emitted",
                "fix": "Emit the class or remove the bean. Spring fails at context "
                       "startup, and that takes the whole extension with it."})

    for spring_id in sorted(set(re.findall(r"^;[^;\n]*;([A-Za-z]\w*)\s*$", impex, re.M))):
        if spring_id not in bean_ids:
            issues.append({
                "rule": "impex_bean_missing", "file": "impex", "line": 0,
                "severity": "critical",
                "message": f"ImpEx names springId `{spring_id}`, which no bean defines",
                "fix": "Define the bean in the extension's spring.xml. Without it the "
                       "ImpEx imports cleanly and the cronjob fails the first time it "
                       "runs, which is later and quieter than a build failure."})
    return issues
