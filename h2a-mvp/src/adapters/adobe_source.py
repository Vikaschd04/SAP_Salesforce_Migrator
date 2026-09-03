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

import json
import re
from pathlib import Path


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _find(base: Path, pattern: str, *, limit: int) -> list:
    """Matching files, excluding vendor/ and generated/ — neither is customer code.

    Capped because a real Magento project has tens of thousands of PHP files under
    vendor/, and detection must stay fast enough to run on every registered adapter.
    """
    out = []
    for p in base.rglob(pattern):
        parts = set(p.parts)
        if parts & {"vendor", "generated", "node_modules", "var", "pub"}:
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out


def _module_name(module_xml: Path) -> str:
    try:
        m = re.search(r'<module\s+name="([^"]+)"', module_xml.read_text(encoding="utf-8"))
        return m.group(1) if m else ""
    except Exception:
        return ""


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
        """Recognise a Magento 2 codebase — no model calls. [2.2]

        Returns a verdict rather than raising, because detection runs across every
        registered source adapter to decide what a codebase *is*. One adapter that cannot
        yet migrate must not break identification of the others — and must not refuse to
        identify what it is looking at, either. Recognising a Magento project and saying
        the migration is not built yet is a useful answer; "unrecognised" is not.

        Scoring is by *signal*, not by file count, so a small module and a full project
        both identify. Each signal is something only a Magento codebase has.
        """
        base = Path(root)
        signals: list[str] = []
        project: dict = {"modules": [], "php_files": 0}

        composer = _read_json(base / "composer.json")
        ctype = str(composer.get("type", ""))
        if ctype.startswith("magento2-"):
            signals.append(f"composer.json declares type `{ctype}`")
            project["package"] = composer.get("name", "")
        if any(k.startswith("magento/") for k in (composer.get("require") or {})):
            signals.append("composer.json requires a magento/* package")

        registrations = _find(base, "registration.php", limit=200)
        if registrations:
            signals.append(f"{len(registrations)} registration.php")

        modules = [m for m in _find(base, "module.xml", limit=200) if m.parent.name == "etc"]
        for m in modules:
            name = _module_name(m)
            if name:
                project["modules"].append(name)
        if modules:
            signals.append(f"{len(modules)} etc/module.xml declaring "
                           f"{len(project['modules'])} module(s)")

        for marker, why in ((base / "app" / "etc" / "di.xml", "app/etc/di.xml"),
                            (base / "app" / "etc" / "env.php", "app/etc/env.php")):
            if marker.exists():
                signals.append(f"{why} present")

        php = _find(base, "*.php", limit=5000)
        project["php_files"] = len(php)

        # Credentials live in app/etc/env.php in every Magento install, so this is not a
        # hypothetical: it is reported before anything is uploaded anywhere, which is the
        # only moment reporting it is any use.
        secrets = []
        env = base / "app" / "etc" / "env.php"
        if env.exists():
            secrets.append({
                "file": "app/etc/env.php",
                "detail": "Magento keeps database credentials, the crypt key and cache "
                          "backend passwords here. Exclude it, or rotate afterwards.",
            })

        confidence = min(100, 25 * len(signals))
        recognised = confidence >= 50
        if not recognised:
            return {
                "verdict": "reject", "confidence": confidence, "platform": self.platform,
                "implemented": False, "signals": signals, "project": project,
                "blockers": [], "warnings": [], "secrets": secrets,
                "summary": "Not identified as an Adobe Commerce (Magento 2) codebase.",
            }

        mods = ", ".join(project["modules"][:4]) or "no named modules"
        return {
            "verdict": "not_yet_supported",
            "confidence": confidence,
            "platform": self.platform,
            "implemented": False,
            "is_magento": True,
            "signals": signals,
            "project": project,
            "blockers": [
                "Reading an Adobe Commerce codebase is not implemented yet (items 2.3–2.9). "
                "This is a recognised Magento project, and the migration cannot run against "
                "it — those are two different statements and the second one is not a "
                "detection failure."
            ],
            "warnings": [],
            "secrets": secrets,
            "summary": (f"Adobe Commerce (Magento 2) project detected ({confidence}% "
                        f"confidence) — {len(project['modules'])} module(s) [{mods}], "
                        f"{project['php_files']} PHP file(s). Migration not implemented yet."),
        }

    def read(self, root: str):
        raise NotImplementedYet("Reading an Adobe Commerce codebase", "2.3–2.9")

    def mine_behaviours(self, test_classes: list) -> list:
        raise NotImplementedYet("Mining recorded behaviour from PHPUnit", "2.6")

ADAPTER = AdobeCommerceSource()
