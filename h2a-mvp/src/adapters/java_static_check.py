"""
java_static_check.py — the `static` rung, made real. [3.10]

There is no free SAP compiler, so this is the strongest check available without a licensed
platform: does the generated Java **parse**, and does every type it names **resolve** to
something that will exist?

Parsing is definitive — javalang either builds a tree or it does not. Resolution is the
part that needs care, because a Hybris extension names three different kinds of type and
only one of them is in the output:

    emitted     a class this migration wrote
    generated   `AcmeLoyaltyAccountModel` — the *platform* writes it during the build,
                from the itemtype declared in items.xml. Absent from the output and
                entirely resolvable, provided the itemtype is actually declared
    platform    `FlexibleSearchQuery`, `ModelService` — SAP's own API, matched against a
                stub list rather than a real classpath

Anything in none of those is unresolved, and that is a defect in the output rather than a
gap in this checker. The distinction matters most for the second bucket: treating a
generated model as missing would bury every genuine problem under a hundred false ones, and
treating it as present *without checking items.xml* would miss the case that actually
happens — a DAO written for an itemtype nobody declared.

This rung cannot see type mismatches, missing overrides, or anything else that needs real
type checking. `assurance.STATIC` says so, and says it in the sign-off.
"""

from __future__ import annotations

import re
from pathlib import Path

import javalang

#: SAP Commerce API this generator emits references to. A stub classpath, not a real one:
#: it is a list of names, checked for presence, and it grows as the emitters do.
PLATFORM_TYPES = {
    # servicelayer
    "FlexibleSearchQuery", "FlexibleSearchService", "SearchResult",
    "ModelService", "SessionService", "UserService", "MediaService",
    "InterceptorContext", "InterceptorException", "ValidateInterceptor",
    "PrepareInterceptor", "InitDefaultsInterceptor", "LoadInterceptor",
    "RemoveInterceptor",
    # cronjob
    "AbstractJobPerformable", "PerformResult", "CronJobModel", "CronJobResult",
    "CronJobStatus",
    # events
    "AbstractEventListener", "AbstractEvent", "EventService",
    # config / common
    "ConfigurationService", "Configuration", "Registry", "ItemModel", "GenericItem",
    "Required", "Resource", "Autowired",
}

#: java.lang, plus the handful of java.util types worth resolving without an import.
_JDK = {
    "String", "Integer", "Long", "Double", "Float", "Boolean", "Byte", "Short",
    "Character", "Object", "Number", "Math", "System", "Exception", "RuntimeException",
    "IllegalArgumentException", "IllegalStateException", "UnsupportedOperationException",
    "NullPointerException", "Override", "Deprecated", "SuppressWarnings", "Comparable",
    "Iterable", "Runnable", "Class", "Enum", "Void", "void", "int", "long", "double",
    "float", "boolean", "byte", "short", "char",
    "List", "Map", "Set", "Collection", "ArrayList", "HashMap", "HashSet", "Optional",
    "Date", "Arrays", "Collections", "Objects", "BigDecimal", "BigInteger", "Stream",
}


def _issue(rule, filename, message, fix, line=0):
    return {"rule": rule, "file": filename, "line": line, "severity": "critical",
            "message": message, "fix": fix}


def parse(code: str, filename: str) -> tuple:
    """`(tree, issues)`. A file that does not parse cannot be checked further."""
    try:
        return javalang.parse.parse(code or ""), []
    except Exception as e:
        detail = str(e)[:160]
        return None, [_issue(
            "java_syntax", filename,
            f"generated Java does not parse: {detail}",
            "This is a defect in the generated file, not in the source. It cannot compile "
            "and no further static check is meaningful until it parses.")]


def _declared_in(tree) -> set:
    names = set()
    for kind in (javalang.tree.ClassDeclaration, javalang.tree.InterfaceDeclaration,
                 javalang.tree.EnumDeclaration):
        for _, node in tree.filter(kind):
            names.add(node.name)
    return names


