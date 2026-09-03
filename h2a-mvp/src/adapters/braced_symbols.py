"""
braced_symbols.py — method declarations in C-family source. [2.11]

Java, Apex and generated Hybris code all declare methods the same way: modifiers, an
optional return type, a name, a parameter list, a brace. One extractor serves all three,
which is why it lives in `adapters/` shared by two platforms rather than in each — but it
is emphatically *not* neutral, and PHP proves it: run this regex over a Magento model and
it finds one method out of six, because `public function name()` has no return type where
this expects one and its `function` keyword sits where the type would be.

That near-miss is the dangerous shape. It does not fail; it silently under-reports, and
provenance is the module whose entire output is "how much of the source can we account
for". A traceability report that quietly finds one method in six is worse than one that
refuses to run.
"""

from __future__ import annotations

import re

# A method declaration in Apex or Java. Deliberately conservative — it is better to miss
# an exotic signature than to claim a `for` loop is a method.
_METHOD = re.compile(
    r"^[ \t]*(?:@\w+[^\n]*\n[ \t]*)*"                       # annotations on their own lines
    r"(?:public|private|protected|global)\s+"
    r"(?:static\s+|final\s+|override\s+|virtual\s+|abstract\s+|synchronized\s+)*"
    r"(?:[\w<>\[\],.\s]+?\s+)?"                             # return type (absent on ctors)
    r"(\w+)\s*\([^)]*\)\s*(?:throws\s[\w,.\s]+)?\{",
    re.MULTILINE,
)

# Names that carry no signal — matching on these would pair unrelated code.
_GENERIC = {"get", "set", "run", "execute", "perform", "handle", "process", "toString",
            "equals", "hashCode", "init", "main"}


def _symbols(text: str) -> list[dict]:
    """Every method in a source text, with the line range of its body."""
    out = []
    for m in _METHOD.finditer(text or ""):
        name = m.group(1)
        start = (text[:m.start()].count("\n")) + 1
        # Walk braces from the opening one to find the real end of the body.
        i = text.index("{", m.end() - 1)
        depth, j = 0, i
        while j < len(text):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        end = text[:j].count("\n") + 1
        out.append({"name": name, "line_start": start, "line_end": max(start, end)})
    return out




def symbols(text: str) -> list[dict]:
    """Every method in a source text, with the line range of its body."""
    out = []
    for m in _METHOD.finditer(text or ""):
        name = m.group(1)
        start = (text[:m.start()].count("\n")) + 1
        # Walk braces from the opening one to find the real end of the body.
        i = text.index("{", m.end() - 1)
        depth, j = 0, i
        while j < len(text):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        end = text[:j].count("\n") + 1
        out.append({"name": name, "line_start": start, "line_end": max(start, end)})
    return out
