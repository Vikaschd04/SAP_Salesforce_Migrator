"""
preflight.py — decide whether a codebase is worth migrating, before spending anything.

Until now anything you pointed at the tool started a migration. Upload a holiday photo
album and it would dutifully find zero classes, plan nothing, and walk you through three
review gates to tell you so. That is a bad first impression and, with a real provider,
a bill for it.

So this runs first and answers four questions, all without a single model call:

    1. Is this actually a SAP Hybris codebase?   (and how confident are we)
    2. What is it — version, extensions, what it is built from?
    3. Is there anything here that blocks a migration outright?
    4. Is there anything here that should not have been uploaded at all?

Question 4 is the one people do not ask for and always need. Hybris extensions carry
`local.properties` and `*-spring.xml` files, and those routinely hold database passwords
and API tokens. Uploading them to a migration tool copies those secrets onto someone
else's disk. Finding them is cheap, and saying so before the run is the difference
between a tool and a liability.

Verdicts are deliberately three-valued. `reject` means we will not start. `warn` means
we will, and you should look first. Refusing outright on a hunch would be worse than
useless for the odd repository that is genuinely Hybris but oddly laid out.
"""

from __future__ import annotations

import re
from pathlib import Path

_SKIP_DIRS = {".git", "node_modules", "target", "build", "dist", "__pycache__",
              ".venv", "venv", ".idea", ".vscode", "__MACOSX", ".gradle"}

# Files that mean "this is Hybris" with varying force. extensioninfo.xml is definitive:
# nothing else produces one. The rest are corroborating.
_STRUCTURE = [
    ("extensioninfo.xml", 45, "extensioninfo.xml — the Hybris extension descriptor"),
    ("localextensions.xml", 25, "localextensions.xml — a Hybris platform config"),
    ("buildcallbacks.xml", 15, "buildcallbacks.xml — Hybris build hooks"),
    ("build.number", 10, "build.number — a Hybris platform build stamp"),
    ("extensions.xml", 10, "extensions.xml"),
]
_PATTERNS = [
    (re.compile(r".*-items\.xml$"), 30, "*-items.xml — the Hybris type system"),
    (re.compile(r"^items\.xml$"), 25, "items.xml — the Hybris type system"),
    (re.compile(r".*-beans\.xml$"), 12, "*-beans.xml — Hybris bean definitions"),
    (re.compile(r".*-spring\.xml$"), 10, "*-spring.xml — Spring wiring"),
    (re.compile(r".*\.impex$"), 12, "ImpEx data files"),
]

_HYBRIS_IMPORT = re.compile(r"\b(de\.hybris\.platform|de\.hybris\.bootstrap)\b")
_SPARTACUS = re.compile(r"@spartacus/|@angular/core")

# Secrets. Tuned for precision over recall: a false alarm on every run trains people to
# ignore the warning, which is worse than missing one.
_SECRETS = [
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"), "a private key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "an AWS access key id"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"), "an Anthropic API key"),
    (re.compile(r"\bsk-or-v1-[A-Za-z0-9]{20,}"), "an OpenRouter API key"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), "a GitHub token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "a Slack token"),
    # [^\S\n]* is horizontal whitespace only. Plain \s* crosses the newline, so
    # `db.password=` with an empty value would greedily match the *next* line and
    # report a placeholder as a leaked secret.
    (re.compile(r"(?im)^[^\S\n]*(?:db|datasource|jdbc)\.(?:password|pass)[^\S\n]*="
                r"[^\S\n]*(?!\$\{)(?!<)\S+"),
     "a database password"),
    (re.compile(r"(?im)^[^\S\n]*[\w.]*(?:secret|apikey|api_key|access[_.]?token)[^\S\n]*="
                r"[^\S\n]*(?!\$\{)(?!<)\S{8,}"),
     "a credential in a properties file"),
]
_SECRET_SCAN_EXT = {".properties", ".xml", ".yaml", ".yml", ".json", ".env", ".txt",
                    ".pem", ".key", ".conf", ".cfg", ".ini"}
_MAX_SECRET_BYTES = 400_000            # don't read a 2 GB file looking for a password

_VERSION_HINTS = [
    (re.compile(r"(?im)^\s*version\s*=\s*([\d][\w.\-]*)"), "build.number"),
    (re.compile(r'"@spartacus/core"\s*:\s*"[\^~]?([\d][\w.\-]*)"'), "package.json"),
]


def _walk(root: Path, limit: int = 20000):
    for p in root.rglob("*"):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if p.is_file():
            yield p
            limit -= 1
            if limit <= 0:
                return


