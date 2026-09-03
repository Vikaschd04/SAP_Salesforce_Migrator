"""
assurance.py — how strongly a migration's output has actually been checked. [3.9]

Verification was a boolean: deploy-verified, or not. That worked while there was one
target and it lent us a free compiler. It stops working the moment a second target cannot
be compiled at all, because "not verified" then covers two very different situations — a
Salesforce run where nobody asked for verification, and a Hybris run where verification is
*not available*. Those deserve different sentences and the same word gave them one.

Four rungs. A run reports the highest one it actually reached, and the sign-off says only
what that rung supports:

    none      nothing beyond this tool's own rules looked at the output
    static    parsed and resolved against the platform's API surface — no compiler ran
    compiled  the target platform's own compiler accepted it
    replayed  compiled, and the behaviours recorded from the source's tests ran against it

The ladder is ordered, and the ordering is the point: a report may never describe a run as
having reached a rung it did not, and `at_least` is how everything downstream asks.
"""

from __future__ import annotations

NONE = "none"
STATIC = "static"
COMPILED = "compiled"
REPLAYED = "replayed"

#: Ascending. Index is the rung's strength.
ORDER = (NONE, STATIC, COMPILED, REPLAYED)

#: What each rung entitles a report to say, and — the more important half — what it does
#: not. Written in the second person because a sign-off is read by someone deciding
#: whether to trust this.
CLAIMS = {
    NONE: (
        "was not checked by {platform} at all",
        "Nothing outside this tool has looked at the generated {language}. It is not "
        "known to compile.",
    ),
    STATIC: (
        "was statically checked, not compiled",
        "The generated {language} parses and its references resolve against the "
        "platform's API surface. No compiler ran, so anything a compiler alone would "
        "catch — type mismatches, missing overrides — is still open.",
    ),
    COMPILED: (
        "was compiled by {platform}",
        "{platform} accepted the generated {language}. That establishes it builds; it "
        "says nothing about whether it behaves as the source did.",
    ),
    REPLAYED: (
        "was compiled by {platform}, and the recorded behaviours ran against it",
        "The strongest claim available: it builds, and the facts recorded from the "
        "source's own test suite were replayed against it. Failures are behavioural "
        "differences, not style.",
    ),
}


def rung_of(verification: dict | None) -> str:
    """The rung a verification result reached, defaulting down rather than up."""
    v = verification or {}
    rung = str(v.get("rung") or "").lower()
    if rung in ORDER:
        return rung
    # Older results predate the ladder and only said yes/no. A bare success means the
    # compiler accepted it; it never meant the behaviours were replayed.
    if v.get("verified") or (v.get("ran") and v.get("success")):
        return COMPILED
    return NONE


def at_least(verification: dict | None, rung: str) -> bool:
    return ORDER.index(rung_of(verification)) >= ORDER.index(rung)


def describe(verification: dict | None, *, platform: str = "the target platform",
             language: str = "code") -> dict:
    """`{rung, claim, limit}` — what may be said, and what may not."""
    rung = rung_of(verification)
    claim, limit = CLAIMS[rung]
    fmt = {"platform": platform, "language": language}
    return {"rung": rung, "claim": claim.format(**fmt), "limit": limit.format(**fmt)}
