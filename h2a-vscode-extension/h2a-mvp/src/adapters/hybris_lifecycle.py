"""
hybris_lifecycle.py — code the Hybris platform invoked, and what Apex needs instead. [1.21]

One detector, three callers: ingest records the hook on the parsed class, radar raises the
hazard, and the trigger emitter builds the invocation Apex is missing. They used to be
capable of disagreeing, which for a rule about *silently* lost behaviour is the wrong
place to keep two implementations.

The mapping to trigger events is the point of the module. A Hybris hook and an Apex
trigger are not the same shape, and three differences matter:

  * the platform calls the hook per record; a trigger receives up to 200
  * an interceptor chain does not re-enter; a trigger does, which is what produces
    "maximum trigger depth exceeded" from code that passed every test
  * `LoadInterceptor` has no Apex equivalent at all — there is no after-read hook — so it
    is reported as manual rather than given a trigger that would never fire
"""

from __future__ import annotations

import re

#: hook -> (what it did, trigger events or None when Apex has no equivalent)
HOOKS = {
    "ValidateInterceptor":     ("validated every save", "before insert, before update"),
    "PrepareInterceptor":      ("prepared every save", "before insert, before update"),
    "InitDefaultsInterceptor": ("populated defaults on creation", "before insert"),
    "RemoveInterceptor":       ("ran on every remove", "before delete"),
    "LoadInterceptor":         ("ran on every load", None),
}

_DECL = re.compile(
    r"\b(?:implements|extends)\s+[\w<>,\s\.]*?\b(" + "|".join(HOOKS) + r")\b"
    r"(?:\s*<\s*(\w+?)(?:Model)?\s*>)?")


def detect(source: str) -> dict | None:
    """The lifecycle hook a class implements, and the type it was registered against.

    Returns None for ordinary code, which is almost all of it.
    """
    m = _DECL.search(source or "")
    if not m:
        return None
    hook = m.group(1)
    note, events = HOOKS[hook]
    return {"hook": hook, "note": note, "events": events, "type": m.group(2) or "",
            "line": (source[:m.start()].count("\n") + 1)}