def _read(p: Path, cap: int = _MAX_SECRET_BYTES) -> str:
    try:
        if p.stat().st_size > cap:
            return ""
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def inspect(input_dir: str) -> dict:
    """Look at a codebase and decide whether a migration should start. No LLM calls."""
    root = Path(input_dir)
    if not root.exists() or not root.is_dir():
        return _reject("That path is not a readable folder.", [])

    files = list(_walk(root))
    if not files:
        return _reject("The upload is empty.", [])

    # {reason: points} — keyed by reason so a repo with 40 ImpEx files does not look
    # forty times more like Hybris than one with a single extensioninfo.xml.
    found: dict[str, int] = {}
    signals: list[dict] = []

    def mark(why: str, pts: int, rel: str):
        if why not in found:
            found[why] = pts
            signals.append({"file": rel, "why": why})

    java, xml, impex, ng, extensions = [], [], [], [], []
    version, version_src = None, None
    secrets: list[dict] = []

    for p in files:
        name = p.name
        rel = str(p.relative_to(root))

        for fname, pts, why in _STRUCTURE:
            if name == fname:
                mark(why, pts, rel)
                if fname == "extensioninfo.xml":
                    extensions.append(_extension_name(_read(p)) or p.parent.name)
        for pat, pts, why in _PATTERNS:
            if pat.match(name):
                mark(why, pts, rel)
                break

        suffix = p.suffix.lower()
        if suffix == ".java":
            java.append(rel)
        elif suffix == ".xml":
            xml.append(rel)
        elif suffix == ".impex":
            impex.append(rel)
        elif suffix == ".ts" and name.endswith(".component.ts"):
            ng.append(rel)

        # Version + Hybris imports + secrets all come from one read.
        if suffix in _SECRET_SCAN_EXT or suffix in (".java", ".ts"):
            text = _read(p)
            if not text:
                continue
            if suffix == ".java" and _HYBRIS_IMPORT.search(text):
                mark("de.hybris.platform imports in Java sources", 25, rel)
            if version is None and name in ("build.number", "package.json"):
                for pat, src in _VERSION_HINTS:
                    m = pat.search(text)
                    if m:
                        version, version_src = m.group(1), f"{rel} ({src})"
                        break
            if suffix in _SECRET_SCAN_EXT:
                for pat, what in _SECRETS:
                    m = pat.search(text)
                    if m:
                        secrets.append({"file": rel, "what": what,
                                        "line": text[:m.start()].count("\n") + 1})
                        break                       # one finding per file is enough

    # A Spartacus storefront is a first-class input — the tool migrates it to LWC — so
    # Angular components are their own evidence, not a footnote to the Java signals.
    if ng:
        mark("Angular / Spartacus components", 35, f"{len(ng)} file(s)")
    if java:
        mark("Java sources", min(12, len(java)), f"{len(java)} file(s)")

    score = min(100, sum(found.values()))
    uniq = signals

    blockers, warnings = [], []
    if not java and not ng:
        blockers.append("No Java sources and no Angular components — there is nothing to migrate.")
    elif score < 25:
        blockers.append("This does not look like a SAP Commerce (Hybris) project. None of the "
                        "usual markers are present: no extensioninfo.xml, no *-items.xml, no "
                        "de.hybris.platform imports, and no Spartacus components.")
    if java and not any(n.endswith("items.xml") for n in [Path(x).name for x in xml]):
        warnings.append("No items.xml found — the Salesforce data model will be inferred "
                        "from code alone, which is less reliable.")
    if len(java) > 800:
        warnings.append(f"{len(java)} Java files — expect a long run; consider migrating "
                        "one extension at a time.")

    verdict = "reject" if blockers else ("warn" if (warnings or secrets) else "ok")
    return {
        "verdict": verdict,
        "is_hybris": score >= 25,
        "confidence": score,
        "project": {
            "version": version, "version_source": version_src,
            "extensions": sorted(set(e for e in extensions if e)),
            "java_files": len(java), "xml_files": len(xml),
            "impex_files": len(impex), "components": len(ng),
            "total_files": len(files),
        },
        "signals": uniq,
        "blockers": blockers,
        "warnings": warnings,
        "secrets": secrets,
        "summary": _summary(verdict, score, version, java, ng, blockers, secrets),
    }


def _extension_name(xml_text: str) -> str | None:
    m = re.search(r'<extension\b[^>]*\bname\s*=\s*"([^"]+)"', xml_text or "")
    return m.group(1) if m else None


def _reject(msg: str, signals: list) -> dict:
    return {"verdict": "reject", "is_hybris": False, "confidence": 0,
            "project": {"version": None, "version_source": None, "extensions": [],
                        "java_files": 0, "xml_files": 0, "impex_files": 0,
                        "components": 0, "total_files": 0},
            "signals": signals, "blockers": [msg], "warnings": [], "secrets": [],
            "summary": msg}


def _summary(verdict, score, version, java, ng, blockers, secrets) -> str:
    if verdict == "reject":
        return blockers[0]
    what = []
    if java:
        what.append(f"{len(java)} Java file(s)")
    if ng:
        what.append(f"{len(ng)} Angular component(s)")
    kind = ("SAP Commerce (Hybris) project" if java
            else "SAP Spartacus storefront" if ng else "SAP Commerce project")
    line = (f"{kind} detected ({score}% confidence)"
            + (f", version {version}" if version else "")
            + (" — " + ", ".join(what) if what else "") + ".")
    if secrets:
        line += (f" {len(secrets)} file(s) appear to contain credentials — review before "
                 "you continue.")
    return line
