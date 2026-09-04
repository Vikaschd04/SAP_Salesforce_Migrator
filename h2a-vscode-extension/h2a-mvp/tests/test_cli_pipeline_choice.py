"""Choosing a migration on the command line. [4.5]

The default is detection, and that is the right default: there is one valid answer for
almost every codebase, and asking an operator to pick a source/target pair would mostly
offer invalid combinations. The flag exists for when detection has no single answer.

An explicit choice is honoured even when detection disagrees — the operator may know
something the detector does not — but the mismatch is said out loud, because the likeliest
cause of the two disagreeing is a wrong flag.
"""

from pathlib import Path

import pytest

from src.main import _resolve_pipeline

TESTING = Path(__file__).resolve().parents[2] / "Testing"
HYBRIS = str(TESTING / "acme-commerce-hybris")
MAGENTO = str(TESTING / "acme-commerce-magento")


def test_detection_chooses_when_nothing_is_asked_for(capsys):
    p = _resolve_pipeline(HYBRIS, None)
    assert p.id == "hybris->salesforce"
    assert "Detected hybris" in capsys.readouterr().out


def test_an_explicit_choice_is_honoured():
    assert _resolve_pipeline(HYBRIS, "hybris->salesforce").id == "hybris->salesforce"


def test_a_mismatch_is_said_out_loud_but_obeyed(capsys):
    """The operator may know something the detector does not. They may also have typed
    the wrong flag, and only one of those is silent."""
    p = _resolve_pipeline(MAGENTO, "hybris->salesforce")
    assert p.id == "hybris->salesforce"
    out = capsys.readouterr().out
    assert "expects a hybris source" in out and "adobe-commerce" in out


def test_an_unrecognised_source_refuses_with_the_specific_reason(tmp_path):
    (tmp_path / "photo.txt").write_text("not code", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        _resolve_pipeline(str(tmp_path), None)
    assert "nothing to migrate" in str(e.value)


def test_a_recognised_but_unrunnable_source_says_which_it_is(monkeypatch, capsys):
    """"Recognised and not yet supported" is a roadmap fact. Reporting it as a detection
    failure would send someone looking for a problem with their codebase.

    Magento is runnable since 1.34, so the flag is flipped back for this test: the
    message is for whichever platform is registered-but-unbuilt next, and it has to keep
    working until then."""
    from src import pipeline

    pipeline.ensure_registered()
    monkeypatch.setattr(pipeline.get("adobe->hybris").target, "implemented", False)
    with pytest.raises(SystemExit) as e:
        _resolve_pipeline(MAGENTO, None)
    msg = str(e.value)
    assert "Adobe Commerce" in msg
    assert "no migration from it can run yet" in msg
    assert "not a detection failure" in msg


def test_a_runnable_source_resolves_instead_of_exiting():
    """The other half of the same behaviour, and the one that is live now."""
    assert _resolve_pipeline(MAGENTO, None).id == "adobe->hybris"


def test_an_unknown_pipeline_id_is_rejected():
    with pytest.raises(KeyError):
        _resolve_pipeline(HYBRIS, "no-such->pipeline")


# ── the identify command ──────────────────────────────────────────────────────

class _Args:
    def __init__(self, input):
        self.input = input


def test_identify_reports_a_runnable_source(capsys):
    from src.main import cmd_identify

    with pytest.raises(SystemExit) as e:
        cmd_identify(_Args(HYBRIS))
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "hybris->salesforce" in out and "ready" in out
    assert "compile-verified" in out


def test_identify_reports_what_a_run_could_claim(capsys):
    """The oracle difference belongs beside the choice, not in the sign-off afterwards.

    It matters more now that the pipeline runs: before 1.34 "not implemented yet" was the
    headline, and the compiler caveat was a detail under it. Now the run is available and
    the only thing separating it from the Salesforce path is what it can *claim*."""
    from src.main import cmd_identify

    with pytest.raises(SystemExit) as e:
        cmd_identify(_Args(MAGENTO))
    assert e.value.code == 0, "a runnable source is not an error"
    out = capsys.readouterr().out
    assert "no compiler for this target" in out
    assert "statically checked" in out


def test_the_three_answers_get_three_exit_codes(tmp_path, capsys):
    """So a script can act on the difference rather than parsing the prose."""
    from src.main import cmd_identify

    codes = {}
    # Both real sources are runnable since 1.34, so `2` — recognised but not runnable —
    # has no live example. The code stays, and stays tested: it is what a scaffolded
    # pipeline will report the next time one is registered, and an exit code nothing
    # exercises is one that has quietly stopped working by the time it is needed.
    for label, root in (("runnable", HYBRIS), ("also runnable", MAGENTO),
                        ("unrecognised", str(tmp_path))):
        with pytest.raises(SystemExit) as e:
            cmd_identify(_Args(root))
        codes[label] = e.value.code
    assert codes == {"runnable": 0, "also runnable": 0, "unrecognised": 1}


def test_the_recognised_but_unrunnable_exit_code_is_still_reachable(monkeypatch, capsys):
    """`2` distinguishes "we know what this is and cannot migrate it" from "we have no
    idea what this is", which is the difference a script most needs to act on."""
    import pytest as _pytest
    from src import pipeline
    from src.main import cmd_identify

    pipeline.ensure_registered()
    # `Pipeline` is frozen, so the flag is flipped on the target object itself.
    monkeypatch.setattr(pipeline.get("adobe->hybris").target, "implemented", False)
    with _pytest.raises(SystemExit) as e:
        cmd_identify(_Args(MAGENTO))
    assert e.value.code == 2


def test_identify_exits_nonzero_on_an_unrecognised_upload(tmp_path, capsys):
    from src.main import cmd_identify

    with pytest.raises(SystemExit) as e:
        cmd_identify(_Args(str(tmp_path)))
    assert e.value.code == 1


def test_the_cli_exposes_both_the_flag_and_the_command():
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    out = subprocess.run([sys.executable, "-m", "src.main", "agent-migrate", "--help"],
                         cwd=root, capture_output=True, text=True,
                         env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(root)}).stdout
    assert "--pipeline" in out
