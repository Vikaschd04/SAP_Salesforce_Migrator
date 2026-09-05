"""Lift method bodies out of generated Java, so the emitter can use them. [1.48]

Phase 0 — the first migration ever run against a real model — found that the Adobe→Hybris
path *generates* Java and then throws it away. `emit_extension` never received the
artifacts; it wrote a deterministic skeleton with `UnsupportedOperationException` in every
method, and the model's output went nowhere. Mock and real runs produced byte-identical
code, which is why nine months of mock runs never showed it.

The fix is not to write the model's class instead. The two halves are good at different
things, and the split is the same one this project keeps returning to:

**The emitter knows what is derivable** — the package, the class name the planner chose,
the imports, the signatures resolved from PHP declarations, which model types exist. On
the run that found this, the model named the class `AcmePricingService` where the plan said
`PricingService`, and omitted the package line entirely.

**The model knows the logic** — and on that same run it chose `BigDecimal` for money where
the derived signature said `Double`, which is the better call and not one a type mapping
would make.

So the bodies are merged into the derived skeleton, matched by method name. What the
migration *knew* and what a model *decided* stay separable in the output, which is the
property the whole assurance layer rests on.
"""

from __future__ import annotations

import re

#: A method signature followed by a brace. Deliberately loose about the return type and
#: modifiers — this reads generated code, which varies — and strict about the shape:
#: a name, a parenthesised parameter list, then `{`.
_METHOD = re.compile(
    r"(?:public|protected|private)\s+(?:static\s+|final\s+|synchronized\s+)*"
    r"[\w<>\[\],.?\s]+?\s+(?P<name>\w+)\s*\([^)]*\)\s*(?:throws\s+[\w,.\s]+?)?\s*\{")


def _balanced_body(text: str, open_brace: int) -> str | None:
    """The text between `{` at `open_brace` and its matching `}`."""
    depth, i, n = 0, open_brace, len(text)
    in_str = in_chr = in_line = in_block = False
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_line:
            if c == "\n":
                in_line = False
        elif in_block:
            if c == "*" and nxt == "/":
                in_block, i = False, i + 1
        elif in_str:
            if c == "\\":
                i += 1
            elif c == '"':
                in_str = False
        elif in_chr:
            if c == "\\":
                i += 1
            elif c == "'":
                in_chr = False
        elif c == "/" and nxt == "/":
            in_line, i = True, i + 1
        elif c == "/" and nxt == "*":
            in_block, i = True, i + 1
        elif c == '"':
            in_str = True
        elif c == "'":
            in_chr = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace + 1:i]
        i += 1
    return None


def bodies(java: str) -> dict:
    """`method name -> body text` for every method with one.

    Braces are matched rather than pattern-matched, and string, character and comment
    contexts are skipped: a `}` inside a string literal or a comment would otherwise close
    a method early and hand back a fragment that does not compile.
    """
    out: dict = {}
    text = java or ""
    for m in _METHOD.finditer(text):
        body = _balanced_body(text, m.end() - 1)
        if body is None:
            continue
        stripped = body.strip()
        if not stripped:
            continue
        out.setdefault(m.group("name"), body)
    return out


def is_stub(body: str) -> bool:
    """A body that does nothing but refuse.

    Merging one of these over a derived TODO gains nothing and loses the marker that says
    the method is unfinished, so the skeleton's own stub is kept instead.
    """
    text = (body or "").strip()
    if not text:
        return True
    meaningful = [ln.strip() for ln in text.splitlines()
                  if ln.strip() and not ln.strip().startswith(("//", "/*", "*"))]
    if not meaningful:
        return True
    return (len(meaningful) == 1
            and ("UnsupportedOperationException" in meaningful[0]
                 or meaningful[0] in ("return null;", "return;")))


def indent(body: str, spaces: int = 8) -> list:
    """Re-indent a lifted body to sit inside the emitted class."""
    lines = [ln.rstrip() for ln in (body or "").splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()          # a lifted body ends with the indentation before its `}`
    if not lines:
        return []
    common = min((len(ln) - len(ln.lstrip()) for ln in lines if ln.strip()), default=0)
    pad = " " * spaces
    return [(pad + ln[common:]) if ln.strip() else "" for ln in lines]
