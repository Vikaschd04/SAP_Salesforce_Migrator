"""
adobe_source.py — Adobe Commerce (Magento 2) as a *source*.

**The source half is built** (items 2.1–2.12). `read()` assembles a full `ir.SourceModel`
from the modules that own each skill: PHP via tree-sitter, the di/events/crontab/db_schema
readers, EAV attributes, recorded behaviour from PHPUnit, hazards, and type resolution.

The `adobe->hybris` pipeline still cannot run, because a pipeline needs both halves and the
SAP Hybris *target* is Phase 3. That is why the class reports `implemented = True` while
`Pipeline.implemented` stays false — the distinction is deliberate: "this source is
readable" and "this migration can run" are different claims.

What this module still refuses to do is fill gaps. Files it cannot parse stay in the model
with `unreadable` set; types no declaration resolves are recorded rather than inferred; EAV
entities say the attribute set is open. A source model that looks complete because the
parts it could not read were dropped is the failure the whole layer exists to prevent —
"0 classes, nothing unaccounted for" reads exactly like a clean migration of an empty
codebase.
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
    from src.adapters.magento_config import _excluded

    out = []
    for p in base.rglob(pattern):
        if _excluded(p, base):
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
        # The tail of this message used to read "it cannot run a migration", which was
        # true while the pipeline was a scaffold and became a lie the moment it was not:
        # 1.34 made Adobe→Hybris runnable, and the *remaining* gaps are individual
        # capabilities, not the pipeline. A warning that overstates what is broken is
        # read as noise, and then so is the next one. [1.34]
        super().__init__(
            f"{what} is not implemented for Adobe Commerce yet (delivery item {item}). "
            "The migration itself runs; this capability is the part that does not, so "
            "whatever it would have contributed is absent from the output.")
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



def _preflight_summary(project: dict) -> str:
    """What was found, in the customer's own vocabulary. [1.33]"""
    mods = project.get("modules") or []
    bits = [f"{len(mods)} module(s)" + (f" [{', '.join(mods[:3])}]" if mods else ""),
            f"{project.get('php_files', 0)} PHP file(s)"]
    return "Adobe Commerce (Magento 2) project — " + ", ".join(bits) + "."


