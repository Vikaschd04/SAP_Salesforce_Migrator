"""
metadata_generator.py — Compiler translating Hybris items.xml configurations
directly into Salesforce DX Custom Object and Field metadata XML configurations.
"""

import os
from pathlib import Path
import xml.etree.ElementTree as ET


def generate_salesforce_metadata(items_xml_path: str, output_dir: str):
    """
    Parse items.xml, compile definitions to custom SObjects and custom fields XML templates.
    """
    if not os.path.exists(items_xml_path):
        raise FileNotFoundError(f"Source metadata file not found at: {items_xml_path}")

    # Parse XML file
    tree = ET.parse(items_xml_path)
    root = tree.getroot()

    # Map itemtype declarations
    itemtypes = []
    for item in root.findall(".//itemtype"):
        code = item.get("code")
        if not code:
            continue
        
        fields = []
        for attr in item.findall(".//attribute"):
            qualifier = attr.get("qualifier")
            attr_type = attr.get("type")
            if qualifier and attr_type:
                fields.append({
                    "name": qualifier,
                    "type": attr_type
                })
        
        itemtypes.append({
            "name": code,
            "fields": fields
        })

    # Map relationship declarations
    relations = []
    for rel in root.findall(".//relation"):
        source = rel.find("sourceElement")
        target = rel.find("targetElement")
        if source is not None and target is not None:
            relations.append({
                "source_type": source.get("type"),
                "source_card": source.get("cardinality", "many"),
                "target_type": target.get("type"),
                "target_card": target.get("cardinality", "many")
            })

    # Write target Salesforce XML files
    base_path = Path(output_dir) / "force-app" / "main" / "default" / "objects"
    base_path.mkdir(parents=True, exist_ok=True)

    # 1. Write Custom Object files
    for item in itemtypes:
        obj_name = f"{item['name']}__c"
        obj_dir = base_path / obj_name
        fields_dir = obj_dir / "fields"
        fields_dir.mkdir(parents=True, exist_ok=True)

        # Write object meta definition
        obj_meta_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <deploymentStatus>Deployed</deploymentStatus>
    <label>{item['name']}</label>
    <pluralLabel>{item['name']}s</pluralLabel>
    <sharingModel>ReadWrite</sharingModel>
    <visibility>Public</visibility>
</CustomObject>
"""
        with open(obj_dir / f"{obj_name}.object-meta.xml", "w", encoding="utf-8") as f:
            f.write(obj_meta_xml)

        # Write Custom Field definitions (capitalise first letter to match the
        # schema/Apex convention: totalAmount -> TotalAmount__c).
        for field in item["fields"]:
            q = field["name"]
            field_name = f"{q[:1].upper()}{q[1:]}__c"
            sf_type, extra_nodes = _map_datatype(field["type"])
            
            field_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>{field_name}</fullName>
    <label>{field['name']}</label>
    <type>{sf_type}</type>
{extra_nodes}
</CustomField>
"""
            with open(fields_dir / f"{field_name}.field-meta.xml", "w", encoding="utf-8") as f:
                f.write(field_xml)

    # 2. Write Relation Custom Field lookups
    for rel in relations:
        # Check parent-child lookup structures: source cardinality = "one", target cardinality = "many"
        # This translates to a Lookup custom field on target pointing to source object!
        if rel["source_card"] == "one" and rel["target_card"] == "many":
            child_obj = f"{rel['target_type']}__c"
            parent_obj = f"{rel['source_type']}__c"
            
            child_fields_dir = base_path / child_obj / "fields"
            child_fields_dir.mkdir(parents=True, exist_ok=True)
            
            lookup_field_name = f"{rel['source_type']}__c"
            lookup_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>{lookup_field_name}</fullName>
    <label>{rel['source_type']}</label>
    <type>Lookup</type>
    <referenceTo>{parent_obj}</referenceTo>
    <relationshipLabel>{rel['target_type']}s</relationshipLabel>
    <relationshipName>{rel['target_type']}s</relationshipName>
