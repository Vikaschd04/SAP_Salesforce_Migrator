"""
golden.py — the regression net that test counts cannot provide.

339 unit tests prove individual functions behave. They do not prove the *product* behaves:
a refactor of code generation can pass every one of them and still change what a customer
receives. That gap is exactly the risk of the v2 adapter work, so this snapshots the whole
output of a reference migration — every generated class, every report — and fails on any
unintended difference.

**What it deliberately normalises**, and why each one is genuinely environmental rather
than a behaviour we are choosing not to police:

- absolute paths — the output directory is a temp dir with a different name each run
- timestamps — a document that records when it was written must differ between runs
- the order of the model-call log — comprehension runs on a thread pool, so completion
  order is scheduler-dependent. The *set* of calls and their cache keys is compared; only
  the sequence is sorted, because thread scheduling is not product behaviour.

Everything else is compared byte for byte. Notably that includes the recipe hash and the
sign-off contract id, which were non-deterministic until the set-ordering fix — building
this harness is how that was found.

    pytest tests/test_golden.py                  # verify
    H2A_GOLDEN_UPDATE=1 pytest tests/test_golden.py   # deliberately re-baseline
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_TESTING = ROOT.parent / "Testing"
_BASELINES = Path(__file__).resolve().parent / "golden"

#: The shipped pipeline's reference migration. Kept under the original names so the
#: existing baseline and every caller of it are untouched.
CORPUS = _TESTING / "acme-commerce-hybris"
MANIFEST = _BASELINES / "manifest.json"

#: The second pipeline's. A net per pipeline, not one shared net: they convert different
#: corpora into different platforms, and a single manifest could only ever cover one.
#: Until this existed, Adobe→Hybris had no product-level regression test at all — every
#: defect found in it during 1.33 and 1.34 was found by running it by hand. [1.35]
ADOBE_CORPUS = _TESTING / "acme-commerce-magento"
ADOBE_MANIFEST = _BASELINES / "manifest_adobe.json"

# Regenerated per run by design — a snapshot of them would be noise, not signal.
SKIP_DIRS = {"checkpoints", "__pycache__"}
SKIP_FILES = {
    ".h2a_agentic_state.json",
    ".call_graph.json",
    # ORG_FIT.md reports on a *live Salesforce org* read through the `sf` CLI: its
    # username, API version, object count and collision findings are facts about an
    # external system that changes without this repository changing. It is not
    # reproducible by definition — it differs between machines, and between today and
    # tomorrow on the same machine after someone deploys. Excluded rather than
    # normalised, because normalising away the org identity, the API version and the
    # findings leaves no content to compare. Its rendering is covered by the 11 unit
    # tests in test_orgfit.py, which use a fixed org payload and are reproducible.
    "ORG_FIT.md",
}

_ISO = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\s*UTC|Z|[+-]\d{2}:\d{2})?")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_ELAPSED = re.compile(r"\b\d+\.\d+\s*(s|sec|seconds|ms|min)\b", re.I)
# A row of the model-call log: | 7 | comprehend_Foo | `model` | `key…` | cache |
_CALLROW = re.compile(r"^\|\s*\d+\s*\|\s*\S+\s*\|.*\|\s*$")


def _normalise(text: str, out_dir: Path) -> str:
    """Strip what is environmental, keep everything that is behaviour."""
    text = text.replace(str(out_dir), "<OUT>").replace(str(out_dir.resolve()), "<OUT>")
    # Every corpus, not just the Salesforce one. The Adobe path was left absolute, so a
    # report naming it differed between checkouts — and `ROOT` covers anything else under
    # the repository that finds its way into a report. [1.54]
    for corpus in (CORPUS, ADOBE_CORPUS, ROOT):
        text = text.replace(str(corpus), "<REPO>").replace(str(corpus.resolve()), "<REPO>")
    text = _ISO.sub("<TIME>", text)
    text = _DATE.sub("<DATE>", text)
    text = _ELAPSED.sub("<ELAPSED>", text)

    # The call log is a set, not a sequence: sort the contiguous block of rows so thread
    # scheduling cannot fail the comparison, while any change to which calls were made
    # (or their keys) still does.
    out, block = [], []
    for line in text.splitlines():
        if _CALLROW.match(line) and "|" in line:
            block.append(re.sub(r"^\|\s*\d+\s*\|", "| N |", line))
            continue
        if block:
            out.extend(sorted(block)); block = []
        out.append(line)
    if block:
        out.extend(sorted(block))
    return "\n".join(out)


def capture(out_dir: Path) -> dict[str, str]:
    """path → hash of normalised content, for every file the migration produced."""
    manifest: dict[str, str] = {}
    for p in sorted(out_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(out_dir)
        if set(rel.parts) & SKIP_DIRS or rel.name in SKIP_FILES:
            continue
        try:
            body = _normalise(p.read_text(encoding="utf-8"), out_dir)
        except UnicodeDecodeError:
            body = p.read_bytes().hex()
        manifest[str(rel)] = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    return manifest


def run_reference(out_dir: Path, *, engine_version: str | None = None,
                  corpus: Path | None = None) -> dict[str, str]:
    """Run a reference migration and capture it. Mock provider — free and offline."""
    # A cache of its own, thrown away after. The repo's shared cache made this harness
    # non-deterministic in a way that only showed when something invalidated it: the
    # reports carrying token counts differ between a cold and a warm run of identical
    # code, so a baseline saved cold failed every warm check afterwards. [1.51]
    cache = tempfile.mkdtemp(prefix="h2a-golden-cache-")
    env = {**os.environ,
           "H2A_PROVIDER": "mock",
           "H2A_INCREMENTAL": "false",     # a cached run would not exercise generation
           "H2A_CACHE_DIR": cache,
           "PYTHONPATH": str(ROOT)}
    if engine_version:
        env["H2A_ENGINE_VERSION"] = engine_version
    r = subprocess.run(
        [sys.executable, "-m", "src.main", "agent-migrate",
         "--input", str(corpus or CORPUS), "--output", str(out_dir)],
        cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=900)
    shutil.rmtree(cache, ignore_errors=True)
    if r.returncode != 0:
        raise AssertionError(f"reference migration failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    return capture(out_dir)


def compare(expected: dict, actual: dict) -> list[str]:
    """Human-readable differences, or an empty list."""
    diffs = []
    for path in sorted(set(expected) - set(actual)):
        diffs.append(f"MISSING   {path}  (was produced before, is not now)")
    for path in sorted(set(actual) - set(expected)):
        diffs.append(f"NEW       {path}  (not produced before)")
    for path in sorted(set(expected) & set(actual)):
        if expected[path] != actual[path]:
            diffs.append(f"CHANGED   {path}")
    return diffs


def load(path: Path | None = None) -> dict:
    path = path or MANIFEST
    return json.loads(path.read_text(encoding="utf-8"))["files"] if path.exists() else {}


def save(manifest: dict, note: str = "", path: Path | None = None,
         corpus: Path | None = None) -> None:
    path = path or MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"note": note or "Baseline of the reference migration. Regenerate deliberately: "
                         "H2A_GOLDEN_UPDATE=1 pytest tests/test_golden.py",
         "corpus": (corpus or CORPUS).name,
         "files": manifest}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
