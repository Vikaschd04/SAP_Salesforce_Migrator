"""Code the platform invoked, which the target will not. [1.21]

The engine had this wrong in the most dangerous way available to it. A Hybris
`ValidateInterceptor` in the reference corpus enforces four rules on every Order save —
code non-blank, total above zero, at least one entry, non-negative priority. It was
classified as layer "Utility", converted into a perfectly good Apex class, and recorded
in the completeness ledger as **converted**, with no caveat.

Nothing calls that class. All four rules silently stopped being enforced while the ledger
said the migration was complete. A success-shaped failure is the one outcome the ledger
exists to make impossible, which is why this is tested here rather than trusted.
"""

import textwrap

from src.agentic.blackboard import Artifact, Blackboard
from src.adapters.hybris_lifecycle import HOOKS
from src.ingest import _parse_java_file

INTERCEPTOR = textwrap.dedent("""\
    package com.acme.core.interceptor;

    import de.hybris.platform.servicelayer.interceptor.ValidateInterceptor;

    public class OrderValidateInterceptor implements ValidateInterceptor<OrderModel>
    {
        public void onValidate(final OrderModel order, final InterceptorContext ctx)
        {
            if (order.getCode() == null) { throw new InterceptorException("blank"); }
        }
    }
    """)

PLAIN = textwrap.dedent("""\
    package com.acme.core.service;

    public class OrderHelper
    {
        public void check(final Object order) { }
    }
    """)


def _parse(tmp_path, name, src):
    f = tmp_path / name
    f.write_text(src, encoding="utf-8")
    return _parse_java_file(str(f))


def test_a_lifecycle_hook_is_recognised(tmp_path):
    got = _parse(tmp_path, "OrderValidateInterceptor.java", INTERCEPTOR)
    assert got["lifecycle_hook"] == "ValidateInterceptor"
    assert got["lifecycle_note"] == "validated every save"


def test_an_ordinary_class_is_not_a_hook(tmp_path):
    assert _parse(tmp_path, "OrderHelper.java", PLAIN)["lifecycle_hook"] == ""


def test_every_known_hook_says_what_used_to_run_it():
    assert all(note for note, _ in HOOKS.values()), "a hook with no explanation is a name"


def test_load_interceptor_is_honestly_given_no_trigger():
    """Apex has no after-read hook. A trigger that could never fire is worse than a gap."""
    assert HOOKS["LoadInterceptor"][1] is None


def _ledger_for(hook, events="before insert, before update"):
    bb = Blackboard("in", "out")
    art = Artifact(target_name="OrderValidateInterceptor", layer="Utility")
    art.source_classes = [{"class_name": "OrderValidateInterceptor",
                           "layer": "Utility", "lifecycle_hook": hook,
                           "lifecycle_note": "validated every save",
                           "lifecycle_events": events if hook else "",
                           "lifecycle_type": "Order" if hook else ""}]
    bb.artifacts = [art]
    bb.all_classes = art.source_classes
    return bb.completeness_ledger(), art


def test_a_hook_is_never_recorded_as_a_clean_conversion():
    """This is the regression. It used to say "converted" and mean nothing was lost."""
    rows, _ = _ledger_for("ValidateInterceptor")
    row = next(r for r in rows if r["source"] == "OrderValidateInterceptor")
    assert row["outcome"] == "scaffolded", "converted would be a success-shaped failure"
    assert "not enforced" in row["note"]


def test_a_hook_apex_cannot_restore_is_not_called_scaffolded():
    """Nothing was scaffolded for it, so saying so would be the same lie one level down."""
    rows, _ = _ledger_for("LoadInterceptor", events="")
    row = next(r for r in rows if r["source"] == "OrderValidateInterceptor")
    assert row["outcome"] == "flagged"
    assert "no equivalent" in row["note"]


def test_the_note_says_what_is_missing_not_just_that_something_is():
    rows, _ = _ledger_for("ValidateInterceptor")
    note = next(r for r in rows if r["source"] == "OrderValidateInterceptor")["note"]
    assert "ValidateInterceptor" in note
    assert "OrderLifecycleTrigger" in note, "name the file that restores the invocation"


def test_an_ordinary_class_still_converts_cleanly():
    """The flag must be specific, or every artifact drowns in caveats."""
    rows, _ = _ledger_for("")
    assert next(r for r in rows
                if r["source"] == "OrderValidateInterceptor")["outcome"] == "converted"


def test_asking_twice_gives_the_same_answer():
    """Building a ledger is a question. It used to mutate its subject, so the note
    appeared twice in the report the second time anything asked."""
    bb = Blackboard("in", "out")
    art = Artifact(target_name="OrderValidateInterceptor", layer="Utility")
    art.source_classes = [{"class_name": "OrderValidateInterceptor", "layer": "Utility",
                           "lifecycle_hook": "ValidateInterceptor",
                           "lifecycle_note": "validated every save"}]
    bb.artifacts, bb.all_classes = [art], art.source_classes

    first = bb.completeness_ledger()
    second = bb.completeness_ledger()
    assert first == second
    assert art.review_flags == [], "the artifact must come out unchanged"
    assert second[0]["note"].count("ValidateInterceptor") == 1


def test_the_corpus_interceptor_is_flagged_end_to_end():
    from pathlib import Path

    from src.radar import scan

    corpus = Path(__file__).resolve().parents[2] / "Testing" / "acme-commerce-hybris"
    hits = [f for f in scan(str(corpus))["findings"] if f["rule"] == "LIFECYCLE_HOOK"]
    assert len(hits) == 1
    assert hits[0]["severity"] == "critical"
    assert "up to 200" in hits[0]["fix"], "a trigger sees 200 records, not one"
    assert "OrderLifecycleTrigger" in hits[0]["fix"], "point at what was emitted"


# ── the emitted invocation ────────────────────────────────────────────────────

def test_the_trigger_restores_the_invocation_with_a_guard():
    from src.adapters.apex_triggers import emit_for
    from src.adapters.hybris_lifecycle import detect

    files = emit_for("OrderValidateInterceptor.java", "OrderValidateInterceptor",
                     detect(INTERCEPTOR))
    trigger = files["triggers/OrderLifecycleTrigger.trigger"]
    handler = files["classes/OrderLifecycleHandler.cls"]

    assert "on Order__c (before insert, before update)" in trigger
    assert "running" in handler, "an Apex trigger re-enters; an interceptor chain does not"
    assert "maximum trigger depth" in handler, "say what the guard prevents"
    assert "up to 200" in handler, "the interceptor saw one record; the trigger sees many"
    assert "TODO" in handler, "the call into the converted class is not invented"
    assert "classes/OrderLifecycleHandler.cls-meta.xml" in files, \
        "an Apex class without its meta does not deploy — a scaffold that fails to " \
        "deploy fails at the one moment it is meant to help"


def test_no_trigger_is_emitted_where_apex_has_no_hook():
    from src.adapters.apex_triggers import emit_for
    from src.adapters.hybris_lifecycle import detect

    assert emit_for("X", "X", detect("class X implements LoadInterceptor<CartModel> {}")) == {}
