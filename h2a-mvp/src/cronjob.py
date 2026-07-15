"""
cronjob.py — Hybris cronjob → Salesforce Scheduled Apex (Phase 2).

Hybris schedules background work with a **Job** class (extends
`AbstractJobPerformable`) wired to a cron **Trigger**. The job's *body* is
translated like any other class — a new "Job" layer maps to the Schedulable
pattern and goes through the normal LLM generation path (see ingest.py /
generate.py), so its business logic is faithfully preserved, reviewed by the
Critic, and covered by tests, exactly like a Selector or Service.

This module handles the *scheduling* side, deterministically — no LLM needed to
parse a trigger definition. Hybris triggers are commonly declared one of two
ways, both supported here:

  1. **Spring XML** — a `TriggerModel` bean with a `cronExpression` property,
     referencing a `cronJob` bean, which references the job-performable bean.
  2. **ImpEx** — an `INSERT_UPDATE Trigger;cronJob(code);cronExpression;...` block.

Hybris and Salesforce both use Quartz-based cron syntax, so translation is
mostly a *validated pass-through* rather than a rewrite — the real work is
resolving which cron expression belongs to which job class, and flagging the
handful of syntax differences that do exist.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field as dc_field
from pathlib import Path


@dataclass
class CronTrigger:
    job_class: str                  # simple Java class name of the job performable
    cron_expression: str            # as declared in the source
    source: str                     # file the trigger was found in
    active: bool = True
    resolved: bool = True           # False if the job/cronJob chain couldn't be traced
    warnings: list = dc_field(default_factory=list)


# ── Cron translation (Hybris/Quartz -> Salesforce) ────────────────────────────

def translate_cron(expr: str) -> tuple[str, list[str]]:
    """
    Validate/normalise a Quartz-style cron expression for Salesforce's
    `System.schedule`. Hybris and Salesforce both speak Quartz cron, so this is
    a pass-through plus the handful of real constraint checks Salesforce enforces.

    Returns (expression, warnings) — the expression is returned unchanged (it is
    already valid Quartz syntax); warnings flag anything that needs a human's
    attention before scheduling.
    """
    warnings: list[str] = []
    fields = expr.split()
    if len(fields) not in (6, 7):
        warnings.append(f"Expected 6 or 7 cron fields (seconds..[year]), got {len(fields)}: '{expr}'")
        return expr, warnings

    day_of_month, day_of_week = fields[3], fields[5]
    # Salesforce (like Quartz) requires exactly one of day-of-month / day-of-week
    # to be '?' — both being concrete values is invalid.
    if day_of_month not in ("?", "*") and day_of_week not in ("?", "*"):
        warnings.append("Both day-of-month and day-of-week are concrete values; "
                        "Salesforce requires one of them to be '?'.")
    return expr, warnings


# ── Spring XML trigger parsing ─────────────────────────────────────────────────

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _bean_props(bean_el) -> dict:
    """{{property name: {"value": str|None, "ref": str|None}}} for a <bean>."""
    props = {}
    for child in bean_el:
        if _local(child.tag) != "property":
            continue
        name = child.get("name")
        if not name:
            continue
        value = child.get("value")
        ref = child.get("ref")
        if value is None and ref is None:
            for grand in child:
                if _local(grand.tag) == "value" and grand.text:
                    value = grand.text.strip()
                elif _local(grand.tag) == "ref":
                    ref = grand.get("bean") or grand.text
        props[name] = {"value": value, "ref": ref}
    return props


def _simple_class_name(fq: str | None) -> str | None:
    if not fq:
        return None
    return fq.rsplit(".", 1)[-1]


def parse_spring_triggers(text: str, source: str = "") -> list[CronTrigger]:
    """Parse Spring XML for TriggerModel beans and resolve trigger -> cronJob -> job."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []

    beans = {}
    for el in root.iter():
        if _local(el.tag) != "bean":
            continue
        bean_id = el.get("id")
        if not bean_id:
            continue
        beans[bean_id] = {"class": el.get("class"), "parent": el.get("parent"),
                          "props": _bean_props(el)}

    triggers: list[CronTrigger] = []
    for bean_id, bean in beans.items():
        props = bean["props"]
        if "cronExpression" not in props:
            continue  # only beans that actually declare a schedule are triggers
        cron_expr = props["cronExpression"].get("value")
        if not cron_expr:
            continue
        active = (props.get("active", {}).get("value") or "true").lower() != "false"

        cron_job_ref = props.get("cronJob", {}).get("ref")
        job_class = None
        resolved = False
        if cron_job_ref and cron_job_ref in beans:
            job_ref = beans[cron_job_ref]["props"].get("job", {}).get("ref")
            if job_ref and job_ref in beans:
                job_class = _simple_class_name(beans[job_ref]["class"])
                resolved = job_class is not None
        # Fallback: the trigger bean references the job performable directly.
        if not resolved:
            direct_ref = props.get("job", {}).get("ref")
            if direct_ref and direct_ref in beans:
                job_class = _simple_class_name(beans[direct_ref]["class"])
                resolved = job_class is not None

        cron_expr, warns = translate_cron(cron_expr)
        triggers.append(CronTrigger(
            job_class=job_class or f"(unresolved: trigger bean '{bean_id}')",
            cron_expression=cron_expr, source=source, active=active,
            resolved=resolved, warnings=warns,
        ))
    return triggers


