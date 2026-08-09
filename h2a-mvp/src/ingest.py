"""
ingest.py — Parse Hybris Java/Spring source files and items.xml.

Features:
  - javalang-based Java parsing: class name, layer, public methods, signatures, types
  - Layer inference by class name suffix, annotations, or Javadoc
  - items.xml parsing via xml.etree.ElementTree
  - Dependency ordering: Model → DAO → Service → Facade → Controller
  - Zero API requests
"""

import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import javalang


# ── Layer inference ──────────────────────────────────────────────────────────

# Ordered from most specific to broadest match
_LAYER_RULES = [
    # (suffix/keyword, layer)
    ("Controller", "Controller"),
    ("Resource", "Controller"),
    ("Facade", "Facade"),
    ("Service", "Service"),
    ("Dao", "DAO"),
    ("DAO", "DAO"),
    ("Repository", "DAO"),
    ("Data", "Model"),     # DTO / data class
    ("DTO", "Model"),
    ("Model", "Model"),
]

_ANNOTATION_LAYERS = {
    "RestController": "Controller",
    "Controller": "Controller",
    "RequestMapping": "Controller",
    "Service": "Service",
    "Repository": "DAO",
    "Component": "Service",
}

# Canonical dependency order — earlier layers are prerequisites of later ones
LAYER_ORDER = ["Model", "DAO", "Service", "Facade", "Controller", "Job", "Utility"]

# A class extending/implementing one of these is a Hybris scheduled job (cronjob),
# regardless of its name — the strongest, least false-positive-prone signal.
_JOB_BASE_MARKERS = ("AbstractJobPerformable", "JobPerformable", "Performable")


def _infer_layer(class_name: str, annotations: list[str],
                 extends_name: str | None = None, implements_names: list[str] | None = None) -> str:
    """
    Infer the Hybris layer of a Java class from its name, annotations, and
    superclass/interfaces.

    Priority:
      1. Job base class/interface (AbstractJobPerformable, Performable, ...) — cronjob.
      2. Spring annotations (@RestController, @Service, etc.)
      3. Class name suffix (Controller, Facade, Service, Dao, Data, Model, Job)
      4. Fallback to 'Model'
    """
    implements_names = implements_names or []
    if extends_name and any(m in extends_name for m in _JOB_BASE_MARKERS):
        return "Job"
    if any(m in name for name in implements_names for m in _JOB_BASE_MARKERS):
        return "Job"

    # Check annotations first
    for ann in annotations:
        if ann in _ANNOTATION_LAYERS:
            return _ANNOTATION_LAYERS[ann]

    # A Job-suffixed class name is checked with endswith (not substring) to avoid
    # false positives like "JobTitleService".
    if class_name.endswith("Job"):
        return "Job"

    # Check class name suffix
    for suffix, layer in _LAYER_RULES:
        if suffix in class_name:
            return layer

    return "Utility"


# ── Java parsing ─────────────────────────────────────────────────────────────

def _parse_java_file(filepath: str) -> dict | None:
    """
    Parse a single Java file using javalang.

    Returns:
        dict with keys: class_name, layer, annotations, fields, methods,
                        referenced_types, source, file.
        None if parsing fails.
    """
    path = Path(filepath)
    source = path.read_text(encoding="utf-8")

    try:
        tree = javalang.parse.parse(source)
    except javalang.parser.JavaSyntaxError as e:
        print(f"  ⚠ Parse error in {path.name}: {e}")
        return None

    # Find the first class or interface declaration
    class_decl = None
    for _, node in tree.filter(javalang.tree.ClassDeclaration):
        class_decl = node
        break
    if class_decl is None:
        for _, node in tree.filter(javalang.tree.InterfaceDeclaration):
            class_decl = node
            break

    if class_decl is None:
        return None

    class_name = class_decl.name

    # Extract annotations
    annotations = []
    if class_decl.annotations:
        for ann in class_decl.annotations:
            annotations.append(ann.name)

    # Extract the superclass and implemented interfaces (strongest signal for
    # detecting a Hybris cronjob: `extends AbstractJobPerformable<...>`).
    extends_name = None
    if getattr(class_decl, "extends", None) is not None:
        ext = class_decl.extends
        extends_name = getattr(ext, "name", None) or str(ext)
    implements_names = []
    if getattr(class_decl, "implements", None):
        for impl in class_decl.implements:
            implements_names.append(getattr(impl, "name", None) or str(impl))

    # Infer layer
    layer = _infer_layer(class_name, annotations, extends_name, implements_names)

    # Extract fields
    fields = []
    if class_decl.fields:
        for field in class_decl.fields:
            field_type = _type_to_str(field.type)
            for decl in field.declarators:
                fields.append({
                    "name": decl.name,
                    "type": field_type,
                })

    # Extract public methods (exclude constructors)
    methods = []
    decls = class_decl.body if class_decl.body else []
    for decl in decls:
        if isinstance(decl, javalang.tree.MethodDeclaration):
            is_public = "public" in (decl.modifiers or set()) or isinstance(class_decl, javalang.tree.InterfaceDeclaration)
            if is_public:
                params = []
                if decl.parameters:
                    for param in decl.parameters:
                        params.append({
                            "name": param.name,
                            "type": _type_to_str(param.type),
                        })
                return_type = _type_to_str(decl.return_type) if decl.return_type else "void"
                methods.append({
                    "name": decl.name,
                    "return_type": return_type,
                    "parameters": params,
                })

    # Collect referenced types
    referenced_types = set()
    for _, node in tree.filter(javalang.tree.ReferenceType):
        referenced_types.add(node.name)
    # Remove the class itself and common Java types
    common = {"String", "Integer", "Long", "Double", "Boolean", "Object",
              "List", "Map", "Set", "BigDecimal", "void"}
    referenced_types.discard(class_name)
    referenced_types -= common

    return {
        "class_name": class_name,
        "layer": layer,
        "annotations": annotations,
        "fields": fields,
        "methods": methods,
        "referenced_types": sorted(referenced_types),
        "source": source,
        "file": path.name,
        "is_test": _is_junit_test(tree, class_decl, class_name),
    }


