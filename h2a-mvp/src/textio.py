"""
textio.py — read source files that were not written on your machine.

Every reader in this engine used `read_text(encoding="utf-8")`, which is correct for
code you wrote and wrong for code you were sent. A single file breaks the whole run:

  * **Latin-1 is everywhere in Hybris.** The platform's own `extensioninfo.xml` is
    declared `ISO-8859-1`, and any estate with German, French or Nordic developers has
    Java files full of `ü`, `é` and `ø` in comments and string literals. One of those
    raised `UnicodeDecodeError` and aborted the migration before a single class was read.
  * **A `.java` file is not always Java.** Build artefacts, accidental commits and Git
    LFS pointers all turn up with source extensions.
  * **UTF-8 with a BOM** comes from Windows editors and puts an invisible `\\ufeff` at the
    top of the first token.

So: try the encodings that actually occur, in the order they actually occur, and treat a
file that is not text at all as a finding rather than an exception. Losing one file to a
clear "could not read this" line is survivable; losing the run is not.
"""

from __future__ import annotations

from pathlib import Path

# Ordered by real-world frequency, not by elegance. utf-8-sig strips a BOM if present
# and is otherwise identical to utf-8; cp1252 is a superset of latin-1 that covers the
# smart quotes Windows editors insert, so it goes first of the two single-byte guesses.
_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "iso-8859-1")

# A NUL byte in the first block means binary. Text files essentially never contain one,
# and every common binary format does.
_SNIFF_BYTES = 8192


def is_binary(raw: bytes) -> bool:
    return b"\x00" in raw[:_SNIFF_BYTES]


def read_source(path) -> tuple[str, str] | None:
    """Return (text, encoding-used), or None when the file is not text at all."""
    p = Path(path)
    try:
        raw = p.read_bytes()
    except OSError:
        return None
    if is_binary(raw):
        return None
    for enc in _ENCODINGS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    # iso-8859-1 maps every byte, so reaching here is close to impossible — but a
    # lossy read still beats an exception that ends the migration.
    return raw.decode("utf-8", errors="replace"), "utf-8/replace"


def read_text_or_empty(path) -> str:
    """For scanners that only need to look for patterns and never re-emit the content."""
    got = read_source(path)
    return got[0] if got else ""
