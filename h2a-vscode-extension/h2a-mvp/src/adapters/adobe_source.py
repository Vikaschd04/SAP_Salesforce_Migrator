"""
adobe_source.py — Adobe Commerce (Magento 2) as a *source*.

**Scaffold. Not implemented.** Every method raises `NotImplementedError` with the delivery
item that will fill it in.

That is a deliberate choice, not a placeholder left lying around. The alternative — methods
that return empty lists — would let an Adobe→Hybris run complete, report "0 classes, 0
business rules, nothing unaccounted for", and look exactly like a clean migration of an
empty codebase. Everything this product exists to prevent, produced by its own scaffolding.

Registering it now, unimplemented, is what proves the architecture accepts a second
pipeline: detection, resolution, pack loading and the purity rule are all exercised
against two entries rather than one. A design that holds two only in principle is not
proven to hold two.

Implementation is Phase 2 — see docs/V2_DELIVERY_PLAN.md items 2.1–2.13.
"""

from __future__ import annotations

from pathlib import Path


class NotImplementedYet(NotImplementedError):
    """Raised by a scaffolded adapter, naming the item that will implement it.

    A distinct type so callers can tell "this platform is not built yet" from "this
    platform is broken" — the first is a roadmap fact, the second is a bug.
    """

    def __init__(self, what: str, item: str):
        super().__init__(
            f"{what} is not implemented for Adobe Commerce yet (delivery item {item}). "
            "This pipeline is registered so the architecture can be exercised against two "
            "platforms; it cannot run a migration.")
        self.item = item


# Files that only a Magento 2 codebase has. Used by detect() once 2.2 lands; listed now so
# the marker set is reviewable independently of the parsing work.
MAGENTO_MARKERS = (
    "app/etc/di.xml",
    "app/etc/env.php",
    "composer.json",            # with "type": "magento2-module" | "magento2-project"
    "registration.php",
    "etc/module.xml",
)


class AdobeCommerceSource:
    platform = "adobe-commerce"
    label = "Adobe Commerce (Magento 2 · PHP)"
    implemented = False

    def detect(self, root: str) -> dict:
        """Recognise a Magento codebase — no model calls.

        Returns a reject verdict rather than raising, because detection runs across every
        registered source adapter to decide what a codebase *is*. One unimplemented
        platform must not break identification of the others.
        """
        return {
            "verdict": "reject",
            "confidence": 0,
            "summary": ("Adobe Commerce detection is not implemented yet (item 2.2). "
                        "This codebase was not identified as any supported source."),
            "platform": self.platform,
            "implemented": False,
        }

    def read(self, root: str):
        raise NotImplementedYet("Reading an Adobe Commerce codebase", "2.3–2.9")

    def mine_behaviours(self, test_classes: list) -> list:
        raise NotImplementedYet("Mining recorded behaviour from PHPUnit", "2.6")

ADAPTER = AdobeCommerceSource()
