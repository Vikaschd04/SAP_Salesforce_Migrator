"""
hybris_data.py — configuration and seed data on the way to Hybris. [3.5]

Worth stating plainly, because it shapes the whole item: **a Magento codebase contains
almost no data.** Products, customers, orders, prices and every EAV attribute *value* live
in the database. What the code holds is configuration — and the configuration is not
incidental. `discountThreshold = 200` and `spendDiscountRate = 0.10` in `di.xml` *are* the
discount policy. Lose them and the migrated service is correct and wrong at once: the logic
survives, the numbers it applies do not.

So this emits two things and refuses to pretend about a third.

    project.properties   the tunables, in the file Hybris keeps tunables in, with the
                         source of each recorded
    Spring properties    the same values wired onto the bean, so the service behaves
                         identically without reading configuration it never read before
    seed ImpEx           a *header* naming what has to come out of the live database,
                         with no rows — because inventing rows for data we never saw
                         would be worse than an empty file with an honest explanation

The third is the point. An ImpEx file with plausible-looking sample rows is the kind of
artifact that gets loaded into an environment by someone who assumed it came from
somewhere.
"""

from __future__ import annotations

from src.adapters.hybris_extension import pascal
from src.adapters.hybris_service import service_name


def _prop_key(extension: str, on: str, name: str) -> str:
    """`acmeloyalty.pricingservice.discountthreshold` — Hybris property convention."""
    owner = on.rsplit("\\", 1)[-1] if on else ""
    return ".".join(p for p in (extension, owner.lower(), name.lower()) if p)


def build_properties(arguments: list, extension: str) -> str:
    """`project.properties` from the constructor arguments di.xml injected. [3.5]"""
    out = [f"# {extension} — configuration migrated from Adobe Commerce.",
           "#",
           "# These were constructor arguments in di.xml. They are business policy, not",
           "# plumbing: the thresholds and rates the migrated services apply. A service",
           "# whose logic survived and whose numbers did not is wrong in a way that",
           "# reviews well.",
           ""]
    if not arguments:
        out.append("# No configuration was injected through di.xml in this codebase.")
        return "\n".join(out) + "\n"

    for a in sorted(arguments, key=lambda x: (x.get("on", ""), x.get("name", ""))):
        owner = (a.get("on") or "").rsplit("\\", 1)[-1]
        out += [f"# {owner}.{a.get('name', '')} — from {a.get('file', 'di.xml')}",
                f"{_prop_key(extension, a.get('on', ''), a.get('name', ''))}"
                f"={a.get('value', '')}", ""]
    return "\n".join(out) + "\n"


def build_bean_properties(arguments: list, extension: str) -> dict:
    """`{service_bean_id: [(property, property_key)]}` for the Spring wiring. [3.5]"""
    out: dict = {}
    for a in arguments:
        owner = (a.get("on") or "").rsplit("\\", 1)[-1]
        if not owner:
            continue
        bean = f"default{service_name(owner)}"
        key = _prop_key(extension, a.get("on", ""), a.get("name", ""))
        out.setdefault(bean, []).append((a.get("name", ""), key))
    return out


#: Data that only exists in the running system. Naming it is the deliverable; the rows
#: are not ours to write.
LIVE_ONLY = (
    ("EAV attribute values", "every value of every attribute a data patch declared, plus "
     "any attribute added through the admin UI, which is in no file at all"),
    ("Catalog", "products, categories, media and their relationships"),
    ("Customers and addresses", "including the loyalty attributes this migration declares"),
    ("Orders and their history", "with the status values the source's own enums defined"),
    ("Store configuration", "core_config_data, where a store-view scoped value overrides "
     "a website one and neither is in the code"),
)


def build_seed_impex(extension: str, data_types: list) -> str:
    """The ImpEx header, and an honest statement of what is not in it. [3.5]

    No rows. Every one would be invented, and an ImpEx with plausible sample rows is the
    kind of artifact somebody loads into an environment assuming it came from somewhere.
    """
    out = [f"# {extension} — seed data", "#",
           "# This file is deliberately empty of rows.",
           "#",
           "# A Magento codebase contains almost no data: the code declares structure and",
           "# the database holds everything else. Every row below would therefore be",
           "# invented, and an ImpEx carrying plausible sample rows is the kind of file",
           "# somebody loads into an environment assuming it came from somewhere.",
           "#",
           "# What has to be exported from the live system before this migration is",
           "# complete:", "#"]
    for name, detail in LIVE_ONLY:
        out.append(f"#   {name} — {detail}")
    out += ["#",
            "# The item types below are declared and ready to receive it. Use",
            "# INSERT_UPDATE keyed on the unique column so a reload is idempotent.", "#"]

    for dt in data_types or []:
        code = getattr(dt, "code", "")
        if getattr(dt, "deployment", "") == "eav":
            continue
        item = pascal(code)
        attrs = list(getattr(dt, "attributes", None) or [])
        unique = [a["name"] for a in attrs if a.get("unique")] or \
                 [a["name"] for a in attrs[:1]]
        cols = [f"{a['name']}[unique=true]" if a["name"] in unique else a["name"]
                for a in attrs]
        out += ["", f"# INSERT_UPDATE {item};{';'.join(cols)}"]

    return "\n".join(out) + "\n"


# ── 3.6 · scheduled jobs ──────────────────────────────────────────────────────

