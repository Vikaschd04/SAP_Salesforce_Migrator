"""
hybris_extension.py — the SAP Hybris extension an Adobe Commerce project becomes. [3.1, 3.4]

Everything here is deterministic. No model is asked what a table should be called or which
Java type a decimal column maps to, because those are lookups, and a lookup that goes
through an LLM is a lookup that can be wrong in a way nobody notices.

**Two Hybris idioms this has to get right, and they look similar.**

A table the source *declared* becomes a new item type: `autocreate="true" generate="true"`,
its own deployment table and typecode. A Magento **EAV extension** — attributes bolted onto
`customer` or `catalog_product` — becomes the opposite: `autocreate="false"
generate="false"` on a type Hybris already owns, contributing only the new attributes.

Emitting the second as the first is the failure mode. It produces a parallel `Customer`
item type holding half a customer, deploys perfectly, and splits the entity in two — with
the original still there, still authoritative, and now missing the fields.
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape

from src import ir

#: Neutral IR types → the Java types Hybris declares in items.xml.
_IR_TO_JAVA = {
    "String": "java.lang.String",
    "Integer": "java.lang.Integer",
    "Long": "java.lang.Long",
    "Double": "java.lang.Double",
    "BigDecimal": "java.math.BigDecimal",
    "Boolean": "java.lang.Boolean",
    "Date": "java.util.Date",
    "DateTime": "java.util.Date",
    "Binary": "java.lang.String",
}

#: Item types SAP already owns. An EAV extension contributes attributes to one of these
#: and must never declare it as new.
_PLATFORM_TYPES = {
    "customer": "Customer",
    "customer_address": "Address",
    "catalog_product": "Product",
    "catalog_category": "Category",
    "sales_order": "Order",
}

#: Custom typecodes live above 10000 by SAP's convention; below it is platform territory
#: and a collision there is a platform-level conflict, not a merge.
_TYPECODE_BASE = 10001


def pascal(name: str) -> str:
    """`acme_loyalty_account` → `AcmeLoyaltyAccount`."""
    return "".join(p[:1].upper() + p[1:] for p in re.split(r"[_\-\s]+", name or "") if p)


def _table(code: str) -> str:
    """Hybris deployment tables are lowercase and short; 30 chars is the practical cap."""
    return re.sub(r"[^a-z0-9]", "", (code or "").lower())[:30]


def java_type(ir_type: str) -> str:
    return _IR_TO_JAVA.get(ir_type or "", "java.lang.String")


def _attribute(a: dict, references: str = "") -> list:
    """One `<attribute>`.

    `references` is the target type a *declared* foreign key points at. Emitted as the
    attribute's type, it turns an integer column back into the relationship the source
    declared — which the platform can then join, validate and cascade. Without it a
    `customer_id` arrives as `java.lang.Integer` and the relationship is gone. [1.43]
    """
    q = a.get("name", "")
    lines = [f'                <attribute qualifier="{escape(q)}" '
             f'type="{escape(references) if references else java_type(a.get("type"))}">',
             '                    <persistence type="property"/>']
    mods = []
    if a.get("required"):
        mods.append('optional="false"')
    if a.get("unique"):
        mods.append('unique="true"')
    if mods:
        lines.append(f'                    <modifiers {" ".join(mods)}/>')
    if a.get("default"):
        lines.append(f'                    <defaultvalue>{escape(str(a["default"]))}'
                     "</defaultvalue>")
    if a.get("comment"):
        lines.append(f'                    <description>{escape(str(a["comment"]))}'
                     "</description>")
    lines.append("                </attribute>")
    return lines


def _is_extension(dt) -> bool:
    """Does this type add attributes to something SAP already owns?

    True for a Magento EAV entity, which the source adapter records with `extends` set to
    the entity it extends and `deployment == "eav"`.
    """
    return getattr(dt, "deployment", "") == "eav" or (
        (getattr(dt, "code", "") or "").lower() in _PLATFORM_TYPES)



def _code_of(dt) -> str:
    d = dt.to_dict() if hasattr(dt, "to_dict") else dict(dt or {})
    return d.get("code") or d.get("name") or ""


def build_items_xml(data_model, *, extension: str, references: dict | None = None) -> str:
    """`<extension>-items.xml` for a whole data model. [3.4]"""
    types = list(getattr(data_model, "types", None) or [])
    out = ['<?xml version="1.0" encoding="ISO-8859-1"?>',
           '<items xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
           '       xsi:noNamespaceSchemaLocation="items.xsd">', "",
           "    <itemtypes>"]

    typecode = _TYPECODE_BASE
    for dt in types:
        code = getattr(dt, "code", "") or ""
        attrs = list(getattr(dt, "attributes", None) or [])
        note = getattr(dt, "undeclared_note", "") or ""

        if _is_extension(dt):
            # Contributing to a type SAP owns. autocreate/generate false is the whole
            # difference between extending Customer and shadowing it.
            owner = _PLATFORM_TYPES.get(code.lower(), pascal(code))
            out += ["",
                    f"        <!-- Extends the platform's {owner}. These attributes were",
                    "             EAV rows in Magento, created at runtime by a data patch;",
                    "             here they are declared at build time. -->"]
            if note:
                out.append(f"        <!-- {escape(note)} -->")
            out += [f'        <itemtype code="{owner}" autocreate="false" generate="false">',
                    "            <attributes>"]
            for a in attrs:
                out += _attribute(
                    a, (references or {}).get((_code_of(dt), a.get('name', '')), ''))
            out += ["            </attributes>", "        </itemtype>"]
            continue

        name = pascal(code)
        out += ["",
                f'        <itemtype code="{name}" extends="GenericItem"',
                '                  autocreate="true" generate="true">',
                f'            <deployment table="{_table(name)}" typecode="{typecode}"/>',
                "            <attributes>"]
        typecode += 1
        for a in attrs:
            out += _attribute(
                a, (references or {}).get((_code_of(dt), a.get('name', '')), ''))
        out += ["            </attributes>", "        </itemtype>"]

    out += ["", "    </itemtypes>", "</items>", ""]
    return "\n".join(out)


EXTENSION_INFO = """<?xml version="1.0" encoding="ISO-8859-1"?>
<extensioninfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xsi:noNamespaceSchemaLocation="extensioninfo.xsd">
    <extension abstractclassprefix="Generated" classprefix="{prefix}"
               name="{name}" usemaven="false">
        <requires-extension name="core"/>
        <requires-extension name="commerceservices"/>
        <!-- The extension ships Backoffice configuration, so it depends on the
             Backoffice extension and declares itself as a module to it. Without both,
             the config file is written, deployed and silently never loaded. [1.41] -->
        <requires-extension name="backoffice"/>
        <coremodule generated="true" manager="{prefix}Manager"
                    packageroot="{package}"/>
        <meta key="backoffice-module" value="true"/>
    </extension>
