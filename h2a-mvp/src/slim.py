"""
slim.py — send less source to the model, without sending less meaning.

Model routing was supposed to cut cost by 50–70% and delivered about 20%, because
generation and criticism carry most of the tokens and both stay on the frontier tier.
The remaining lever is the prompt itself: every class is currently sent whole, imports
and generated accessors included, to a model that needs neither.

**The constraint that shapes everything here.** This product's entire claim is that no
business rule is silently lost. A slimmer that drops something load-bearing would break
that claim invisibly — the run would still succeed, the reports would still be green, and
a rule would simply be gone. So this only removes constructs that *cannot* carry a rule,
and it is deliberately conservative:

    removed   import statements — a model does not need `import java.util.List;`
    removed   trivial accessors — `getFoo()/setFoo()` whose body is one return or one
              assignment. A Hybris *Model class is mostly these.
    removed   runs of blank lines
    KEPT      javadoc and comments, always. On this codebase javadoc is 25% of the bytes
              and it is where the rules are actually written down — "orders above 5000
              get 10 percent off" lives in a doc comment far more often than it lives in
              an identifier. Dropping it would be the single most expensive mistake here.
    KEPT      every method with any real body, verbatim

An accessor is only removed when its body is provably trivial. `getTotal()` that computes
something is not an accessor, it is business logic wearing an accessor's name, and it
stays.

Anything unexpected — unbalanced braces, a parse that looks wrong, a saving too small to
matter — falls back to the original text. Slimming is an optimisation, and an optimisation
that can corrupt its input is not worth having.
"""

from __future__ import annotations

import re

# `public String getName() { return name; }` / `public void setName(String n) { this.name = n; }`
# Body must be a single return-a-field or assign-a-field statement; anything else is logic.
_ACCESSOR = re.compile(
    r"""^[ \t]*(?:public|protected)\s+                      # visibility
        (?:final\s+|static\s+)*                             # modifiers
        [\w<>\[\],.\s?]+?\s+                                # return type
        (get|set|is)[A-Z]\w*\s*\([^)]*\)\s*                 # accessor-shaped name
        \{\s*
        (?:return\s+[\w.]+\s*;|this\.\w+\s*=\s*\w+\s*;|\w+\s*=\s*\w+\s*;)?
        \s*\}[ \t]*$""",
    re.VERBOSE | re.MULTILINE,
)
_IMPORT = re.compile(r"^[ \t]*import\s+(static\s+)?[\w.*]+\s*;[ \t]*$", re.MULTILINE)
# Angular/Spartacus components go to the model too, and their import blocks are just as
# much noise: `import { Component, OnInit } from '@angular/core';`
_TS_IMPORT = re.compile(r"""^[ \t]*import\s+(?:[\w*\s{},]+\s+from\s+)?['"][^'"]+['"]\s*;?[ \t]*$""",
                        re.MULTILINE)
_BLANKS = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")

# Below this there is nothing worth trimming and the risk is all downside.
_MIN_CHARS = 900
# A saving this small is not worth any behavioural risk at all.
_MIN_GAIN = 0.05


def slim_java(source: str) -> tuple[str, dict]:
    """Return (text, stats). Falls back to the original whenever anything looks off."""
    original = source or ""
    stats = {"original": len(original), "slimmed": len(original), "saved_pct": 0,
             "imports_removed": 0, "accessors_removed": 0, "applied": False}
    if len(original) < _MIN_CHARS:
        return original, stats

    text = original
    is_ts = "@Component" in text or "from '@angular" in text or 'from "@angular' in text
    if is_ts:
        imports = _TS_IMPORT.findall(text)
        kept_pkgs = _ts_import_summary(text)
        text = _TS_IMPORT.sub("", text)
    else:
        imports = _IMPORT.findall(text)
        kept_pkgs = _import_summary(text)
        text = _IMPORT.sub("", text)

    # TypeScript has no Java-shaped accessors, and its class members would be damaged by
    # a regex written for Java, so that pass simply does not run there.
    accessors = 0 if is_ts else len(_ACCESSOR.findall(text))
    if accessors:
        text = _ACCESSOR.sub("", text)

    text = _BLANKS.sub("\n\n", text).strip() + "\n"
    if kept_pkgs:
        # The model still benefits from knowing what the class depends on; it just does
        # not need forty lines to be told.
        text = f"// imports: {kept_pkgs}\n{text}"
    if accessors:
        text += f"\n// ({accessors} trivial getter/setter(s) omitted — no logic)\n"

    # Sanity: a slimmer that unbalances braces has corrupted the class. Checked as a
    # delta of the imbalance, not of the raw counts — a TypeScript import carries braces
    # of its own (`import { Component } from …`), so exact counts legitimately change.
    if (text.count("{") - text.count("}")) != (original.count("{") - original.count("}")):
        return original, stats

    saved = 1 - (len(text) / len(original))
    if saved < _MIN_GAIN:
        return original, stats

    stats.update({"slimmed": len(text), "saved_pct": round(100 * saved),
                  "imports_removed": len(imports), "accessors_removed": accessors,
                  "applied": True})
    return text, stats


def _import_summary(text: str) -> str:
    """One line naming the distinctive dependencies, not the java.util noise."""
    pkgs = []
    for m in re.finditer(r"^[ \t]*import\s+(?:static\s+)?([\w.*]+)\s*;", text, re.MULTILINE):
        p = m.group(1)
        if p.startswith(("java.lang", "java.util", "java.io")):
            continue
        # Collapse to the first three segments: `de.hybris.platform` says everything
        # useful; forty variations on it say the same thing forty times.
        parts = p.split(".")
        pkgs.append(".".join(parts[:3]) if len(parts) > 3 else p.rsplit(".", 1)[0])
    seen, out = [], []
    for p in pkgs:
        if p not in seen:
            seen.append(p)
            out.append(p)
    return ", ".join(out[:8])


def _ts_import_summary(text: str) -> str:
    mods = []
    for m in re.finditer(r"""from\s+['"]([^'"]+)['"]""", text):
        p = m.group(1)
        if p not in mods:
            mods.append(p)
    return ", ".join(mods[:12])


def slim_classes(source_classes: list[dict]) -> tuple[list[dict], dict]:
    """Slim a target's source classes. Returns (classes, aggregate stats)."""
    out, before, after, applied = [], 0, 0, 0
    for c in source_classes or []:
        src = c.get("source") or ""
        text, st = slim_java(src)
        before += st["original"]
        after += st["slimmed"]
        applied += 1 if st["applied"] else 0
        out.append({**c, "source": text} if st["applied"] else c)
    return out, {"classes": len(out), "slimmed": applied, "before": before, "after": after,
                 "saved_pct": round(100 * (1 - after / before)) if before else 0}


def enabled(config: dict) -> bool:
    """On by default; `prompts.slim: false` turns it off for a side-by-side comparison."""
    import os
    env = os.environ.get("H2A_SLIM_PROMPTS")
    if env is not None:
        return env.strip().lower() in ("1", "true", "yes")
    return bool(((config or {}).get("prompts") or {}).get("slim", True))
