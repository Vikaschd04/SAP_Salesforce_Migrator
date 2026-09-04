"""A real compiler, against a stand-in platform. [1.37]

The static rung parses every generated file and checks each type it names is one we
recognise. It cannot see anything a *compiler* sees, and the gap was not theoretical: every
generated DAO referenced `<Item>Model` and imported none of them, so the name resolved
against a known set and `javac` rejected eight lines the moment one was pointed at it.

What this cannot do is more important than what it can. Compiling against a declared
surface proves the output is consistent *with that surface*. Where a stub is wrong the
compiler accepts wrong code exactly as confidently, and the weak link has moved from the
parser into `hybris_stubs`. Hence `typechecked`, below `compiled`, and a claim that says
so in the sign-off.
"""

import shutil
import textwrap
from pathlib import Path

import pytest

from src import assurance
from src.adapters.hybris_stubs import (MODEL_SUBPACKAGE, compile_tree, model_names,
                                       write_stubs)

needs_javac = pytest.mark.skipif(not shutil.which("javac"),
                                 reason="no Java compiler on this machine")


def _extension(root: Path, *files: tuple) -> Path:
    for rel, body in files:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body).strip() + "\n", encoding="utf-8")
    return root


# ── which models the platform would generate ──────────────────────────────────

def test_generated_types_become_model_classes():
    xml = '<itemtype code="AcmeLoyaltyAccount" autocreate="true" generate="true">'
    assert model_names(xml) == ["AcmeLoyaltyAccountModel"]


def test_a_type_the_platform_already_ships_is_not_redeclared():
    """`generate="false"` means this is an *extension of* a platform type — the platform
    already ships its model class, and declaring our own would collide with the real one
    on a licensed build."""
    xml = '<itemtype code="Customer" autocreate="false" generate="false">'
    assert model_names(xml) == []


def test_both_kinds_in_one_file_are_told_apart():
    xml = ('<itemtype code="AcmeAccount" generate="true"><attributes/></itemtype>'
           '<itemtype code="Customer" autocreate="false" generate="false"/>')
    assert model_names(xml) == ["AcmeAccountModel"]


def test_no_items_xml_yields_no_models():
    assert model_names("") == []


# ── the stub tree ─────────────────────────────────────────────────────────────

def test_the_stub_tree_lands_in_real_package_directories(tmp_path):
    write_stubs(tmp_path, items_xml="", model_package="com.x.model")
    assert (tmp_path / "de/hybris/platform/servicelayer/search/"
                       "FlexibleSearchService.java").exists()
    assert (tmp_path / "de/hybris/platform/cronjob/enums/CronJobResult.java").exists()


def test_models_are_written_into_the_package_the_daos_import(tmp_path):
    write_stubs(tmp_path, items_xml='<itemtype code="Acme" generate="true">',
                model_package="com.migrated.model")
    assert (tmp_path / "com/migrated/model/AcmeModel.java").exists()


@needs_javac
def test_the_stub_tree_compiles_on_its_own(tmp_path):
    """If the stand-in does not compile, nothing built on it means anything."""
    src, out = tmp_path / "src", tmp_path / "out"
    out.mkdir()
    write_stubs(src, items_xml='<itemtype code="Acme" generate="true">',
                model_package="com.migrated.model")
    import subprocess
    r = subprocess.run(["javac", "-nowarn", "-proc:none", "-d", str(out),
                        *[str(p) for p in src.rglob("*.java")]],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-2000:]


# ── compiling generated code ──────────────────────────────────────────────────

@needs_javac
def test_clean_generated_code_reaches_the_typechecked_rung(tmp_path):
    ext = _extension(tmp_path, ("src/com/migrated/jobs/J.java", """
        package com.migrated.jobs;
        import de.hybris.platform.cronjob.model.CronJobModel;
        import de.hybris.platform.servicelayer.cronjob.AbstractJobPerformable;
        import de.hybris.platform.servicelayer.cronjob.PerformResult;
        public class J extends AbstractJobPerformable<CronJobModel> {
            @Override public PerformResult perform(final CronJobModel cronJob) {
                throw new UnsupportedOperationException("x");
            }
        }"""))
    got = compile_tree(ext, model_package="com.migrated.model")
    assert got["success"] and got["rung"] == assurance.TYPECHECKED
    assert got["issues"] == []