</extensioninfo>
"""

BUILD_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!-- Standard Hybris extension build file. The platform's buildcallbacks and macros do
     the work; an extension's own build.xml is a hook point, not a build. -->
<project name="{name}" default="build">
    <import file="${{platformhome}}/resources/ant/antmacros.xml" optional="true"/>
</project>
"""


def build_extension(output_dir: str, *, name: str, package: str, data_model,
                    references: dict | None = None) -> list:
    """Write the extension skeleton and its data model. [3.1, 3.4]

    The layout is the one a Hybris developer expects, because an extension that is
    *nearly* in the right shape is worse than an obviously incomplete one: the platform's
    build finds nothing and says little.
    """
    root = Path(output_dir) / "hybris" / "bin" / "custom" / name
    prefix = pascal(name)
    created = []

    def write(rel: str, body: str):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        created.append(str(p))

    write("extensioninfo.xml",
          EXTENSION_INFO.format(name=name, prefix=prefix, package=package))
    write("build.xml", BUILD_XML.format(name=name))
    write(f"resources/{name}-items.xml",
          build_items_xml(data_model, extension=name, references=references))
    write(f"resources/{name}-spring.xml",
          '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<beans xmlns="http://www.springframework.org/schema/beans"\n'
          '       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
          '       xsi:schemaLocation="http://www.springframework.org/schema/beans\n'
          '       http://www.springframework.org/schema/beans/spring-beans.xsd">\n\n'
          "    <!-- Service and DAO beans are emitted here by item 3.2. -->\n\n"
          "</beans>\n")

    # The source tree a Hybris developer expects, created empty. An extension whose
    # src/ does not exist looks broken to the platform's build before it looks incomplete.
    pkg = Path(*package.split("."))
    for tree in ("src", "testsrc"):
        (root / tree / pkg).mkdir(parents=True, exist_ok=True)
    return created
