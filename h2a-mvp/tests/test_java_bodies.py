"""The generated logic reaches the file on disk. [1.48]

Phase 0 — the first migration run against a real model — produced ten methods that all
threw `UnsupportedOperationException`, while the Builder's actual Java sat in run state
and was never written. `emit_extension` did not take a parameter for it. Nine months of
mock runs could not have found this: a mock and a real model produced identical bytes,
because *neither* was used.

These tests fix both halves — that bodies are lifted correctly, and that they arrive.
"""

import textwrap

from src.adapters import java_bodies


def _java(s: str) -> str:
    return textwrap.dedent(s).strip() + "\n"


# ── lifting bodies out of generated Java ──────────────────────────────────────

def test_a_method_body_is_lifted_whole():
    got = java_bodies.bodies(_java("""
        public class A {
            public Double total(Double x) {
                Double r = x * 2;
                return r;
            }
        }"""))
    assert "return r;" in got["total"] and "Double r = x * 2;" in got["total"]


def test_a_brace_inside_a_string_does_not_end_the_method():
    """The reason this matches braces instead of pattern-matching them. A `}` in a
    message would truncate the body and write a fragment that does not compile."""
    got = java_bodies.bodies(_java("""
        public class A {
            public String f() {
                String s = "}";
                return s;
            }
        }"""))
    assert "return s;" in got["f"]


def test_a_brace_inside_a_comment_does_not_end_the_method():
    got = java_bodies.bodies(_java("""
        public class A {
            public void f() {
                // closes like this: }
                doWork();
            }
        }"""))
    assert "doWork();" in got["f"]


def test_nested_blocks_are_kept():
    got = java_bodies.bodies(_java("""
        public class A {
            public int f(int n) {
                if (n > 0) { return 1; }
                for (int i = 0; i < n; i++) { n--; }
                return 0;
            }
        }"""))
    assert "for (int i = 0; i < n; i++)" in got["f"] and "return 0;" in got["f"]


def test_a_method_that_throws_is_still_matched():
    got = java_bodies.bodies(_java("""
        public class A {
            public void f() throws IllegalStateException {
                step();
            }
        }"""))
    assert "step();" in got["f"]


def test_generic_and_qualified_return_types_are_matched():
    got = java_bodies.bodies(_java("""
        public class A {
            public java.util.List<String> names() { return java.util.List.of("a"); }
        }"""))
    assert "names" in got


def test_an_abstract_method_has_no_body_to_lift():
    assert java_bodies.bodies("public interface I { String f(String a); }") == {}


def test_nothing_is_lifted_from_empty_input():
    assert java_bodies.bodies("") == {} and java_bodies.bodies(None) == {}


# ── which bodies are worth merging ────────────────────────────────────────────

def test_a_refusal_is_not_a_body():
    """Merging one over the derived stub loses the TODO marker and gains no logic — the
    method is unfinished either way, and only one version says so."""
    assert java_bodies.is_stub('throw new UnsupportedOperationException("x");')
    assert java_bodies.is_stub("return null;")
    assert java_bodies.is_stub("   ")
    assert java_bodies.is_stub("// nothing here")


def test_real_logic_is_not_a_stub():
    assert not java_bodies.is_stub("return a + b;\nlog(a);")
    assert not java_bodies.is_stub("return getBaseAmount().multiply(RATE);")


def test_indenting_normalises_to_the_emitted_class():
    got = java_bodies.indent("        int a = 1;\n            int b = 2;\n")
    assert got == ["        int a = 1;", "            int b = 2;"]


# ── the merge, in the emitter ─────────────────────────────────────────────────

class _M:
    def __init__(self, name, params=({"name": "subtotal"},), ret="Double"):
        self.name, self.params, self.return_type = name, list(params), ret
        self.parameters = list(params)      # what `_signature` actually reads
        self.docstring = ""
        self.body = ""


class _U:
    def __init__(self, methods):
        self.name = "PricingService"
        self.file = "Pricing.php"
        self.methods = methods
        self.extra = {}
        self.docstring = ""


def _impl(bodies=None):
    from src.adapters import hybris_service
    return hybris_service.build_implementation(
        _U([_M("applySpendDiscount"), _M("baseRate")]), "com.acme",
        {}, {}, name="PricingService", source_names=set(), models=set(),
        bodies=bodies)


