"""
php_reader.py — PHP source into IR units, via tree-sitter. [2.3]

A real parser rather than regex, for the same reason the Java side uses javalang: the
things a migration needs from a class — what it implements, what its constructor demands,
what each method promises to return — are exactly the things regex gets wrong on the files
that matter most. A 900-line Magento model with nested closures is where a pattern-matcher
quietly returns the wrong answer, and it is also where the business rules live.

Two decisions worth stating.

**Docblocks are kept verbatim.** On the Hybris side they turned out to be a quarter of the
prompt bytes and the place business rules were actually written down. PHP is no different:
`@param`, `@return` and the prose above a method are frequently the only statement of
intent in a dynamically typed codebase, and dropping them to save tokens throws away the
part worth migrating.

**A type that is not declared is left empty, never inferred.** PHP will happily let a
property be untyped and a method return `mixed`. Recording "" means unknown, and downstream
that routes to must-review; recording a guess means a Java field of the wrong type that
compiles. The second failure is silent, so the first is the only acceptable one.
"""

from __future__ import annotations

from pathlib import Path

from src import ir

_PARSER = None


def _parser():
    """One parser per process. Building the language object is not free."""
    global _PARSER
    if _PARSER is None:
        from tree_sitter import Language, Parser
        import tree_sitter_php
        _PARSER = Parser(Language(tree_sitter_php.language_php()))
    return _PARSER


def available() -> bool:
    try:
        _parser()
        return True
    except Exception:
        return False


def _text(node) -> str:
    return node.text.decode("utf-8", "replace") if node is not None else ""


def _named(node, *types):
    return [c for c in node.children if c.type in types]


def _first(node, *types):
    return next((c for c in node.children if c.type in types), None)


_TYPE_NODES = ("primitive_type", "named_type", "optional_type", "union_type",
               "intersection_type", "qualified_name", "name")


def _type_of(node) -> str:
    """A declared type, or "" — which means *undeclared*, not `mixed`."""
    t = _first(node, *_TYPE_NODES)
    return _text(t).strip() if t is not None else ""


def _docblock(node, source: bytes) -> str:
    """The `/** ... */` immediately above a declaration, verbatim.

    Walks back over the preceding siblings rather than scanning text, so a docblock that
    belongs to something else is not attributed here.
    """
    prev = node.prev_sibling
    while prev is not None and prev.type in ("comment",):
        text = _text(prev)
        if text.startswith("/**"):
            return text
        prev = prev.prev_sibling
    return ""


def _params(method) -> list:
    out = []
    formal = _first(method, "formal_parameters")
    if formal is None:
        return out
    for p in _named(formal, "simple_parameter", "variadic_parameter",
                    "property_promotion_parameter"):
        name_node = None
        for c in p.children:
            if c.type == "variable_name":
                name_node = c
                break
        out.append({
            "name": _text(name_node).lstrip("$") or _text(_first(p, "name")),
            "type": _type_of(p),
            "promoted": p.type == "property_promotion_parameter",
            "variadic": p.type == "variadic_parameter",
        })
    return out


def _return_type(method) -> str:
    """The `: T` after the parameter list — not the first type inside it."""
    seen_params = False
    for c in method.children:
        if c.type == "formal_parameters":
            seen_params = True
            continue
        if seen_params and c.type in _TYPE_NODES:
            return _text(c).strip()
    return ""


def _methods(cls, source: bytes) -> list:
    out = []
    body = _first(cls, "declaration_list") or cls
    for m in _named(body, "method_declaration"):
        mods = [_text(x) for x in _named(m, "visibility_modifier", "static_modifier",
                                        "abstract_modifier", "final_modifier")]
        name = _text(_first(m, "name"))
        if not name:
            continue
        out.append(ir.Method(
            name=name,
            visibility=next((x for x in mods if x in ("public", "private", "protected")),
                            "public"),
            return_type=_return_type(m),
            parameters=_params(m),
            line_start=m.start_point[0] + 1,
            line_end=m.end_point[0] + 1,
            doc=_docblock(m, source),
            is_static="static" in mods,
        ))
    return out


def _properties(cls) -> list:
    out = []
    body = _first(cls, "declaration_list") or cls
    for p in _named(body, "property_declaration"):
        for el in _named(p, "property_element"):
            var = _first(el, "variable_name")
            out.append({"name": _text(var).lstrip("$"), "type": _type_of(p)})
        if not _named(p, "property_element"):
            var = next((c for c in p.children if c.type == "variable_name"), None)
            if var is not None:
                out.append({"name": _text(var).lstrip("$"), "type": _type_of(p)})
    return out


#: Magento's directory conventions. The layer is what the platform thinks a class *is*,
#: and PHP has no annotation to say so — the path is the only declaration there is.
_LAYERS = (
    ("Test", "Test"), ("Api", "Api"), ("Model/ResourceModel", "DAO"), ("Model", "Model"),
    ("Plugin", "Plugin"), ("Observer", "Observer"), ("Cron", "Cron"),
    # Admin UI before the generic ones: `Block/Adminhtml/...` and `Ui/Component/...` are
    # the *backoffice*, whose Hybris counterpart is cockpit configuration — nothing to do
    # with the storefront, which is where `View` sends them. Called them all "View" and
    # the reason attached to every one said "Spartacus composes pages from CMS
    # components", about an admin grid. [1.41]
    ("Block/Adminhtml", "AdminUi"), ("Ui/Component", "AdminUi"),
    ("Controller/Adminhtml", "Controller"),
    ("Controller", "Controller"), ("Block", "View"), ("ViewModel", "View"),
    ("Helper", "Helper"), ("Setup", "Setup"), ("Ui", "AdminUi"), ("Console", "Command"),
)


