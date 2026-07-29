"""
generate_lwc.py — Angular (Spartacus) component → Lightning Web Component.

Translates one Angular component into a deployable LWC bundle
(`.js` / `.html` / `.css` / `.js-meta.xml` + a Jest test) and, when the component
reads data, a thin `@AuraEnabled` Apex controller it wires to. The heavy lifting is
an LLM call grounded in the component source, its template, styles, the injected
service source, the SObject schema, and retrieved LWC reference docs.

Mirrors `generate.py`'s contract:
  - `mock`/offline → deterministic, structurally-valid stub (clearly labelled),
    so the frontend path is exercisable with no key.
  - real provider → structured output (guaranteed-parseable JSON).
"""

from __future__ import annotations

import json

from src.llm import call_llm, _load_config, _get_provider
from src.schema import schema_prompt_block

# Structured-output contract for one LWC translation.
LWC_SCHEMA = {
    "type": "object",
    "properties": {
        "js": {"type": "string", "description": "Complete LWC JavaScript (extends LightningElement)."},
        "html": {"type": "string", "description": "Complete LWC template."},
        "css": {"type": "string", "description": "Component CSS (may be empty)."},
        "meta": {"type": "string", "description": "Complete .js-meta.xml (LightningComponentBundle)."},
        "test": {"type": "string", "description": "Jest test (sfdx-lwc-jest)."},
        "needs_apex": {"type": "boolean", "description": "True if the component reads/writes data via Apex."},
        "apex_controller_name": {"type": "string", "description": "Apex controller class name, if needed."},
        "apex_controller": {"type": "string", "description": "Complete @AuraEnabled Apex controller, if needed."},
        "apex_controller_test": {"type": "string", "description": "@isTest class for the controller, if needed."},
        "sobject_refs": {"type": "array", "items": {"type": "string"}},
        "mapping_notes": {"type": "string"},
    },
    "required": ["js", "html", "meta", "mapping_notes"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You are a senior Salesforce developer converting SAP Spartacus (Angular) components "
    "into production Lightning Web Components (LWC). Apply these mappings faithfully and "
    "PRESERVE ALL BEHAVIOR (validation, bounds, computed values):\n"
    "  @Input() x            -> @api x;\n"
    "  @Output() y = EventEmitter -> this.dispatchEvent(new CustomEvent('y', { detail }));\n"
    "  *ngFor=\"let i of xs\"  -> <template for:each={xs} for:item=\"i\"> … key={i.id}\n"
    "  *ngIf=\"c\"             -> <template if:true={c}> (or lwc:if)\n"
    "  {{ expr | pipe }}      -> a JS GETTER (LWC templates allow only property refs, NOT expressions)\n"
    "  (click)=\"f()\"         -> onclick={f}\n"
    "  [disabled]=\"c\"        -> disabled={c}\n"
    "  HttpClient/service REST call -> @wire or imperative call to an @AuraEnabled Apex method\n"
    "  RxJS Observable/subscribe    -> reactive property / @wire\n"
    "Rules: no expressions in the template (lift them into getters); public API props are "
    "camelCase in JS and kebab-case in markup; the .js-meta.xml must set apiVersion 60.0, "
    "isExposed true, and appropriate targets. When the component reads data, generate a thin "
    "`with sharing` Apex controller with `@AuraEnabled(cacheable=true)` read methods backed by the "
    "migrated SObjects, and a matching @isTest class."
)


def _pascal(name: str) -> str:
    return (name[0].upper() + name[1:]) if name else name


def generate_lwc(target: dict, comprehensions: dict, schema: dict, *,
                 offline: bool = False, grounding: str = "", model: str | None = None) -> dict:
    """Translate one component (`target['component']`) into an LWC bundle (+ optional Apex).

    Returns {lwc_bundle: {js, html, css, meta, test}, apex_controller: {name, main_class,
    test_class}, sobject_refs, mapping_notes}."""
    component = target.get("component", {}) or {}
    bundle = target["target_name"]                 # camelCase folder name
    class_name = _pascal(bundle)

    provider = _get_provider(_load_config())
    if provider == "mock" or offline:
        return _mock_lwc(bundle, class_name, component)

    config = _load_config()
    understanding = comprehensions.get(component.get("class_name", ""), {})
    rules = "\n".join(f"- {r}" for r in (understanding.get("business_rules") or [])) or "- (none captured)"
    services = "\n\n".join(f"// service {n}\n{src}" for n, src in (component.get("services_source") or {}).items())
    prompt = (
        f"Convert this Angular component `{component.get('class_name', bundle)}` into an LWC "
        f"bundle named `{bundle}` (JS class `{class_name}`).\n\n"
        f"@Input properties: {', '.join(component.get('inputs') or []) or '(none)'}\n"
        f"@Output events: {', '.join(component.get('outputs') or []) or '(none)'}\n"
        f"Injected services: {', '.join(component.get('injected') or []) or '(none)'}\n\n"
        f"== Business rules to preserve ==\n{rules}\n\n"
        f"== Component TypeScript ==\n{component.get('source', '')}\n\n"
        f"== Template (HTML) ==\n{component.get('template', '')}\n\n"
        f"== Styles (SCSS) ==\n{component.get('styles', '')}\n\n"
        + (f"== Injected service source ==\n{services}\n\n" if services else "")
        + f"== SObject schema (data layer) ==\n{schema_prompt_block(schema or {})}\n\n"
        + (grounding + "\n\n" if grounding else "")
        + "Return the full LWC bundle. If the component reads data, set needs_apex=true and include "
        "the @AuraEnabled Apex controller + its @isTest class."
    )
    try:
        result = call_llm(
            f"generate_lwc_{bundle}", prompt, config.get("max_tokens", {}).get("generate", 8000),
            offline=offline, system_prompt=_SYSTEM, json_schema=LWC_SCHEMA,
            effort=config.get("effort", {}).get("generate", "high"), model=model)
        parsed = result.get("parsed") or {}
    except Exception as ex:
        return _mock_lwc(bundle, class_name, component,
                         note=f"[fallback stub — generation error: {str(ex)[:120]}]")
    return _shape(parsed, bundle, class_name, component)


def _shape(parsed: dict, bundle: str, class_name: str, component: dict) -> dict:
    lwc_bundle = {
        "js": parsed.get("js") or _stub_js(class_name, component),
        "html": parsed.get("html") or _stub_html(),
        "css": parsed.get("css") or ":host {\n    display: block;\n}\n",
        "meta": parsed.get("meta") or _meta_xml(),
        "test": parsed.get("test") or _stub_test(bundle, class_name),
    }
    apex_controller = {}
    if parsed.get("needs_apex") and parsed.get("apex_controller"):
        cname = parsed.get("apex_controller_name") or f"{class_name}Controller"
        apex_controller = {"name": cname, "main_class": parsed["apex_controller"],
                           "test_class": parsed.get("apex_controller_test", "")}
    return {"lwc_bundle": lwc_bundle, "apex_controller": apex_controller,
            "sobject_refs": parsed.get("sobject_refs", []),
            "mapping_notes": parsed.get("mapping_notes", "")}


# ── Deterministic mock (keyless) ──────────────────────────────────────────────

def _api_props(component: dict) -> list[str]:
    return list(component.get("inputs") or [])


def _stub_js(class_name: str, component: dict) -> str:
    apis = _api_props(component)
    api_import = ", api" if apis else ""
    lines = [f"import {{ LightningElement{api_import} }} from 'lwc';", "",
             f"export default class {class_name} extends LightningElement {{",
             "    // [mock] deterministic stub — run with a real provider for the real translation."]
    for a in apis:
        lines.append(f"    @api {a};")
    lines += ["}", ""]
    return "\n".join(lines)


def _stub_html() -> str:
    return "<template>\n    <!-- [mock] deterministic stub -->\n</template>\n"


def _meta_xml() -> str:
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<LightningComponentBundle xmlns=\"http://soap.sforce.com/2006/04/metadata\">\n"
        "    <apiVersion>60.0</apiVersion>\n"
        "    <isExposed>true</isExposed>\n"
        "    <targets>\n"
        "        <target>lightning__AppPage</target>\n"
        "        <target>lightning__RecordPage</target>\n"
        "        <target>lightning__HomePage</target>\n"
        "    </targets>\n"
        "</LightningComponentBundle>\n"
    )


def _stub_test(bundle: str, class_name: str) -> str:
    return (
        f"import {{ createElement }} from 'lwc';\n"
        f"import {class_name} from 'c/{bundle}';\n\n"
        f"describe('c-{bundle}', () => {{\n"
        f"    afterEach(() => {{ while (document.body.firstChild) "
        f"document.body.removeChild(document.body.firstChild); }});\n\n"
        f"    it('renders without error', () => {{\n"
        f"        const element = createElement('c-{bundle}', {{ is: {class_name} }});\n"
        f"        document.body.appendChild(element);\n"
        f"        expect(element).toBeTruthy();\n"
        f"    }});\n"
        f"}});\n"
    )


def _mock_lwc(bundle: str, class_name: str, component: dict, note: str = "") -> dict:
    return {
        "lwc_bundle": {
            "js": _stub_js(class_name, component),
            "html": _stub_html(),
            "css": ":host {\n    display: block;\n}\n",
            "meta": _meta_xml(),
            "test": _stub_test(bundle, class_name),
        },
        "apex_controller": {},
        "sobject_refs": [],
        "mapping_notes": note or "[mock] Deterministic LWC stub (provider=mock).",
    }