def test_without_a_generated_body_the_method_still_refuses():
    """The honest default. A method nobody wrote must not look finished."""
    out = _impl()
    assert "UnsupportedOperationException" in out
    assert "TODO migrate: PricingService::applySpendDiscount" in out


def test_a_generated_body_replaces_the_stub():
    out = _impl({"applySpendDiscount": "    return subtotal * 0.9;"})
    assert "return subtotal * 0.9;" in out
    assert "Not migrated yet: applySpendDiscount" not in out


def test_the_untouched_method_keeps_its_stub():
    """Partial generation is the normal case, and a file where the merged and unmerged
    methods are indistinguishable would be the same failure in a new shape."""
    out = _impl({"applySpendDiscount": "    return subtotal * 0.9;"})
    assert "Not migrated yet: baseRate" in out


def test_a_merged_body_is_marked_as_generated():
    """Provenance is the point. A reader must be able to tell what the migration *knew*
    from what a model *decided*, and the sign-off rests on that line existing."""
    out = _impl({"applySpendDiscount": "    return subtotal * 0.9;"})
    line = next(l for l in out.splitlines() if "Generated from" in l)
    assert "PricingService::applySpendDiscount" in line
    assert "PROVENANCE.md" in line


def test_a_generated_refusal_does_not_overwrite_the_derived_one():
    out = _impl({"applySpendDiscount":
                 '    throw new UnsupportedOperationException("later");'})
    assert "Not migrated yet: applySpendDiscount" in out, (
        "the derived stub names the source method; the model's does not")


def test_the_derived_signature_survives_the_merge():
    """The emitter is right about structure and the model is right about logic. On the
    run that found this, the model named the class `AcmePricingService` and omitted the
    package line — taking its class wholesale would have regressed both."""
    out = _impl({"applySpendDiscount": "    return subtotal * 0.9;"})
    assert out.startswith("package com.acme.service.impl;")
    assert "public class DefaultPricingService" in out
    assert "AcmePricingService" not in out


def test_the_blank_line_before_the_closing_brace_is_dropped():
    """A lifted body ends with the whitespace that preceded its own `}`, which lands as a
    blank line inside the emitted method."""
    got = java_bodies.indent("\n        return 1;\n    ")
    assert got == ["        return 1;"]


# ── the seam that actually broke ──────────────────────────────────────────────
#
# Every test above passes against a `build_implementation` nobody calls with bodies. The
# defect was one layer up: `hybris_target.emit()` received the artifacts and did not pass
# them on, and `emit_extension` had no parameter to receive them. So these go through the
# adapter, which is the only place that failure was visible.
#
# The golden baselines cannot cover this. They run `H2A_PROVIDER=mock`, and a mock that
# invents no business logic produces no method names matching the source — correctly, but
# it means nothing merges on a golden run. That is the same blind spot in a new shape, so
# it is named here rather than left to be rediscovered.

import pathlib
import tempfile

import pytest

from src.adapters.adobe_source import ADAPTER as SOURCE
from src.adapters.hybris_plan import plan_targets
from src.adapters.hybris_target import ADAPTER as TARGET