def looks_like_test_file(path) -> bool:
    """Cheap text check for the scanners that never parse a full AST.

    ingest() decides properly from the AST, but repo_analyzer and domain_classifier walk
    the tree independently and only see filenames. Without this they build phantom
    domains like `OrderServiceTest` and schedule work for classes that are deliberately
    never migrated.
    """
    try:
        src = Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    if "org.junit" in src or "junit.framework" in src or "org.testng" in src:
        return True
    return "@Test" in src and Path(path).stem.endswith(("Test", "Tests", "TestCase", "IT"))


def _is_junit_test(tree, class_decl, class_name: str) -> bool:
    """Is this a JUnit test rather than production code?

    It matters twice over. Translating a Java unit test into Apex is waste — the
    Builder already writes Apex tests from the comprehension, so a ported one is noise
    nobody asked for. And these files are the raw material for characterization testing:
    they are a recorded log of how the old system actually behaved.

    Detection is by import and @Test annotation first (the only real proof), then the
    naming convention — a class called `FooTest` with no JUnit anywhere in it is
    somebody's production class and must not be excluded from the migration.
    """
    for _, node in tree.filter(javalang.tree.Import):
        p = node.path or ""
        if p.startswith(("org.junit", "junit.framework", "org.testng")):
            return True

    body = class_decl.body or []
    for decl in body:
        if not isinstance(decl, javalang.tree.MethodDeclaration):
            continue
        for ann in (decl.annotations or []):
            if (ann.name or "").split(".")[-1] in ("Test", "ParameterizedTest", "RepeatedTest"):
                return True

    # Naming alone is weak evidence, so require a test-shaped body to go with it.
    if class_name.endswith(("Test", "Tests", "TestCase", "IT")):
        return any(isinstance(d, javalang.tree.MethodDeclaration) and d.name.startswith("test")
                   for d in body)
    return False


def _type_to_str(type_node) -> str:
    """Convert a javalang type node to a readable string."""
    if type_node is None:
        return "void"

    if isinstance(type_node, javalang.tree.BasicType):
        name = type_node.name
    elif isinstance(type_node, javalang.tree.ReferenceType):
        name = type_node.name
        # Handle generics like List<ProductModel>
        if type_node.arguments:
            args = []
            for arg in type_node.arguments:
                if hasattr(arg, "type") and arg.type:
                    args.append(_type_to_str(arg.type))
            if args:
                name = f"{name}<{', '.join(args)}>"
    else:
        name = str(type_node)

    # Handle array dimensions
    if hasattr(type_node, "dimensions") and type_node.dimensions:
        name += "[]" * len(type_node.dimensions)

    return name


# ── items.xml parsing ────────────────────────────────────────────────────────

def _parse_items_xml(filepath: str) -> list[dict]:
    """
    Parse a Hybris items.xml to extract itemtype definitions.

    Returns:
        List of dicts with keys: name, description, fields.
    """
    tree = ET.parse(filepath)
    root = tree.getroot()

    item_types = []

    # Find all <itemtype> elements (handle with or without namespace)
    for itemtype in root.iter("itemtype"):
        name = itemtype.get("code", "Unknown")
        desc_el = itemtype.find("description")
        description = desc_el.text if desc_el is not None else ""

        fields = []
        attrs_el = itemtype.find("attributes")
        if attrs_el is not None:
            for attr in attrs_el.findall("attribute"):
                qualifier = attr.get("qualifier", "")
                java_type = attr.get("type", "")
                attr_desc_el = attr.find("description")
                attr_desc = attr_desc_el.text if attr_desc_el is not None else ""

                # Parse modifiers
                modifiers = {}
                mod_el = attr.find("modifiers")
                if mod_el is not None:
                    modifiers = dict(mod_el.attrib)

                # Default value: <defaultvalue> child or a `default` attribute.
                default_el = attr.find("defaultvalue")
                if default_el is not None and default_el.text:
                    default_val = default_el.text.strip()
                else:
                    default_val = attr.get("default")

                fields.append({
                    "name": qualifier,
                    "type": java_type,
                    "description": attr_desc,
                    "modifiers": modifiers,
                    "default": default_val,
                })

        item_types.append({
            "name": name,
            "description": description,
            "fields": fields,
        })

    return item_types


