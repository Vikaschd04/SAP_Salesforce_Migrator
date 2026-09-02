"""The product-level regression test.

Unit tests prove functions behave; this proves the *product* behaves. It is the mechanism
behind the promise that the shipped Hybris→Salesforce pipeline is not disturbed by the v2
adapter work — without it, a refactor of code generation can pass all 339 unit tests and
still quietly change what a customer receives.
"""
import os

import pytest

from tests import golden


@pytest.mark.slow
def test_reference_migration_is_unchanged(tmp_path):
    actual = golden.run_reference(tmp_path / "out")

    if os.environ.get("H2A_GOLDEN_UPDATE"):
        golden.save(actual)
        pytest.skip(f"baseline rewritten — {len(actual)} files. Review the diff in git.")

    expected = golden.load()
    assert expected, ("no baseline recorded. Create one deliberately with "
                      "H2A_GOLDEN_UPDATE=1 pytest tests/test_golden.py")

    diffs = golden.compare(expected, actual)
    assert not diffs, (
        f"{len(diffs)} unintended change(s) to what the migration produces:\n  "
        + "\n  ".join(diffs[:40])
        + "\n\nIf the change was intended, re-baseline with H2A_GOLDEN_UPDATE=1 and "
          "review the manifest diff in the commit.")


@pytest.mark.slow
def test_two_identical_runs_agree(tmp_path):
    """Determinism, checked directly rather than assumed.

    This is what caught the recipe hash: it hashed a schema containing sets via `str()`,
    whose element order varies per process, so two identical runs produced different
    recipes — silently disabling incremental reuse, because target fingerprints derive
    from it and never matched the previous run's cache.
    """
    a = golden.run_reference(tmp_path / "a")
    b = golden.run_reference(tmp_path / "b")
    diffs = golden.compare(a, b)
    assert not diffs, ("two identical runs disagreed — the pipeline is not "
                       f"deterministic:\n  " + "\n  ".join(diffs[:20]))


@pytest.mark.slow
def test_v2_engine_matches_v1_exactly(tmp_path):
    """The claim the whole v2 refactor rests on.

    The adapters delegate to the same functions v1 calls, so routing a migration through
    them must change nothing a customer receives. Any difference here means the seam
    altered behaviour — which is the one thing it is not allowed to do, and the reason v1
    stays reachable until this has held for a while.
    """
    v1 = golden.run_reference(tmp_path / "v1", engine_version="v1")
    v2 = golden.run_reference(tmp_path / "v2", engine_version="v2")

    diffs = golden.compare(v1, v2)
    assert not diffs, (
        f"the v2 engine produced {len(diffs)} difference(s) from v1:\n  "
        + "\n  ".join(diffs[:30]))
    assert len(v1) > 100, "the reference migration produced suspiciously few files"
