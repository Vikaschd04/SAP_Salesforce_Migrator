"""A lifted body is emitted only when it is Java, and only under a signature it fits. [4.7]

Both halves of this come from one file in the first real Adobe→Hybris run —
`AppointmentAddressController.java`, in output that had already been demonstrated:

    public AppointmentWsDTO address(@PathVariable final String baseSiteId, ...)
    {
        \\n        return new AddressRegionController().executeInstance(country);\\n
    }

    // Generated helper, called by the logic above.
    {"code":"/** SELECTOR LAYER (fflib) ... */\\npublic with sharing class
     AddressRegionSelector { ... SOQL ... Security.stripInaccessible ... }"}

A raw JSON blob holding a complete *Salesforce Apex class*, written into a `.java` file,
next to a body referencing `country` under a signature that declares `baseSiteId, code`.
The file could not compile.

The Apex came from the pipeline id not reaching worker threads, which 4.6 fixed. These
tests cover what 4.6 did **not**: that `java_bodies` will splice whatever it finds.

  * `helpers()` matches `private void assertReadable() {` wherever those characters
    appear — including inside a JSON string holding escaped code from another platform —
    and `_balanced_body` brace-matches its way through it.
  * `plan_merge` already warned that "where the two genuinely disagree the merge must not
    happen", and nothing enforced it. An OCC signature is derived from the *route*; the
    Magento `execute()` it came from took no parameters and returned a rendered page.

Biased toward accepting, deliberately: a false rejection discards logic a model was paid
to write, while a false acceptance is caught by `hybris_stubs.compile_tree` running a real
`javac`. So the gate rejects only on unambiguous evidence, and every test below that
asserts a rejection pairs with one asserting the good case still merges.
"""

import pytest

from src.adapters import java_bodies


# ── it has to be Java ────────────────────────────────────────────────────────

#: The blob as it reached the emitted file: one line, escaped newlines, Apex inside.
JSON_BLOB_HELPER = (
    'public class AppointmentAddressController {\n'
    '    public AppointmentWsDTO address(String baseSiteId, String code) {\n'
    '        return dataMapper.map(code);\n'
    '    }\n'
    '    {"code":"/**\\n * SELECTOR LAYER (fflib) - owns ALL SOQL\\n */\\npublic with '
    'sharing class AddressRegionSelector {\\n    private void assertReadable() {\\n'
    '        throw new AddressRegionSelectorException(\'nope\');\\n    }\\n}"}\n'
    '}\n')


def test_a_helper_that_is_not_java_is_not_emitted():
    got = java_bodies.plan_merge(
        JSON_BLOB_HELPER, {"address": ["address"]},
        contracts={"address": {"params": ["baseSiteId", "code"],
                               "known": {"dataMapper"}}})
    assert got["bodies"].get("address"), "the good body should still merge"
    assert not got["helpers"], (
        "a JSON blob holding an Apex class was emitted as a Java helper: "
        + ", ".join(got["helpers"]))


def test_a_real_helper_still_comes_across():
    """The counterweight — the gate must not cost us working helpers."""
    src = ('public class X {\n'
           '    public void run(String code) { helper(code); }\n'
           '    private String helper(String c) { return c.trim(); }\n'
           '}\n')
    got = java_bodies.plan_merge(src, {"run": ["run"]},
                                 contracts={"run": {"params": ["code"]}})
    assert "helper" in got["helpers"]
    assert "return c.trim();" in got["helpers"]["helper"]


def test_a_body_that_is_not_java_is_refused_with_a_reason():
    got = java_bodies.plan_merge(
        'public class X { public void run(String code) { '
        '{"code":"public class A {"} } }',
        {"run": ["run"]}, contracts={"run": {"params": ["code"]}})
    assert not got["bodies"]
    assert "not valid Java" in got["rejected"].get("run", "")


# ── it has to fit the signature it is going under ────────────────────────────

def test_a_body_written_for_another_signature_is_refused():
    """The OCC case, reduced. `records` is the model's parameter, not the endpoint's."""
    src = ('public class X {\n'
           '    public java.util.List<Object> execute(java.util.List<Object> records) {\n'
           '        if (records == null) { return java.util.Collections.emptyList(); }\n'
           '        return records;\n'
           '    }\n}\n')
    got = java_bodies.plan_merge(
        src, {"create": ["create", "execute"]},
        contracts={"create": {"params": ["baseSiteId", "code"],
                              "known": {"dataMapper"}}})
    assert not got["bodies"], "a body reading `records` was merged into (baseSiteId, code)"
    why = got["rejected"].get("create", "")
    assert "different signature" in why and "records" in why


def test_a_body_that_fits_is_merged():
    src = ('public class X {\n'
           '    public AppointmentWsDTO create(String baseSiteId, String code) {\n'
           '        return dataMapper.map(code);\n'
           '    }\n}\n')
    got = java_bodies.plan_merge(
        src, {"create": ["create"]},
        contracts={"create": {"params": ["baseSiteId", "code"],
                              "known": {"dataMapper"}}})
    assert "return dataMapper.map(code);" in got["bodies"]["create"]
    assert not got["rejected"]