def _layer(rel_path: str, kind: str) -> str:
    if kind == "interface_declaration":
        return "Api"
    if kind == "trait_declaration":
        return "Trait"
    parts = rel_path.replace("\\", "/").split("/")
    for marker, layer in _LAYERS:
        segs = marker.split("/")
        for i in range(len(parts) - len(segs) + 1):
            if parts[i:i + len(segs)] == segs:
                return layer
    return ""


def read_file(path: str, root: str = "") -> list:
    """Every class, interface and trait in one PHP file, as `ir.SourceUnit`s.

    A file that cannot be parsed comes back as a single unit carrying `unreadable`, so it
    reaches the completeness ledger instead of disappearing — the same contract the Java
    ingest keeps.
    """
    p = Path(path)
    rel = str(p.relative_to(root)) if root else p.name
    try:
        source = p.read_bytes()
    except OSError as e:
        return [ir.SourceUnit(name=p.stem, file=rel, unreadable=f"could not read: {e}")]

    # A .php file that is not text is a build artefact, a Git LFS pointer, or corrupt.
    # tree-sitter will happily "parse" it into nothing, which would file it under
    # "no class here" — indistinguishable from a legitimate config script.
    if b"\x00" in source[:8192]:
        return [ir.SourceUnit(name=p.stem, file=rel,
                              unreadable="not a text file — binary content in a .php file")]

    try:
        tree = _parser().parse(source)
    except Exception as e:
        return [ir.SourceUnit(name=p.stem, file=rel, unreadable=f"could not parse PHP: {e}")]

    if tree.root_node.has_error:
        # Parsed with errors: tree-sitter recovers, so there is usually still a usable
        # tree. It is read anyway and the doubt is recorded, because discarding a file
        # over a syntax error the platform itself accepts would lose real code.
        note = "PHP parsed with syntax errors — structure may be incomplete"
    else:
        note = ""

    text = source.decode("utf-8", "replace")
    ns = ""
    units = []

    def visit(node):
        nonlocal ns
        if node.type == "namespace_definition":
            nn = _first(node, "namespace_name", "qualified_name", "name")
            ns = _text(nn).strip().rstrip(";")
        elif node.type in ("class_declaration", "interface_declaration", "trait_declaration"):
            name = _text(_first(node, "name"))
            if name:
                base = _first(node, "base_clause")
                impl = _first(node, "class_interface_clause")
                units.append(ir.SourceUnit(
                    name=name,
                    layer=_layer(rel, node.type),
                    file=rel,
                    source=text,
                    methods=_methods(node, source),
                    fields=_properties(node),
                    referenced_types=[_text(n) for n in (impl.children if impl else [])
                                      if n.type in ("name", "qualified_name")],
                    is_test=rel.replace("\\", "/").split("/").count("Test") > 0
                            or name.endswith("Test"),
                    unreadable=note,
                    extra={
                        "namespace": ns,
                        "fqn": f"{ns}\\{name}" if ns else name,
                        "kind": node.type.replace("_declaration", ""),
                        "extends": _text(_first(base, "name", "qualified_name")) if base else "",
                        "doc": _docblock(node, source),
                    },
                ))
        for c in node.children:
            visit(c)

    visit(tree.root_node)
    if not units:
        # A PHP file with no class in it — registration.php, a config array, a script.
        # Recorded rather than dropped: "no class here" is a fact, absence is not. The
        # syntax note carries here too, because a file that produced no class *and* did
        # not parse cleanly is far more likely to be a parse failure than a script.
        return [ir.SourceUnit(name=p.stem, file=rel, source=text, layer="Script",
                              unreadable=note,
                              extra={"namespace": ns, "kind": "script"})]
    return units


def read_tree(root: str) -> list:
    """Every PHP unit under `root`, skipping framework and build directories."""
    from src.adapters.magento_config import _excluded

    base = Path(root)
    units = []
    for p in sorted(base.rglob("*.php")):
        if _excluded(p, base):
            continue
        units += read_file(str(p), str(base))
    return units


def symbols(text: str) -> list:
    """Every method in a PHP source text, with the line range of its body. [2.11]

    The provenance layer's contract, answered from the AST rather than a regex — PHP
    declares a method as `public function name()`, with no return type where a Java-shaped
    pattern expects one, so a regex written for Java finds roughly one method in six here.
    """
    try:
        tree = _parser().parse((text or "").encode("utf-8"))
    except Exception:
        return []

    out = []

    def visit(node):
        if node.type == "method_declaration":
            name = _text(_first(node, "name"))
            if name:
                out.append({"name": name,
                            "line_start": node.start_point[0] + 1,
                            "line_end": node.end_point[0] + 1})
        for c in node.children:
            visit(c)

    visit(tree.root_node)
    return out
