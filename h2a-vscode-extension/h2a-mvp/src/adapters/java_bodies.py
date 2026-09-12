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


#: An import line in generated Java.
_IMPORT = re.compile(r"^\s*import\s+(static\s+)?([\w.]+(?:\.\*)?)\s*;", re.M)

#: A field declaration: a modifier, a type, a name, and either `=` or `;`. Deliberately
#: anchored to `private`/`protected`/`static`/`final` — a *public* field on the model's
#: class is part of a surface the emitter owns, and copying it would let generated code
#: widen the contract the plan settled.
_FIELD = re.compile(
    r"^[ \t]*(?P<decl>(?:private|protected)\s+(?:static\s+)?(?:final\s+)?"
    r"[\w<>\[\],.?\s]+?\s+\w+\s*(?:=[^;]*)?;)[ \t]*$", re.M)

#: A method the model added for its own use.
_PRIVATE_METHOD = re.compile(
    r"(?:private|protected)\s+(?:static\s+|final\s+)*"
    r"[\w<>\[\],.?\s]+?\s+(?P<name>\w+)\s*\([^)]*\)\s*(?:throws\s+[\w,.\s]+?)?\s*\{")


def imports(java: str) -> list:
    """Every type the generated code imports.

    A merged body is only as portable as what it names. The model wrote
    `BigDecimal.valueOf(...)` under an `import java.math.BigDecimal;` that lived on *its*
    class; dropping the import and keeping the body produces a file that does not compile
    — which the stub compiler catches, but catching is worse than not causing.
    """
    out, seen = [], set()
    for m in _IMPORT.finditer(java or ""):
        line = f"import {'static ' if m.group(1) else ''}{m.group(2)};"
        if line not in seen:
            seen.add(line)
            out.append(line)
    return out


def fields(java: str) -> list:
    """Private and protected field declarations the merged bodies rely on.

    A constant like `private static final BigDecimal RATE = ...` is part of the logic, not
    decoration: the body that uses it is meaningless without it.
    """
    return [m.group("decl").strip() for m in _FIELD.finditer(java or "")]


def helpers(java: str, *, skip: set | None = None) -> dict:
    """`name -> full source` for private methods the model wrote for its own use.

    The emitter owns the public surface — those methods come from the plan and their
    signatures are derived. A *private* helper has no such contract to violate, and a
    merged body that calls one is broken without it.
    """
    skip = skip or set()
    out: dict = {}
    text = java or ""
    for m in _PRIVATE_METHOD.finditer(text):
        name = m.group("name")
        if name in skip or name in out:
            continue
        body = _balanced_body(text, m.end() - 1)
        if body is None:
            continue
        start = text.rfind("\n", 0, m.start()) + 1
        end = m.end() + len(body) + 1          # past the closing brace
        out[name] = _dedent(text[start:end])
    return out


def _dedent(src: str) -> str:
    """Strip the common leading indentation, so a helper can be re-indented as a block.

    Without this the signature line is dedented by `.strip()` and the body lines are not,
    and the helper lands in the emitted class with its own braces two levels off.
    """
    lines = [ln.rstrip() for ln in (src or "").strip("\n").splitlines()]
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""
    common = min((len(ln) - len(ln.lstrip()) for ln in lines[1:] if ln.strip()),
                 default=0)
    first, rest = lines[0].strip(), [ln[common:] if ln.strip() else "" for ln in lines[1:]]
    return "\n".join([first, *rest])


def support(java: str, *, public_names: set | None = None) -> dict:
    """Everything a merged body needs besides itself: `{imports, fields, helpers}`.

    Split from `bodies()` because the caller merges the two differently — bodies land
    inside methods the emitter already declared; these land in the class around them.
    """
    return {"imports": imports(java),
            "fields": fields(java),
            "helpers": helpers(java, skip=public_names or set())}


#: A method's parameter list, captured so the names inside it can be read.
_PARAMS = re.compile(
    r"(?:public|protected|private)\s+(?:static\s+|final\s+|synchronized\s+)*"
    r"[\w<>\[\],.?\s]+?\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)\s*"
    r"(?:throws\s+[\w,.\s]+?)?\s*\{")


def param_names(java: str, method: str) -> list | None:
    """The parameter names the generated method used, in order. `None` if not found.

    Parameter names are local to an implementation — the interface fixes the types and
    the order, and nothing else. So when a body is merged, the *derived* types stay and
    the *model's* names come with it. Without this the body references `subtotal` while
    the signature declares `amount`, and the file does not compile: a real condition, not
    a hypothetical, since the emitter derives names from PHP and the model picks its own.
    """
    for m in _PARAMS.finditer(java or ""):
        if m.group("name") != method:
            continue
        raw = (m.group("params") or "").strip()
        if not raw:
            return []
        out = []
        for part in raw.split(","):
            tokens = part.replace("final ", " ").strip().split()
            if not tokens:
                return None
            out.append(tokens[-1].strip("[]"))
        return out
    return None


def rename_params(signature: str, names: list) -> str:
    """Re-label a derived signature's parameters, keeping its types and order.

    Only the labels change. If the arity does not match, the signature is returned
    untouched — a mismatch means the two are not the same method, and quietly reshaping
    one to look like the other is how a wrong body ends up under a right name.
    """
    head, _, rest = signature.partition("(")
    inner, _, tail = rest.rpartition(")")
    parts = [p.strip() for p in inner.split(",")] if inner.strip() else []
    if len(parts) != len(names) or not parts:
        return signature
    relabelled = []
    for part, new in zip(parts, names):
        tokens = part.split()
        if len(tokens) < 2:
            return signature
        relabelled.append(" ".join(tokens[:-1] + [new]))
    return f"{head}({', '.join(relabelled)}){tail}"


def plan_merge(generated_class: str, wanted: dict) -> dict:
    """What to merge into one emitted class, keyed the way that class names its methods.

    `wanted` maps *the name the emitter is about to write* to the candidate names it may
    appear under in the generated class, best first. The distinction matters, and getting
    it backwards is why the first version of this merged almost nothing:

    A model is told what it is building, and it writes the *platform's* method names. On
    the first real run the jobs came back with `perform`, the listeners with `onEvent`,
    the decorators with `getGrandTotal` — exactly the names the emitters emit. Keying on
    the *source* method name (`aroundGetGrandTotal`, `execute`) matched none of them.

    Where the two genuinely disagree the merge must not happen: the interceptor on that
    run emitted `onPrepare` — derived from the DI configuration — while the model wrote
    `onValidate`. Those are different hooks with different semantics, and moving a body
    from one to the other would be a wrong body under a right name.

    Returns `{bodies, imports, fields, helpers}`, where `bodies` is keyed by the emitted
    name so a caller can look up exactly what it is about to write.
    """
    text = generated_class or ""
    if not text.strip():
        return {"bodies": {}, "imports": [], "fields": [], "helpers": {}}

    found = bodies(text)
    out: dict = {}
    claimed = set()
    for emitted, candidates in (wanted or {}).items():
        for cand in candidates:
            body = found.get(cand)
            if body is not None and not is_stub(body):
                out[emitted] = body
                claimed.add(cand)
                break

    if not out:
        # Nothing merged: the imports and constants belong to logic that is not being
        # used, and carrying them would leave a file of honest stubs importing types
        # nothing in it names.
        return {"bodies": {}, "imports": [], "fields": [], "helpers": {}}

    return {"bodies": out,
            "imports": imports(text),
            "fields": fields(text),
            "helpers": helpers(text, skip=claimed)}