def _parse_enum_types(filepath: str) -> list[dict]:
    """Parse <enumtype> definitions into {name, values} — these become picklists."""
    enums = []
    try:
        root = ET.parse(filepath).getroot()
    except Exception:
        return enums
    for et in root.iter("enumtype"):
        code = et.get("code")
        if not code:
            continue
        values = [v.get("code") for v in et.findall("value") if v.get("code")]
        if values:
            enums.append({"name": code, "values": values})
    return enums


def _parse_relations(filepath: str) -> list[dict]:
    """Parse <relation> definitions from items.xml into source/target cardinality dicts."""
    relations = []
    try:
        root = ET.parse(filepath).getroot()
    except Exception:
        return relations
    for rel in root.iter("relation"):
        src = rel.find("sourceElement")
        tgt = rel.find("targetElement")
        if src is not None and tgt is not None:
            relations.append({
                "source_type": src.get("type"),
                "source_card": src.get("cardinality", "many"),
                "target_type": tgt.get("type"),
                "target_card": tgt.get("cardinality", "many"),
            })
    return relations


# ── Dependency ordering ─────────────────────────────────────────────────────

def _sort_by_dependency(classes: list[dict]) -> list[dict]:
    """
    Sort parsed classes by dependency order: Model → DAO → Service → Facade → Controller.
    Within the same layer, preserve file-system order.
    """
    layer_rank = {layer: i for i, layer in enumerate(LAYER_ORDER)}
    return sorted(classes, key=lambda c: layer_rank.get(c["layer"], 99))


# ── Public API ───────────────────────────────────────────────────────────────

def ingest(input_dir: str) -> dict:
    """
    Parse all Java files and items.xml in the input directory.

    Args:
        input_dir: Path to the Hybris source directory.

    Returns:
        dict with keys:
          - classes: list of parsed class dicts (dependency-ordered)
          - item_types: list of parsed itemtype dicts
          - dependency_order: list of class names in dependency order
          - api_requests: always 0
    """
    input_path = Path(input_dir)
    if not input_path.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    # Parse Java files recursively
    java_files = []
    for root, _, files in os.walk(input_dir):
        for file in files:
            if file.endswith(".java"):
                java_files.append(Path(root) / file)

    # JUnit tests are split out, never migrated. They are not production logic, and
    # porting them to Apex burns tokens producing code nobody wants. They are kept
    # because characterization testing replays them against the generated Apex.
    classes, test_classes = [], []
    for java_file in sorted(java_files, key=lambda p: p.name):
        parsed = _parse_java_file(str(java_file))
        if not parsed:
            continue
        (test_classes if parsed.get("is_test") else classes).append(parsed)
    if test_classes:
        print(f"  · {len(test_classes)} JUnit test class(es) held aside "
              f"(not migrated — used as recorded behaviour)")

    # Sort by dependency order
    classes = _sort_by_dependency(classes)

    # Parse items.xml recursively
    item_types = []
    relations = []
    enum_types = []
    xml_files = []
    for root, _, files in os.walk(input_dir):
        for file in files:
            if file.endswith("-items.xml") or file == "items.xml":
                xml_files.append(Path(root) / file)

    for xml_file in xml_files:
        item_types.extend(_parse_items_xml(str(xml_file)))
        relations.extend(_parse_relations(str(xml_file)))
        enum_types.extend(_parse_enum_types(str(xml_file)))

    # Frontend (Spartacus / Angular → LWC): components are appended as first-class
    # source classes (layer "Component"); framework glue / type-only files are
    # recorded so the completeness ledger can account for them.
    frontend_skipped = []
    try:
        from src.llm import _load_config
        if (_load_config().get("frontend") or {}).get("enabled", True):
            from src.frontend_ingest import ingest_frontend
            fe = ingest_frontend(input_dir)
            classes.extend(fe.get("components", []))
            frontend_skipped = fe.get("skipped", [])
    except Exception as fe_err:  # frontend parsing must never break a backend run
        print(f"  ⚠ frontend ingest skipped: {fe_err}")

    # Build dependency order list
    dependency_order = [c["class_name"] for c in classes]

    return {
        "classes": classes,
        "test_classes": test_classes,
        "item_types": item_types,
        "relations": relations,
        "enum_types": enum_types,
        "dependency_order": dependency_order,
        "frontend_skipped": frontend_skipped,
        "api_requests": 0,
    }