class AdobeCommerceSource:
    platform = "adobe-commerce"
    label = "Adobe Commerce (Magento 2 · PHP)"
    code_language = "PHP"      # what the source is written in, in reports
    #: The source half is built (items 2.1–2.12): detection, PHP, the XML wiring, EAV,
    #: recorded behaviour, symbols and type resolution. `adobe->hybris` still cannot run,
    #: because Pipeline.implemented needs *both* halves and the Hybris target is Phase 3.
    implemented = True

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
        # `detect` answers "what is this codebase", and nothing else. It used to also
        # answer "can a migration run against it" — hardcoded to no, with blockers citing
        # items 2.3–2.9 that shipped long ago. So `identify` printed "Migration not
        # implemented yet" directly above a list saying the pipeline was ready. Whether a
        # migration can run is `Pipeline.implemented`'s question, and it is asked one
        # level up where both halves are known. [1.38]
        return {
            "verdict": "ok",
            "confidence": confidence,
            "platform": self.platform,
            "implemented": True,
            "is_magento": True,
            "signals": signals,
            "project": project,
            "blockers": [],
            "warnings": [],
            "secrets": secrets,
            "summary": (f"Adobe Commerce (Magento 2) project detected ({confidence}% "
                        f"confidence) — {len(project['modules'])} module(s) [{mods}], "
                        f"{project['php_files']} PHP file(s)."),
        }

    def hazards(self, root: str) -> dict:
        """Magento habits that become problems on Hybris. [1.39]

        `magento_radar` already produced these and the source model already carried them;
        nothing rendered them, because the orchestrator asked the Hybris scanner instead.
        The summary is widened here to the keys the report writer reads — `files_affected`
        and `by_rule` — rather than in the scanner, so the scanner keeps its own shape and
        its own tests.
        """
        from src.adapters import magento_radar

        got = magento_radar.scan(root)
        _order = {"critical": 0, "high": 1, "medium": 2, "info": 3}
        findings = sorted(got.get("findings") or [],
                          key=lambda f: (_order.get(f["severity"], 9), f["file"], f["line"]))
        # Worst first, and each row addressable. The reports index hazards by `id` and
        # the Magento scanner did not assign one, so every consumer downstream raised
        # KeyError the moment these findings were real rather than empty. [1.39]
        by_rule: dict = {}
        for i, f in enumerate(findings, 1):
            f["id"] = f"H-{i:03d}"
            by_rule[f["rule"]] = by_rule.get(f["rule"], 0) + 1
        summary = dict(got.get("summary") or {})
        summary.setdefault("info", 0)
        summary["by_rule"] = by_rule
        summary["files_affected"] = summary.get("files", len({f["file"] for f in findings}))
        return {"findings": findings, "summary": summary}

    def preflight(self, root: str) -> dict:
        """Is there an Adobe Commerce estate here worth migrating? [1.33]

        Built on `detect`, which already knows what a Magento module looks like, so the
        two cannot disagree about whether this is Adobe Commerce. The gate this replaces
        looked for Java and Angular, and told a Magento project full of PHP that "there
        is nothing to migrate".

        Refuses on the two things that make a run pointless rather than merely thin: the
        path is not a codebase, or it is one and there is no PHP in it.
        """
        from pathlib import Path

        got = self.detect(root)
        p = Path(root)
        # `detect` folds "not implemented yet" into its own verdict and blockers. That is
        # a fact about this adapter's maturity, not about the customer's codebase, and
        # refusing an unrunnable pipeline is `pipeline.require_runnable`'s job. Preflight
        # answers only "is there an estate here worth migrating", so the blockers are
        # built here rather than inherited.
        if not p.exists() or not p.is_dir():
            blockers = ["That path is not a readable folder."]
        elif not got.get("is_magento"):
            blockers = ["This does not look like an Adobe Commerce (Magento 2) codebase — "
                        "no `registration.php`, `etc/module.xml` or Magento composer type "
                        "was found."]
        elif not (got.get("project", {}) or {}).get("php_files"):
            blockers = ["No PHP sources were found — there is nothing to migrate."]
        else:
            blockers = []

        project = dict(got.get("project") or {})
        warnings = list(got.get("warnings") or [])
        if project.get("modules") and not project.get("db_schema_files"):
            # An estate with code and no declared tables converts logic that reads
            # entities the target will not have. Worth knowing before paying for a run.
            warnings.append(
                "No `db_schema.xml` was found, so no data model can be derived. Services "
                "will be generated against types this extension does not declare.")

        return {
            "ok": not blockers,
            "verdict": "reject" if blockers else "ok",
            "confidence": got.get("confidence", 0),
            "project": project,
            "signals": list(got.get("signals") or []),
            "blockers": blockers,
            "warnings": warnings,
            "secrets": list(got.get("secrets") or []),
            "counts": {"php_files": project.get("php_files", 0),
                       "modules": len(project.get("modules") or [])},
            "summary": (blockers[0] if blockers else _preflight_summary(project)),
        }

    def read(self, root: str):
        """The whole Magento codebase as an `ir.SourceModel`. [2.3–2.12]

        Assembly only: every part is read by the module that owns that skill, and this
        puts them behind one contract. The alternative — a second set of readers here —
        is two things to keep correct that would quietly disagree.

        What it deliberately does *not* do is fill gaps. Units the PHP reader could not
        parse arrive with `unreadable` set and stay in the model; types no declaration
        resolves are recorded as such rather than inferred; EAV entities carry a note
        saying the set is open. A source model that looks complete because the parts it
        could not read were dropped is the failure this whole layer exists to prevent.
        """
        from src import ir
        from src.adapters import (magento_config, magento_eav, magento_radar,
                                  php_phpunit_mining, php_reader, php_types)

        if not php_reader.available():
            raise NotImplementedYet(
                "Reading PHP requires tree-sitter (pip install tree-sitter "
                "tree-sitter-php); it is an optional dependency", "2.3")

        all_units = php_reader.read_tree(root)
        units = [u for u in all_units if not u.is_test and not u.unreadable
                 and u.layer != "Script"]
        tests = [u for u in all_units if u.is_test]
        unreadable = [u for u in all_units if u.unreadable]
        # A PHP file with no class — registration.php, a config array. Not migratable and
        # not lost: it gets a row saying which it is.
        skipped = [u for u in all_units if u.layer == "Script" and not u.unreadable]

        di = magento_config.read_di(root)
        magento_config.classify_plugins(root, di["plugins"])

        tables = magento_config.read_db_schema(root)
        eav = magento_eav.as_data_types(magento_eav.read_attributes(root))
        data_model = ir.DataModel(types=tables + eav, relations=[], enums=[])

        behaviours = [
            ir.RecordedBehaviour(
                id=b["id"], label=b["label"], target_unit=b["source_class"],
                target_method=b["target_method"],
                expected={"args": b["args"], "expected": b["expected"],
                          "expects_exception": b["expects_exception"]},
                source_file=b["test_class"])
            for b in php_phpunit_mining.mine(
                [{"class_name": u.name, "source": u.source} for u in tests])
        ]

        hazards = [
            ir.Hazard(id=f"H-{i + 1:03d}", rule=f["rule"], severity=f["severity"],
                      file=f["file"], line=f["line"], source_unit=f["source_class"],
                      detail=f["hazard"], fix=f["fix"])
            for i, f in enumerate(magento_radar.scan(root)["findings"])
        ]

        types = php_types.resolve(units, data_model.types)

        return ir.SourceModel(
            platform=self.platform, root=root, units=units, tests=tests,
            unreadable=unreadable, skipped=skipped, data_model=data_model,
            jobs=magento_config.read_crontab(root),
            processes=[],            # Magento has no process-definition equivalent
            behaviours=behaviours, hazards=hazards,
            dependency_order=[u.name for u in units],
            extra={
                # Wiring the IR does not model yet. Carried verbatim rather than dropped,
                # because it is how the PHP is *reached* — and that is the first thing a
                # migration loses.
                "di": di,
                # A controller's URL is assembled from `etc/*/routes.xml`, the
                # directory and the class name — none of it is in the class. Every
                # other `etc/` file was read and this one was not, so controllers
                # arrived looking like ordinary classes with an `execute()`. [1.53]
                "routes": magento_config.read_routes(root),
                "observers": magento_config.read_events(root),
                "unresolved_types": php_types.unresolved_by_unit(types),
                "type_resolutions": types["resolutions"],
            },
        )

    def symbols(self, text: str) -> list:
        """PHP method declarations, from the AST. [2.11]"""
        from src.adapters import php_reader
        return php_reader.symbols(text)

    def mine_behaviours(self, test_classes: list) -> list:
        """Recorded input→output facts from the customer's PHPUnit suite. [2.9]

        Same contract and same output shape as the Hybris side: the neutral
        characterization layer must not care which platform recorded the behaviour.
        """
        from src.adapters import php_phpunit_mining as pm
        return pm.mine(test_classes)

ADAPTER = AdobeCommerceSource()