def _qualified(node) -> bool:
    return getattr(node, "sub_type", None) is not None


def _leaf(node) -> str:
    """The type name at the end of a qualified reference.

    javalang models `java.math.BigDecimal` as a ReferenceType named `java` whose
    `sub_type` chain ends at `BigDecimal` — so reading `.name` reports `java` and `math`
    as undeclared types. That fired on this checker's own test and would have fired on
    every BigDecimal signature the service emitter produces.
    """
    while getattr(node, "sub_type", None) is not None:
        node = node.sub_type
    return getattr(node, "name", "") or ""


def _referenced(tree) -> set:
    """Type names the file names, ignoring the ones it declares itself.

    A qualified name is taken at its word: whether `com.other.Thing` exists is a question
    only a real classpath answers, and this rung does not claim to be one.
    """
    # `filter` yields the nested halves of a qualified name as well as the whole, so
    # `com.other.Thing` arrives as three nodes and `Thing` looks like a bare reference.
    # Only the outermost node of each chain is a reference the file actually made.
    nested = {id(n.sub_type) for _, n in tree.filter(javalang.tree.ReferenceType)
              if n.sub_type is not None}

    out = set()
    for _, node in tree.filter(javalang.tree.ReferenceType):
        if id(node) in nested or _qualified(node):
            continue
        out.add(_leaf(node))
    for _, node in tree.filter(javalang.tree.ClassCreator):
        if node.type is not None and not _qualified(node.type):
            out.add(_leaf(node.type))
    return {n for n in out if n}


def generated_model_types(items_xml: str) -> set:
    """`<itemtype code="AcmeLoyaltyAccount">` → `AcmeLoyaltyAccountModel`.

    These do not exist in the output and are not missing: the platform build writes them.
    Reading items.xml rather than assuming any `*Model` resolves is the point — a DAO
    written for an itemtype nobody declared is exactly the failure worth catching.
    """
    return {f"{m}Model" for m in re.findall(r'<itemtype\s+code="(\w+)"', items_xml or "")}


def check(code: str, filename: str, *, emitted: set | None = None,
          items_xml: str = "") -> list:
    """Every static problem in one generated Java file."""
    tree, issues = parse(code, filename)
    if tree is None:
        return issues

    known = set(_JDK) | set(PLATFORM_TYPES) | set(emitted or set())
    known |= generated_model_types(items_xml)
    known |= _declared_in(tree)
    # An explicit import resolves its own name; whether the package exists is a question
    # only a real classpath can answer, and this rung does not claim to.
    for _, imp in tree.filter(javalang.tree.Import):
        known.add((imp.path or "").rsplit(".", 1)[-1])

    for name in sorted(_referenced(tree) - known):
        issues.append(_issue(
            "unresolved_type", filename,
            f"`{name}` is not declared here, not emitted by this migration, not a "
            "platform type, and not generated from items.xml",
            "Emit the missing type, import it, or declare the itemtype it is generated "
            "from. A Hybris build fails on this."))
    return issues


def check_tree(output_dir: str) -> dict:
    """Check every generated Java file in an emitted extension. [3.10]

    Returns `{files, issues, rung}` — and the rung is `static` only when *everything*
    parses and resolves, because a partial pass is not a rung, it is a hope.
    """
    from src import assurance

    root = Path(output_dir)
    java = sorted(p for p in root.rglob("*.java"))
    items = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                      for p in root.rglob("*-items.xml"))

    sources = {p: p.read_text(encoding="utf-8", errors="replace") for p in java}
    emitted: set = set()
    for text in sources.values():
        tree, _ = parse(text, "")
        if tree is not None:
            emitted |= _declared_in(tree)

    issues = []
    for p, text in sources.items():
        issues += check(text, str(p.relative_to(root)), emitted=emitted, items_xml=items)

    return {"files": len(java), "issues": issues,
            "rung": assurance.STATIC if (java and not issues) else assurance.NONE}
