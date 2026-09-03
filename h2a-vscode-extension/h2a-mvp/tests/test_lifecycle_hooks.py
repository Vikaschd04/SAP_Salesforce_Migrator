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
from src.ingest import _LIFECYCLE_HOOKS, _parse_java_file

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
    assert all(_LIFECYCLE_HOOKS.values()), "a hook with no explanation is just a name"


def _ledger_for(hook):
    bb = Blackboard("in", "out")
    art = Artifact(target_name="OrderValidateInterceptor", layer="Utility")
    art.source_classes = [{"class_name": "OrderValidateInterceptor",
                           "layer": "Utility", "lifecycle_hook": hook,
                           "lifecycle_note": "validated every save"}]
    bb.artifacts = [art]
    bb.all_classes = art.source_classes
    return bb.completeness_ledger(), art


def test_a_hook_is_never_recorded_as_a_clean_conversion():
    """This is the regression. It used to say "converted" and mean nothing was lost."""
    rows, _ = _ledger_for("ValidateInterceptor")
    row = next(r for r in rows if r["source"] == "OrderValidateInterceptor")
    assert row["outcome"] == "flagged", "converted would be a success-shaped failure"
    assert "not enforced" in row["note"]


def test_the_note_says_what_is_missing_not_just_that_something_is():
    rows, _ = _ledger_for("ValidateInterceptor")
    note = next(r for r in rows if r["source"] == "OrderValidateInterceptor")["note"]
    assert "ValidateInterceptor" in note
    assert "trigger" in note, "name the thing that would fix it"


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
    assert "bulkified" in hits[0]["fix"], "a trigger sees 200 records, not one"
