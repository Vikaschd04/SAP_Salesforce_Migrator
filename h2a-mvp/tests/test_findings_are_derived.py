"""A finding must come from the project, not from the code that prints it. [1.65]

The first review gate told a user that no `db_schema.xml` was found, on a module whose
`etc/db_schema.xml` was sitting there being parsed correctly into eighteen columns two
stages later.

The condition read `project["db_schema_files"]` — a key **nothing ever wrote**. One
occurrence in the whole codebase, and it was the read. So `not project.get(...)` was true
for every project ever scanned, and every Magento module with code got the same warning
regardless of what it contained.

That is the failure worth guarding against, and it is not really about `db_schema`: a
message that cannot vary is not a finding, it is decoration shaped like one. Worse than
saying nothing, because a reader who acts on it wastes their time, and a reader who
notices it is wrong stops believing the ones that are right.
"""

import pathlib
import shutil

import pytest

from src.adapters.adobe_source import ADAPTER

ROOT = pathlib.Path(__file__).resolve().parents[2]
CORPORA = ("appointment-demo", "appointment-magento", "acme-commerce-magento",
           "acme-commerce-magento-full")


def _warnings(path) -> set:
    return set(ADAPTER.preflight(str(path)).get("warnings") or [])


# ── the specific defect ───────────────────────────────────────────────────────

def test_a_module_that_declares_tables_is_not_told_it_has_none():
    for corpus in CORPORA:
        got = _warnings(ROOT / "Testing" / corpus)
        assert not any("db_schema.xml` was found" in w for w in got), corpus


def test_the_warning_still_appears_when_there_really_is_no_schema(tmp_path):
    """The other half. A check that cannot fire is not a check, and removing the read of
    a phantom key would have "fixed" this by making the warning unreachable."""
    demo = tmp_path / "no-schema"
    shutil.copytree(ROOT / "Testing" / "appointment-demo", demo)
    (demo / "etc" / "db_schema.xml").unlink()

    got = _warnings(demo)
    assert any("db_schema.xml` was found" in w for w in got)


def test_the_count_it_depends_on_is_actually_written():
    """The root cause, named. The key existed only as a read."""
    project = ADAPTER.preflight(str(ROOT / "Testing" / "appointment-demo")).get("project")
    assert project.get("db_schema_files") == 1


# ── the general property ──────────────────────────────────────────────────────

def test_no_warning_fires_on_every_project():
    """A warning common to four genuinely different modules — one of eight files, one of
    twenty-three, one hand-written, one with three modules — is far more likely to be
    unconditional than to be four true findings."""
    sets = [_warnings(ROOT / "Testing" / c) for c in CORPORA]
    always = set.intersection(*sets)
    assert not always, f"fires regardless of the project: {sorted(always)}"


def test_two_different_projects_do_not_produce_the_same_preflight():
    """If the answer does not change when the question does, it was not an answer."""
    a = ADAPTER.preflight(str(ROOT / "Testing" / "appointment-demo"))
    b = ADAPTER.preflight(str(ROOT / "Testing" / "acme-commerce-magento"))
    assert a["project"] != b["project"]
    assert a["signals"] != b["signals"]