CORPUS = str(pathlib.Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-magento")


@pytest.fixture(scope="module")
def emitted():
    model = SOURCE.read(CORPUS)
    plan = plan_targets(model.units, model.extra["di"])
    target = next(t["target_name"] for t in plan if t.get("kind") == "service")
    written = """package whatever;
public class Acme%s {
    public Double applySpendDiscount(Double subtotal) {
        if (subtotal == null) { return 0.0; }
        return subtotal * 0.9;
    }
}
""" % target
    out = tempfile.mkdtemp()
    TARGET.emit(out, [{"target_name": target, "main_class": written}], model.data_model,
                {"source_model": model, "plan": plan, "extension_name": "acmeloyalty",
                 "package": "com.acme.loyalty"})
    impl = next(pathlib.Path(out).rglob(f"Default{target}.java")).read_text()
    return {"target": target, "impl": impl, "emit": TARGET.last_emit or {}}


def test_generated_logic_reaches_the_file_on_disk(emitted):
    """The Phase 0 defect, stated as a test. Before 1.48 this file held ten methods that
    all threw, and the Java the Builder wrote was never passed to the emitter at all."""
    assert "return subtotal * 0.9;" in emitted["impl"]


def test_the_emitters_own_structure_wins(emitted):
    """The model called its class `AcmePricingService` and wrote no package line. Taking
    its class wholesale would have regressed both; the merge keeps neither."""
    assert emitted["impl"].startswith("package com.acme.loyalty.service.impl;")
    assert f"public class Default{emitted['target']}" in emitted["impl"]
    assert "AcmePricingService" not in emitted["impl"]


def test_methods_nobody_generated_still_refuse(emitted):
    """Partial generation is the normal case. A file where merged and unmerged methods
    read alike would be the same success-shaped failure wearing a different hat."""
    assert "UnsupportedOperationException" in emitted["impl"]


def test_the_ledger_names_which_bodies_came_from_a_model(emitted):
    """A reviewer must not have to diff against a skeleton to find out."""
    assert emitted["emit"]["generated_bodies"] == [f"{emitted['target']}.applySpendDiscount"]


def test_a_merged_body_is_held_to_the_same_assurance_rung(emitted):
    """Generated code now passes through the stub compiler like everything else, so a
    body referencing something that does not exist lowers the rung instead of shipping.
    Before the merge there was nothing to check: a `throw` always compiles."""
    static = emitted["emit"].get("static") or {}
    assert static.get("issues") == [], static.get("issues")


# ── decorators merge; the two collapsing kinds deliberately do not ────────────

def _unit(*names):
    return _U([_M(n) for n in names])


def _decorator(bodies=None):
    from src.adapters.hybris_hooks import build_decorator
    u = _unit("getTotal")
    u.name = "OrderTotalPlugin"
    u.extra = {"fqn": "A\\B\\OrderTotalPlugin"}
    wiring = {"plugins": [{"type": "A\\B\\OrderTotalPlugin", "on": "Sales\\Order"}]}
    return build_decorator(u, "com.x", wiring, {"OrderService"}, bodies=bodies)


def test_a_decorator_takes_the_generated_body():
    """One emitted method per source method, so the names line up exactly as they do for
    a service."""
    out = _decorator({"getTotal": "    return args[0];"})
    assert "return args[0];" in out
    assert "Generated from OrderTotalPlugin::getTotal" in out


def test_the_body_lands_inside_the_method_derived_from_that_source_name():
    """The merge keys on the *source* method name, and the emitted method is whatever
    `wrapped_method` derives from it — the same name here, `beforeX` where the source
    already carried a hook prefix. Keying on the source name is what makes them meet
    under either spelling."""
    from src.adapters.hybris_hooks import wrapped_method

    out = _decorator({"getTotal": "    return args[0];"})
    emitted = wrapped_method("getTotal")
    lines = out.splitlines()
    at = next(i for i, l in enumerate(lines) if f"public Object {emitted}(" in l)
    assert "return args[0];" in "\n".join(lines[at:at + 6])


def test_a_decorator_without_a_body_still_refuses():
    assert "UnsupportedOperationException" in _decorator()


def test_delegation_stays_an_open_decision_even_when_merged():
    """The generated body is the plugin's logic. Whether it also calls through to the
    wrapped service is a separate question the model was never asked."""
    out = _decorator({"getTotal": "    return args[0];"})
    assert "Delegation is still yours to decide" in out


def test_an_interceptor_never_takes_a_generated_body():
    """It collapses every source method into one `onValidate`. There is no method for a
    body to belong to, and concatenating separately-written ones would rarely compile
    while always looking migrated."""
    from src.adapters.hybris_hooks import build_interceptor
    import inspect

    assert "bodies" not in inspect.signature(build_interceptor).parameters


def test_an_event_listener_never_takes_a_generated_body():
    from src.adapters.hybris_hooks import build_event_listener
    import inspect

    assert "bodies" not in inspect.signature(build_event_listener).parameters


# ── a body is only as portable as what it names ───────────────────────────────
#
# The first realistic output merged here called `base.multiply(RATE)` — `RATE` a constant
# on the model's own class, `BigDecimal` an import on it, `norm()` a private helper it
# wrote. Taking the body alone produced a file that would not compile. The stub compiler
# catches that, but causing it and catching it is worse than not causing it.

REALISTIC = """```java
package com.acme.loyalty.service.impl;

import java.math.BigDecimal;
import static java.util.Objects.requireNonNull;

public class AcmePricingService implements PricingService
{
    private static final BigDecimal RATE = new BigDecimal("0.90");
    public String publicSurface = "not yours to copy";

    @Override
    public Double applySpendDiscount(final Double subtotal)
    {
        // a brace in a comment: }
        return norm(subtotal).multiply(RATE).doubleValue();
    }

    private BigDecimal norm(final Double v) {
        return v == null ? BigDecimal.ZERO : BigDecimal.valueOf(v);
    }
}
```"""


def test_imports_come_across():
    assert "import java.math.BigDecimal;" in java_bodies.imports(REALISTIC)


def test_a_static_import_keeps_its_static():
    assert "import static java.util.Objects.requireNonNull;" in java_bodies.imports(REALISTIC)


def test_constants_the_body_relies_on_come_across():
    got = java_bodies.fields(REALISTIC)
    assert any("RATE" in f for f in got)


def test_a_public_field_does_not():
    """The emitter owns the public surface. Copying a public field across would let
    generated code widen a contract the plan settled."""
    assert not any("publicSurface" in f for f in java_bodies.fields(REALISTIC))


def test_private_helpers_come_across():
    got = java_bodies.helpers(REALISTIC, skip={"applySpendDiscount"})
    assert "norm" in got and "BigDecimal.valueOf(v)" in got["norm"]


def test_a_public_method_is_not_smuggled_in_as_a_helper():
    """Its signature is derived from the source; the model's version of it is not."""
    assert "applySpendDiscount" not in java_bodies.helpers(
        REALISTIC, skip={"applySpendDiscount"})


def test_a_helper_keeps_its_own_indentation():
    """Dedenting the signature line and not the body puts the helper's braces two levels
    off, which is invalid where the emitted class expects a block."""
    got = java_bodies.helpers(REALISTIC, skip={"applySpendDiscount"})["norm"]
    lines = got.splitlines()
    assert lines[0].startswith("private BigDecimal norm")
    assert lines[-1].strip() == "}"
    assert len(lines[-1]) - len(lines[-1].lstrip()) == 0, "closing brace must be flush"


#: What 2.12 resolves for this unit — without it every signature derives as `Object`,
#: which is a property of the fixture rather than of the emitter.
RESOLVED = [
    {"where": "PricingService::applySpendDiscount()", "type": "float"},
    {"where": "PricingService::applySpendDiscount($subtotal)", "type": "float"},
    {"where": "PricingService::pointsFor()", "type": "float"},
    {"where": "PricingService::pointsFor($subtotal)", "type": "float"},
]


def _merged():
    from src.adapters import hybris_service
    unit = _U([_M("applySpendDiscount"), _M("pointsFor")])
    return hybris_service.build_implementation(
        unit, "com.acme", RESOLVED, {}, name="PricingService", source_names=set(),
        models=set(), bodies=java_bodies.bodies(REALISTIC),
        generated_class=REALISTIC)


def test_the_merged_class_carries_everything_its_body_names():
    out = _merged()
    assert "import java.math.BigDecimal;" in out
    assert "private static final BigDecimal RATE" in out
    assert "private BigDecimal norm(" in out


def test_the_derived_import_is_not_duplicated():
    out = _merged()
    assert out.count("import com.acme.service.PricingService;") == 1


def test_the_header_says_how_much_of_the_file_a_model_wrote():
    """A reviewer's first question. Answering it in the file beats making them diff
    against a skeleton to find out."""
    out = _merged()
    assert "1 of 2" in out


def test_the_header_does_not_claim_bodies_are_underived_when_none_were_merged():
    from src.adapters import hybris_service
    out = hybris_service.build_implementation(
        _U([_M("a")]), "com.acme", [], {}, name="S", source_names=set(), models=set())
    assert "Method bodies are not translated here" in out


def test_nothing_is_carried_when_nothing_was_merged():
    """Imports and constants belonging to logic that was rejected have no business in a
    file of honest stubs."""
    from src.adapters import hybris_service
    out = hybris_service.build_implementation(
        _U([_M("other")]), "com.acme", [], {}, name="S", source_names=set(),
        models=set(), bodies=java_bodies.bodies(REALISTIC), generated_class=REALISTIC)
    assert "BigDecimal" not in out


# ── the compiler, on merged output ────────────────────────────────────────────
#
# Every assertion above checks text. This one checks the thing that matters: that a class
# built half from derivation and half from a model is valid Java. It is also the reason
# carrying imports, fields and helpers was not optional — without them this fails.

import shutil
import subprocess

needs_javac = pytest.mark.skipif(not shutil.which("javac"),
                                 reason="no Java compiler on this machine")


#: The same output, with the helper typed as the derivation types the method. A model
#: that is given the signature — which the Builder is — produces this; `REALISTIC` above
#: keeps the boxed `Double` a model reaches for when it is not, and the test below shows
#: what happens then.
AGREEING = REALISTIC.replace("private BigDecimal norm(final Double v) {",
                             "private BigDecimal norm(final float v) {") \
                    .replace("return v == null ? BigDecimal.ZERO : BigDecimal.valueOf(v);",
                             "return BigDecimal.valueOf(v);") \
                    .replace("return norm(subtotal).multiply(RATE).doubleValue();",
                             "return norm(subtotal).multiply(RATE).floatValue();")


def _compile(tmp_path, impl, iface):
    for rel, body in (("com/acme/service/PricingService.java", iface),
                      ("com/acme/service/impl/DefaultPricingService.java", impl)):
        p = tmp_path / "src" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    return subprocess.run(["javac", "-nowarn", "-proc:none", "-d", str(out),
                           *[str(p) for p in (tmp_path / "src").rglob("*.java")]],
                          capture_output=True, text=True, timeout=180)


@needs_javac
def test_a_type_the_model_assumed_and_the_source_did_not_is_caught(tmp_path):
    """`REALISTIC` writes `norm(Double)`; the source resolves the method to `float`, and
    Java does not widen a primitive to a boxed type. This is the merge's real residual
    risk, and it is the compiler's to catch rather than something to paper over — which
    is why generated bodies go through the stub compiler at all."""
    from src.adapters import hybris_service

    unit = _U([_M("applySpendDiscount")])
    r = _compile(
        tmp_path,
        hybris_service.build_implementation(
            unit, "com.acme", RESOLVED, {}, name="PricingService", source_names=set(),
            models=set(), bodies=java_bodies.bodies(REALISTIC),
            generated_class=REALISTIC),
        hybris_service.build_interface(
            unit, "com.acme", RESOLVED, {}, name="PricingService", source_names=set(),
            models=set()))
    assert r.returncode != 0
    assert "incompatible types" in r.stderr


@needs_javac
def test_a_merged_class_compiles(tmp_path):
    from src.adapters import hybris_service

    unit = _U([_M("applySpendDiscount")])
    r = _compile(
        tmp_path,
        hybris_service.build_implementation(
            unit, "com.acme", RESOLVED, {}, name="PricingService", source_names=set(),
            models=set(), bodies=java_bodies.bodies(AGREEING),
            generated_class=AGREEING),
        hybris_service.build_interface(
            unit, "com.acme", RESOLVED, {}, name="PricingService", source_names=set(),
            models=set()))
    assert r.returncode == 0, r.stderr[-3000:]


@needs_javac
def test_dropping_the_support_breaks_that_same_class(tmp_path):
    """The counter-test, so the one above is not passing for an unrelated reason. This is
    what the merge produced before 1.48 carried imports, fields and helpers across."""
    from src.adapters import hybris_service

    unit = _U([_M("applySpendDiscount")])
    r = _compile(
        tmp_path,
        hybris_service.build_implementation(
            unit, "com.acme", RESOLVED, {}, name="PricingService", source_names=set(),
            models=set(), bodies=java_bodies.bodies(AGREEING)),   # no generated_class
        hybris_service.build_interface(
            unit, "com.acme", RESOLVED, {}, name="PricingService", source_names=set(),
            models=set()))
    assert r.returncode != 0, "the body names RATE, BigDecimal and norm — none declared"
    assert "cannot find symbol" in r.stderr