def test_a_body_may_read_the_constants_the_model_declared():
    """`fields()` lifts the model's constants, so a body using one is not "undefined"."""
    src = ('public class X {\n'
           '    private static final java.math.BigDecimal RATE = '
           'java.math.BigDecimal.ONE;\n'
           '    public java.math.BigDecimal total(java.math.BigDecimal amount) {\n'
           '        return amount.multiply(RATE);\n'
           '    }\n}\n')
    got = java_bodies.plan_merge(src, {"total": ["total"]},
                                 contracts={"total": {"params": ["amount"]}})
    assert got["bodies"].get("total"), got["rejected"]


def test_locals_and_catch_variables_are_in_scope():
    src = ('public class X {\n'
           '    public void run(String code) {\n'
           '        try { final String t = code.trim(); System.out.println(t); }\n'
           '        catch (RuntimeException ex) { System.out.println(ex); }\n'
           '    }\n}\n')
    got = java_bodies.plan_merge(src, {"run": ["run"]},
                                 contracts={"run": {"params": ["code"]}})
    assert got["bodies"].get("run"), got["rejected"]


# ── a caller that says nothing gets the parse check only ─────────────────────

def test_without_a_contract_only_the_parse_check_applies():
    """Every caller before 4.7 passed no contract, and must keep working.

    Applying the signature check with an empty parameter list would reject every body
    that reads its own parameters — which is most of them.
    """
    src = ('public class X { public void run(String code) '
           '{ System.out.println(code); } }')
    got = java_bodies.plan_merge(src, {"run": ["run"]})
    assert got["bodies"].get("run")
    assert got["rejected"] == {}


# ── the emitter says what happened ───────────────────────────────────────────

def test_the_controller_says_a_body_was_generated_and_why_it_was_not_used():
    """A refused body must not look like a body that was never written.

    There is logic to review in the run's record, and a reason it is not in the file —
    the reviewer is the person who can act on that difference.
    """
    from src.adapters import hybris_occ

    unit = type("U", (), {"name": "Create", "file": "Controller/Index/Create.php",
                          "methods": []})()
    route = {"front_name": "appointment", "path": "appointment/create",
             "action": "create"}
    out = hybris_occ.build_controller(
        unit, "com.acme.core", route,
        generated_class=('public class X {\n'
                         '    public java.util.List<Object> execute('
                         'java.util.List<Object> records) { return records; }\n}\n'))
    assert "UnsupportedOperationException" in out
    assert "A body WAS generated" in out
    assert "records" in out, "the reason names the symbol that did not exist"
    assert "return records;" not in out, "the refused body was emitted anyway"


def test_a_fitting_controller_body_is_still_merged():
    from src.adapters import hybris_occ

    unit = type("U", (), {"name": "Create", "file": "Controller/Index/Create.php",
                          "methods": []})()
    route = {"front_name": "appointment", "path": "appointment/create",
             "action": "create"}
    out = hybris_occ.build_controller(
        unit, "com.acme.core", route,
        generated_class=('public class X {\n'
                         '    public AppointmentWsDTO create(String baseSiteId, '
                         'String code) { return dataMapper.map(code); }\n}\n'))
    assert "return dataMapper.map(code);" in out
    assert "UnsupportedOperationException" not in out


# ── the whole extension compiles, which is the point ─────────────────────────

@pytest.mark.slow
def test_the_emitted_adobe_extension_typechecks():
    """End of the chain: a real `javac` over the emitted extension.

    Run against **appointment-demo**, not the golden corpus, and that is the point. The
    golden Adobe corpus (`acme-commerce-magento`) contains **zero controllers**, so the
    OCC emitter added in 1.53 has never once been exercised by the regression net — which
    is exactly how a controller that could not compile survived 1,349 tests and two golden
    baselines while being plainly visible in the demo output. A net with a hole in it is
    worth less than its pass count suggests. [4.7]
    """
    import glob
    import pathlib
    import tempfile

    from src.adapters.hybris_stubs import compile_tree
    from tests import golden

    corpus = golden.ROOT.parent / "Testing" / "appointment-demo"
    if not corpus.is_dir():
        pytest.skip(f"corpus not present: {corpus}")

    out = pathlib.Path(tempfile.mkdtemp())
    golden.run_reference(out, corpus=corpus)

    controllers = glob.glob(str(out / "**" / "controllers" / "*.java"), recursive=True)
    assert controllers, "this corpus has a controller — the OCC path did not run"

    roots = glob.glob(str(out / "hybris" / "bin" / "custom" / "*"))
    assert roots, "no extension was emitted"
    items = "\n".join(pathlib.Path(p).read_text(encoding="utf-8")
                      for p in glob.glob(roots[0] + "/resources/*-items.xml"))
    got = compile_tree(roots[0], items_xml=items, model_package="com.migrated.model")
    assert got.get("ran"), "javac did not run — is a JDK on PATH?"
    assert got.get("success"), "the emitted extension does not compile: " + "; ".join(
        f"{i.get('file')}:{i.get('line')} {i.get('message')}"
        for i in (got.get("issues") or [])[:6])