# ── ImpEx trigger parsing (reuses impex.py's parser) ───────────────────────────

def parse_impex_triggers(text: str, source: str = "") -> list[CronTrigger]:
    """Parse `INSERT_UPDATE Trigger;cronJob(code);cronExpression;...` rows."""
    from src.impex import parse_impex
    triggers: list[CronTrigger] = []
    for block in parse_impex(text):
        if block.type_code != "Trigger":
            continue
        for row in block.rows:
            cron_expr = row.get("cronExpression")
            job_code = row.get("cronJob") or row.get("job")
            if not cron_expr or not job_code:
                continue
            active_val = (row.get("active") or "true").lower()
            cron_expr, warns = translate_cron(cron_expr)
            triggers.append(CronTrigger(
                job_class=job_code, cron_expression=cron_expr, source=source,
                active=active_val != "false", resolved=True, warnings=warns,
            ))
    return triggers


# ── Directory driver ────────────────────────────────────────────────────────────

def find_cron_triggers(input_dir: str) -> list[CronTrigger]:
    """Scan input_dir for Spring XML trigger beans and ImpEx Trigger rows."""
    triggers: list[CronTrigger] = []
    for path in Path(input_dir).rglob("*.xml"):
        name = path.name
        if name == "items.xml" or name.endswith("-items.xml"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "<bean" in text:
            triggers += parse_spring_triggers(text, source=str(path))
    for path in Path(input_dir).rglob("*.impex"):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        triggers += parse_impex_triggers(text, source=str(path))
    return triggers


def _scheduler_name(job_class: str) -> str:
    """Mirror generate.py's Job -> '{Domain}Scheduler' target naming."""
    name = job_class
    if name.startswith("Default"):
        name = name[len("Default"):]
    if name.endswith("Job"):
        name = name[:-len("Job")]
    return f"{name}Scheduler"


def write_cron_runbook(output_dir: str, triggers: list[CronTrigger]) -> list[str]:
    """Write CRON_JOBS.md + a ready-to-run schedule.apex. Returns files written."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    resolved = [t for t in triggers if t.resolved]
    unresolved = [t for t in triggers if not t.resolved]

    lines = [
        "# Scheduled Jobs Runbook (Hybris Cronjobs → Salesforce Scheduled Apex)",
        "",
        "Hybris schedules background jobs with a cron trigger in Spring XML or ImpEx. "
        "Salesforce's `System.schedule` uses the same Quartz-based cron syntax, so "
        "translation is a **validated pass-through**, not a rewrite — the job's own "
        "logic was translated separately (see the generated `*Scheduler.cls` classes, "
        "which implement `Schedulable`).",
        "",
    ]
    if not triggers:
        lines.append("_No cron triggers were found in this source._")
        (out / "CRON_JOBS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return [str(out / "CRON_JOBS.md")]

    lines += ["## Jobs", "", "| Hybris Job | Apex Scheduler | Cron Expression | Active | Notes |",
              "|---|---|---|---|---|"]
    for t in resolved:
        notes = "; ".join(t.warnings) if t.warnings else "—"
        lines.append(f"| `{t.job_class}` | `{_scheduler_name(t.job_class)}` | "
                     f"`{t.cron_expression}` | {'yes' if t.active else 'no'} | {notes} |")
    lines.append("")

    active_resolved = [t for t in resolved if t.active]
    apex_lines = []
    if active_resolved:
        lines += ["## Schedule commands (Anonymous Apex)", "", "```apex"]
        for t in active_resolved:
            sched = _scheduler_name(t.job_class)
            stmt = f"System.schedule('{sched}', '{t.cron_expression}', new {sched}());"
            lines.append(stmt)
            apex_lines.append(stmt)
        lines += ["```", "",
                  "Run via `sf apex run --file schedule.apex --target-org <org>` "
                  "(also written alongside this runbook), or paste into "
                  "Setup → Apex → Execute Anonymous Window.", ""]

    if unresolved:
        lines += ["## Unresolved triggers (manual mapping needed)", "",
                  "These declared a cron schedule but the job class couldn't be traced "
                  "automatically — wire them up by hand:", ""]
        for t in unresolved:
            lines.append(f"- `{t.cron_expression}` in `{t.source}` — {t.job_class}")
        lines.append("")

    written = []
    md_path = out / "CRON_JOBS.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    written.append(str(md_path))

    if apex_lines:
        apex_path = out / "schedule.apex"
        apex_path.write_text("\n".join(apex_lines) + "\n", encoding="utf-8")
        written.append(str(apex_path))

    return written


def translate_cronjobs_dir(input_dir: str, output_dir: str) -> dict:
    """Find all cron triggers under input_dir, translate, and write the runbook."""
    triggers = find_cron_triggers(input_dir)
    written = write_cron_runbook(output_dir, triggers) if triggers else []
    return {
        "triggers": [{"job_class": t.job_class, "cron_expression": t.cron_expression,
                     "resolved": t.resolved, "active": t.active} for t in triggers],
        "resolved_count": sum(1 for t in triggers if t.resolved),
        "unresolved_count": sum(1 for t in triggers if not t.resolved),
        "files_written": written,
    }
