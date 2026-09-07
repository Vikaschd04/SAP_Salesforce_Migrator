#!/usr/bin/env python3
"""Fail if a credential is committed to this repository. [1.52]

The engine already knows what a leaked key looks like — finding them in a customer's
codebase is one of the things preflight does. It had simply never been pointed at our own
tree, and on 2026-09-07 that cost us: a live gateway key went into a test fixture, through
review, and onto a public remote. The detector that would have caught it was sitting in
`src/preflight.py` the whole time.

Two decisions make this usable rather than noisy:

**Only tracked files.** `git ls-files` is exactly what a clone contains, which is exactly
what can leak. Scanning the working tree instead flags every developer's `.env` — files
that are gitignored, were never committed, and are supposed to hold real keys.

**Only key-shaped patterns.** `preflight` also carries a `db.password=` rule, which is
right for a Java properties file in a codebase being migrated and fires constantly on our
own Python. A check that cries wolf is a check people learn to skip, and this one has to
be believed on the day it matters.

Obvious filler (`your-key-here`, `changeme`) passes without ceremony. Everything else
that is deliberately key-shaped must say so with an `allow-secret-fixture` marker, in the
line or the file header.

A marker rather than a cleverer heuristic, because the two cases are genuinely
indistinguishable by inspection: a good fixture for a *detector* has to look exactly like
the thing it detects. The synthetic key written to replace the leaked one tripped an
entropy check on the first attempt, which is the argument in miniature. A marker is
explicit, greppable, and visible in the diff where a reviewer can weigh it.

    python scripts/scan_secrets.py            # the repo
    python scripts/scan_secrets.py --staged   # what is about to be committed
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "h2a-mvp"))

#: Binary and vendored things a key cannot meaningfully hide in.
SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".pptx", ".docx",
               ".woff", ".woff2", ".ttf", ".gz", ".zip", ".lock"}
SKIP_PARTS = {"node_modules", "dist", ".venv", "__pycache__", "cache"}

#: Rules from `preflight` that describe a *credential*, by name. The others there are
#: about configuration shapes and belong to source being migrated, not to us.
WANTED = ("private key", "AWS access key id", "Anthropic API key",
          "OpenRouter API key", "API key", "GitHub token", "Slack token")

#: Obvious filler, allowed without ceremony.
_FILLER = re.compile(r"your-key-here|placeholder|changeme|\.\.\.", re.I)

#: The deliberate escape hatch, for the handful of files whose *subject* is credentials —
#: the secret detector's own tests need key-shaped strings to detect.
#:
#: A marker rather than a cleverer heuristic, because the two cases are genuinely
#: indistinguishable by inspection: a good fixture for a detector has to look exactly like
#: the thing it detects. My own synthetic replacement key tripped an entropy check, which
#: is the argument in miniature. A marker is explicit, greppable, and visible in the diff
#: where a reviewer can weigh it — which is more than any guess offers.
ALLOW = "allow-secret-fixture"


def _rules():
    from src.preflight import _SECRETS

    return [(rx, what) for rx, what in _SECRETS
            if any(w in what for w in WANTED)]


def _files(staged: bool) -> list:
    cmd = (["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"]
           if staged else ["git", "ls-files"])
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True)
    paths = []
    for line in out.stdout.splitlines():
        p = ROOT / line
        if not p.is_file() or p.suffix.lower() in SKIP_SUFFIX:
            continue
        if set(p.parts) & SKIP_PARTS:
            continue
        paths.append(p)
    return paths


def findings(staged: bool = False) -> list:
    out = []
    for p in _files(staged):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = text.splitlines()
        # A file may declare itself a fixture file in its header, which is where a test
        # about credentials says so anyway.
        if ALLOW in "\n".join(lines[:40]):
            continue
        for rx, what in _rules():
            for m in rx.finditer(text):
                hit = m.group(0)
                if _FILLER.search(hit):
                    continue
                line = text[:m.start()].count("\n") + 1
                # …or a single line may claim it, for a one-off.
                own_line = lines[line - 1] if 0 < line <= len(lines) else ""
                if ALLOW in own_line:
                    continue
                out.append({"path": str(p.relative_to(ROOT)), "line": line,
                            "what": what, "hint": hit[:6] + "…" + hit[-4:]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--staged", action="store_true",
                    help="scan what is staged for commit rather than the whole repo")
    args = ap.parse_args()

    found = findings(args.staged)
    for f in found:
        # `::error::` makes GitHub annotate the file and line directly.
        print(f"::error file={f['path']},line={f['line']}::"
              f"{f['what']} committed here ({f['hint']}). Remove it, and rotate the "
              f"credential — anything that reached a remote is already spent.")
    if found:
        print(f"\n{len(found)} credential(s) found in tracked files.", file=sys.stderr)
        return 1
    print("no credential found in tracked files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
