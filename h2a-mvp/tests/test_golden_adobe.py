"""The product-level regression net for the *second* pipeline. [1.35]

The Hybris→Salesforce path has had one since v2 and it has earned its place — it caught
the non-deterministic recipe hash, and it is what let 1.33 and 1.34 refactor the
orchestrator's spine with the shipped output provably byte-identical at every step.

Adobe→Hybris had nothing. Every defect found in it during those two items was found by
running it by hand and reading the output: the ledger claiming eight conversions over an
extension holding three, the planner discarding the target's own decision, the two
sources disagreeing about `DataModel.types`, a Spring bean naming a platform class
reported as missing. All real, all invisible to 1073 unit tests, none of which would be
caught a second time.

A net per pipeline rather than one shared net: they read different corpora and write
different platforms, so a single manifest could only ever cover one of them.

    pytest tests/test_golden_adobe.py
    H2A_GOLDEN_UPDATE=1 pytest tests/test_golden_adobe.py   # re-baseline deliberately
"""

import os

import pytest

from tests import golden


def _run(path):
    return golden.run_reference(path, corpus=golden.ADOBE_CORPUS)


@pytest.mark.slow
def test_the_adobe_migration_is_unchanged(tmp_path):
    actual = _run(tmp_path / "out")

    if os.environ.get("H2A_GOLDEN_UPDATE"):
        golden.save(actual, path=golden.ADOBE_MANIFEST, corpus=golden.ADOBE_CORPUS,
                    note="Baseline of the Adobe Commerce → SAP Hybris reference "
                         "migration. Regenerate deliberately: H2A_GOLDEN_UPDATE=1 "
                         "pytest tests/test_golden_adobe.py")
        pytest.skip(f"baseline rewritten — {len(actual)} files. Review the diff in git.")

    expected = golden.load(golden.ADOBE_MANIFEST)
    assert expected, ("no baseline recorded. Create one deliberately with "
                      "H2A_GOLDEN_UPDATE=1 pytest tests/test_golden_adobe.py")

    diffs = golden.compare(expected, actual)
    assert not diffs, (
        f"{len(diffs)} unintended change(s) to what the Adobe migration produces:\n  "
        + "\n  ".join(diffs[:40])
        + "\n\nIf the change was intended, re-baseline with H2A_GOLDEN_UPDATE=1 and "
          "review the manifest diff in the commit.")


@pytest.mark.slow
def test_two_identical_adobe_runs_agree(tmp_path):
    """Determinism, checked rather than assumed.

    On the Salesforce path this caught a recipe hash that varied per process, silently
    disabling incremental reuse. The Adobe path has its own opportunities for the same
    bug — the schema it hashes is built by a different adapter — and no reason to assume
    it does not have one.
    """
    a = _run(tmp_path / "a")
    b = _run(tmp_path / "b")
    diffs = golden.compare(a, b)
    assert not diffs, ("two identical runs disagreed — the Adobe pipeline is not "
                       "deterministic:\n  " + "\n  ".join(diffs[:20]))


@pytest.mark.slow
def test_the_two_pipelines_do_not_write_into_each_other(tmp_path):
    """Each writes its own platform's layout, and nothing of the other's.

    Both pipelines share every stage between the adapters, so a target-shaped assumption
    left in the middle shows up as one platform's artifacts appearing in the other's
    output. That is exactly what 1.33 found — `force-app/objects/` written during an
    Adobe→Hybris run — and the kind of thing that returns quietly.
    """
    adobe = _run(tmp_path / "adobe")
    assert any(p.startswith("hybris/bin/custom/") for p in adobe), \
        "the Hybris extension layout is missing"
    assert not [p for p in adobe if p.startswith("force-app/")], \
        "an Adobe→Hybris run wrote Salesforce metadata"

    salesforce = golden.run_reference(tmp_path / "sf")
    assert any(p.startswith("force-app/") for p in salesforce)
    assert not [p for p in salesforce if p.startswith("hybris/bin/")], \
        "a Hybris→Salesforce run wrote a Hybris extension"


@pytest.mark.slow
def test_the_adobe_output_is_java_not_apex(tmp_path):
    """A cheap check on the seam. `.cls` files in this output would mean a Salesforce
    assumption survived somewhere between the two adapters."""
    files = _run(tmp_path / "out")
    assert not [p for p in files if p.endswith(".cls")]
    assert [p for p in files if p.endswith(".java")]
    assert any(p.endswith("-items.xml") for p in files)


@pytest.mark.slow
def test_the_extension_still_reaches_the_static_rung(tmp_path):
    """Every generated file parses and every type it names resolves.

    The strongest check available without a licensed platform, and the one thing that
    stops "it emitted 14 files" from being the whole claim. It is asserted here rather
    than only inside the emitter so that a change anywhere in the pipeline — not just in
    the emitter — has to keep it true.
    """
    from src.adapters.java_static_check import check_tree

    out = tmp_path / "out"
    _run(out)
    got = check_tree(str(out / "hybris" / "bin" / "custom" / "migrated"))
    assert got["files"] > 0, "nothing was emitted to check"
    assert got["issues"] == [], f"static issues: {got['issues'][:3]}"
    assert got["rung"] == "static"


@pytest.mark.slow
def test_nothing_is_reported_as_converted_that_was_not_written(tmp_path):
    """The claim the completeness ledger exists to make, checked against the disk.

    This is the defect 1.33 found: the ledger walked the Builder's artifacts and reported
    eight conversions over an extension containing three of them, because five kinds had
    no emitter and the Builder cannot see a loss that happens after it finishes. An
    input-side check passes in exactly that situation, which is why this one reads the
    output directory instead.
    """
    import re

    out = tmp_path / "out"
    _run(out)
    plan = (out / "MIGRATION_PLAN.md").read_text(encoding="utf-8")
    emitted = {p.name for p in out.rglob("*.java")}

    converted = re.findall(r"^\| `[^`]+` \| [^|]* \| converted \| ([^|]+?) \|", plan, re.M)
    named = [t.strip().strip("`").split("/")[-1] for t in converted
             if t.strip().strip("`").endswith(".java")]
    assert named, "no converted row named a Java file — has the ledger's format changed?"
    missing = [t for t in named if t not in emitted]
    assert not missing, f"reported converted, never written: {missing}"