</CustomField>
"""
            with open(child_fields_dir / f"{lookup_field_name}.field-meta.xml", "w", encoding="utf-8") as f:
                f.write(lookup_xml)

    print(f"✓ Successfully compiled database schemas into Salesforce metadata DX format at: {base_path}")


# SObject-type -> the extra XML nodes that type requires.
_SF_TYPE_NODES = {
    "Text": "    <length>255</length>\n    <required>false</required>",
    "Number": "    <precision>18</precision>\n    <scale>2</scale>\n    <required>false</required>",
    "Currency": "    <precision>18</precision>\n    <scale>2</scale>\n    <required>false</required>",
    "Checkbox": "    <defaultValue>false</defaultValue>",
    "DateTime": "    <required>false</required>",
    "Date": "    <required>false</required>",
}


def _custom_field_xml(field_api: str, sf_type: str, obj_meta: dict) -> str:
    """Build a CustomField XML honoring picklist value sets, required, unique, and defaults."""
    label = field_api[:-3] if field_api.endswith("__c") else field_api
    required = field_api in obj_meta.get("required", set())
    is_unique = field_api in obj_meta.get("unique", set())
    default = (obj_meta.get("defaults", {}) or {}).get(field_api)

    body = [f"    <fullName>{field_api}</fullName>", f"    <label>{label}</label>",
            f"    <type>{sf_type}</type>"]

    if sf_type == "Picklist":
        values = (obj_meta.get("picklists", {}) or {}).get(field_api, [])
        body.append("    <valueSet>")
        body.append("        <valueSetDefinition>")
        body.append("            <sorted>false</sorted>")
        for v in values:
            is_def = "true" if (default is not None and str(default) == str(v)) else "false"
            body.append(f"            <value><fullName>{v}</fullName>"
                        f"<default>{is_def}</default><label>{v}</label></value>")
        body.append("        </valueSetDefinition>")
        body.append("    </valueSet>")
        body.append(f"    <required>{'true' if required else 'false'}</required>")
    elif sf_type == "Checkbox":
        dv = "true" if str(default).lower() in ("true", "1") else "false"
        body.append(f"    <defaultValue>{dv}</defaultValue>")
    elif sf_type in ("Number", "Currency"):
        body += ["    <precision>18</precision>", "    <scale>2</scale>",
                 f"    <required>{'true' if required else 'false'}</required>"]
        if is_unique:
            body.append("    <unique>true</unique>")
    else:  # Text, DateTime, Date, etc.
        if sf_type == "Text":
            body.append("    <length>255</length>")
            if default:
                body.append(f'    <defaultValue>"{default}"</defaultValue>')
        body.append(f"    <required>{'true' if required else 'false'}</required>")
        if is_unique and sf_type == "Text":
            body.append("    <unique>true</unique>")

    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">\n'
            + "\n".join(body) + "\n</CustomField>\n")


def write_schema_metadata(output_dir: str, schema: dict) -> list[str]:
    """
    Emit Salesforce Custom Object + Field metadata from the (reconciled) schema
    dict — the single source of truth for what objects/fields exist, *including*
    fields auto-added by schema reconciliation.

    Without this the repo-migrate output has Apex referencing custom objects that
    don't exist in the org, so any real deploy fails immediately. Driving it from
    the schema (not raw items.xml) guarantees the emitted metadata matches what
    the generated Apex was grounded against.

    Returns the list of files written.
    """
    base_path = Path(output_dir) / "force-app" / "main" / "default" / "objects"
    written = []

    for obj_api, meta in sorted(schema.items()):
        code = meta.get("code", obj_api[:-3] if obj_api.endswith("__c") else obj_api)
        obj_dir = base_path / obj_api
        fields_dir = obj_dir / "fields"
        fields_dir.mkdir(parents=True, exist_ok=True)

        obj_meta_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">\n'
            "    <deploymentStatus>Deployed</deploymentStatus>\n"
            "    <label>{label}</label>\n"
            "    <pluralLabel>{label}s</pluralLabel>\n"
            "    <nameField>\n        <label>{label} Name</label>\n        <type>Text</type>\n    </nameField>\n"
            "    <sharingModel>ReadWrite</sharingModel>\n"
            "    <visibility>Public</visibility>\n"
            "</CustomObject>\n"
        ).format(label=code)
        obj_file = obj_dir / f"{obj_api}.object-meta.xml"
        obj_file.write_text(obj_meta_xml, encoding="utf-8")
        written.append(str(obj_file))

        for field_api, sf_type in sorted(meta.get("fields", {}).items()):
            if sf_type == "Lookup":
                # build_schema names a relation's lookup field after the parent
                # object (e.g. Order__c gets a `Customer__c` lookup -> Customer__c).
                parent = field_api
                label = field_api[:-3] if field_api.endswith("__c") else field_api
                lookup_xml = (
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">\n'
                    f"    <fullName>{field_api}</fullName>\n"
                    f"    <label>{label}</label>\n"
                    f"    <type>Lookup</type>\n"
                    f"    <referenceTo>{parent}</referenceTo>\n"
                    f"    <relationshipLabel>{code}s</relationshipLabel>\n"
                    f"    <relationshipName>{code}s</relationshipName>\n"
                    "</CustomField>\n"
                )
                lf = fields_dir / f"{field_api}.field-meta.xml"
                lf.write_text(lookup_xml, encoding="utf-8")
                written.append(str(lf))
                continue
            field_file = fields_dir / f"{field_api}.field-meta.xml"
            field_file.write_text(_custom_field_xml(field_api, sf_type, meta), encoding="utf-8")
            written.append(str(field_file))

    return written


def _map_datatype(java_type: str) -> tuple[str, str]:
    """Map Java datatype to Salesforce Custom Field Type."""
    t = java_type.strip()
    if t in ("java.lang.String", "String"):
        return "Text", "    <length>255</length>\n    <required>false</required>"
    if t in ("java.lang.Double", "java.math.BigDecimal", "Double"):
        return "Number", "    <precision>18</precision>\n    <scale>2</scale>\n    <required>false</required>"
    if t in ("java.lang.Boolean", "Boolean"):
        return "Checkbox", "    <defaultValue>false</defaultValue>"
    if t in ("java.lang.Integer", "Integer"):
        return "Number", "    <precision>9</precision>\n    <scale>0</scale>\n    <required>false</required>"
    
    # Fallback to Text
    return "Text", "    <length>255</length>\n    <required>false</required>"