def build_job_performable(job, package: str, class_name: str = "",
                          generated_class: str = "") -> str:
    """`AbstractJobPerformable` for one scheduled job. [3.6]

    `class_name` comes from the planner when there is one. A job has two names in the
    source — the PHP class the planner routed and the crontab entry that schedules it —
    and they must resolve to one Java class, or the ImpEx wires a springId nothing
    defines.
    """
    name = class_name or f"{pascal(job.name)}JobPerformable"

    # The model is told it is writing a job performable, and it writes `perform` — the
    # platform's name, which is also the one emitted here. [1.48]
    from src.adapters import java_bodies
    # The signature below is the *platform's*, not the source method's — so a
    # generated body written against its own parameter names lands under names it
    # never declared. Stated to the merge so a body that does not fit is refused with
    # a reason rather than written into a file that cannot compile. [4.7]
    merge = java_bodies.plan_merge(
        generated_class, {"perform": ["perform"]},
        contracts={"perform": {"params": ["cronJob"]}})
    if merge["bodies"]:
        body = "\n".join([
            f"        // Generated from {job.implemented_by}. Reviewed as generated"
            " logic, not derived — see PROVENANCE.md.",
            *java_bodies.indent(merge["bodies"]["perform"])])
    else:
        body = (f"        // TODO migrate: {job.implemented_by}\n"
                "        throw new UnsupportedOperationException(\n"
                f'                "Not migrated yet: {job.name}");')
    extra_imports = "\n".join(merge["imports"])
    if extra_imports:
        extra_imports += "\n"
    extra_members = ""
    if merge["fields"]:
        extra_members += "\n" + "\n".join(f"    {f}" for f in merge["fields"]) + "\n"
    for _hn, hs in sorted(merge["helpers"].items()):
        extra_members += "\n" + "\n".join(("    " + ln) if ln.strip() else ""
                                           for ln in hs.splitlines()) + "\n"

    return f"""package {package}.jobs;

import de.hybris.platform.cronjob.enums.CronJobResult;
import de.hybris.platform.cronjob.enums.CronJobStatus;
import de.hybris.platform.cronjob.model.CronJobModel;
import de.hybris.platform.servicelayer.cronjob.AbstractJobPerformable;
import de.hybris.platform.servicelayer.cronjob.PerformResult;
{extra_imports}
/**
 * Migrated from the Adobe Commerce cron job `{job.name}`
 * ({job.implemented_by}).
 *
 * Schedule: {job.cron}
 *
 * A Magento cron job runs ONCE across the cluster — whichever node takes the lock. A
 * Hybris cronjob has no such default: without node affinity on the trigger, every node
 * runs it, so a nightly job runs four times on a four-node cluster. The trigger emitted
 * alongside this class does not set affinity, because which node should own it is a
 * deployment decision nobody here can make.
 */
public class {name} extends AbstractJobPerformable<CronJobModel>
{{
{extra_members}
    @Override
    public PerformResult perform(final CronJobModel cronJob)
    {{
{body}
    }}

    @Override
    public boolean isAbortable()
    {{
        return true;
    }}
}}
"""


def _cron_to_quartz(cron: str) -> str:
    """Unix 5-field cron → Quartz 6-field, which is what Hybris triggers take.

    Quartz adds a leading seconds field and treats day-of-week differently: Unix Sunday is
    0, Quartz Sunday is 1. Emitting a 5-field expression into a Hybris trigger is not a
    parse error — it is a job that runs at a different time, which is worse.
    """
    parts = (cron or "").split()
    if len(parts) != 5:
        return ""
    minute, hour, dom, month, dow = parts
    if dow.isdigit():
        dow = str(int(dow) + 1)
    # Quartz rejects `*` in both day fields at once; the unused one becomes `?`.
    if dom == "*" and dow != "*":
        dom = "?"
    elif dow == "*" and dom != "*":
        dow = "?"
    elif dom == "*" and dow == "*":
        dow = "?"
    return f"0 {minute} {hour} {dom} {month} {dow}"


def build_cron_impex(jobs, package: str, extension: str) -> str:
    """The ImpEx that creates each job and its trigger. [3.6]

    Hybris cronjobs are *data*, not configuration: the job and its trigger are rows, which
    is why this is ImpEx and not XML.
    """
    out = [f"# {extension} — scheduled jobs migrated from Adobe Commerce crontab.xml",
           "#",
           "# Schedules are translated from Unix cron to Quartz, which Hybris triggers",
           "# use: Quartz adds a seconds field and numbers days of the week from 1 rather",
           "# than 0. A 5-field expression here would not fail — it would run at a",
           "# different time.",
           "#",
           "# No node affinity is set. A Magento job runs once per cluster; a Hybris job",
           "# runs on every node unless a trigger names one. Which node should own each",
           "# job is a deployment decision, so it is left visible rather than guessed.",
           ""]
    # `jobs` is {performable_class: ScheduledJob} once the planner has reconciled the two
    # names, or a plain list otherwise. Either way the springId written here has to be the
    # bean the emitter actually defines.
    pairs = (sorted(jobs.items()) if isinstance(jobs, dict)
             else [(f"{pascal(j.name)}JobPerformable", j) for j in (jobs or [])])

    for performable, j in pairs:
        code = pascal(j.name)
        quartz = _cron_to_quartz(j.cron)
        out += [f"# {j.name} — was `{j.cron}` (Unix cron)",
                "INSERT_UPDATE ServicelayerJob;code[unique=true];springId",
                f";{code}Job;{performable[:1].lower()}{performable[1:]}",
                "",
                "INSERT_UPDATE CronJob;code[unique=true];job(code);sessionLanguage(isocode)",
                f";{code}CronJob;{code}Job;en",
                ""]
        if quartz:
            out += ["INSERT_UPDATE Trigger;cronJob(code)[unique=true];cronExpression",
                    f";{code}CronJob;{quartz}", ""]
        else:
            out += [f"# TRIGGER NOT EMITTED — `{j.cron}` is not a 5-field cron expression",
                    "# and was not translated. Set the schedule by hand.", ""]
    return "\n".join(out) + "\n"