@needs_javac
def test_a_type_used_without_an_import_is_caught(tmp_path):
    """The defect that motivated the rung. The static check resolves a *name* against a
    known set, and the name was known, so eight of these shipped."""
    ext = _extension(tmp_path, ("src/com/migrated/daos/D.java", """
        package com.migrated.daos;
        public interface D {
            AcmeModel findByCode(final String code);
        }"""))
    got = compile_tree(ext, items_xml='<itemtype code="Acme" generate="true">',
                       model_package="com.migrated.model")
    assert not got["success"]
    assert got["rung"] == assurance.STATIC, "a failed compile must not claim the rung"
    assert any("cannot find symbol" in i["message"] for i in got["issues"])


@needs_javac
def test_an_import_makes_the_same_file_compile(tmp_path):
    ext = _extension(tmp_path, ("src/com/migrated/daos/D.java", """
        package com.migrated.daos;
        import com.migrated.model.AcmeModel;
        public interface D {
            AcmeModel findByCode(final String code);
        }"""))
    got = compile_tree(ext, items_xml='<itemtype code="Acme" generate="true">',
                       model_package="com.migrated.model")
    assert got["success"], got["issues"]


@needs_javac
def test_a_wrong_override_is_caught(tmp_path):
    """Signatures are the thing a parser cannot check and a compiler can."""
    ext = _extension(tmp_path, ("src/com/migrated/jobs/J.java", """
        package com.migrated.jobs;
        import de.hybris.platform.cronjob.model.CronJobModel;
        import de.hybris.platform.servicelayer.cronjob.AbstractJobPerformable;
        public class J extends AbstractJobPerformable<CronJobModel> {
            @Override public String perform(final CronJobModel cronJob) { return null; }
        }"""))
    got = compile_tree(ext, model_package="com.migrated.model")
    assert not got["success"]


@needs_javac
def test_diagnostics_carry_a_relative_path_and_a_line(tmp_path):
    """A finding naming a temp directory is not one a reviewer can act on."""
    ext = _extension(tmp_path, ("src/com/migrated/A.java", """
        package com.migrated;
        public class A { Nope field; }"""))
    got = compile_tree(ext, model_package="com.migrated.model")
    issue = got["issues"][0]
    assert issue["file"] == "src/com/migrated/A.java"
    assert issue["line"] > 0 and issue["rule"] == "compile_error"


@needs_javac
def test_the_fix_text_admits_the_stub_may_be_the_one_at_fault(tmp_path):
    """A compile error here has two possible causes and only one of them is the
    generated code. Saying so stops someone 'fixing' an emitter that was right."""
    ext = _extension(tmp_path, ("src/com/migrated/A.java", """
        package com.migrated;
        public class A { Nope field; }"""))
    got = compile_tree(ext, model_package="com.migrated.model")
    assert "the stub is wrong" in got["issues"][0]["fix"]


def test_no_compiler_is_reported_as_a_fact_about_the_machine(tmp_path, monkeypatch):
    """Not as a failure of the output: without a compiler the static rung still stands,
    and reporting `ran=False` is what stops the caller lowering it."""
    monkeypatch.setattr("src.adapters.hybris_stubs.shutil.which", lambda *a, **k: None)
    _extension(tmp_path, ("src/com/migrated/A.java", "package com.migrated;\npublic class A {}"))
    got = compile_tree(tmp_path, model_package="com.migrated.model")
    assert got["ran"] is False and got["rung"] == assurance.STATIC
    assert "No Java compiler" in got["message"]


def test_an_empty_extension_is_not_a_compile_success(tmp_path):
    got = compile_tree(tmp_path, model_package="com.migrated.model")
    assert got["ran"] is False and got["success"] is False


# ── the whole reference extension ─────────────────────────────────────────────

@needs_javac
def test_the_reference_extension_compiles_end_to_end(tmp_path):
    """The claim the rung makes about the real output, not a fixture."""
    from src.adapters.adobe_source import ADAPTER
    from src.adapters.hybris_emit import emit_extension
    from src.adapters.hybris_plan import plan_targets

    magento = str(Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-magento")
    model = ADAPTER.read(magento)
    result = emit_extension(str(tmp_path), name="acmeloyalty",
                            package="com.acme.loyalty", source_model=model,
                            targets=plan_targets(model.units, model.extra["di"]))
    assert result["static"]["rung"] == assurance.TYPECHECKED, result["static"]["issues"][:3]
    assert result["static"]["issues"] == []
    assert MODEL_SUBPACKAGE == "model"
