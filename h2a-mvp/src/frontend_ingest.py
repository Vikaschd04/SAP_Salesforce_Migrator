"""
frontend_ingest.py — Parse SAP Spartacus / Angular components for LWC migration.

The Java ingest (`ingest.py`) handles the backend. This module is its frontend
counterpart: it discovers Angular component/service files and extracts just enough
structure for the agent team to translate each component into a Lightning Web
Component (LWC). It is intentionally regex/heuristic based — no TypeScript compiler
dependency — because the heavy lifting (the actual Angular→LWC translation) is done
by the LLM from the full source, template and styles we attach here.

Emits component dicts in the SAME shape `ingest()` uses (`class_name`, `layer`,
`source`, `methods`, `referenced_types`, `file`) plus frontend extras
(`selector`, `inputs`, `outputs`, `injected`, `services_source`, `template`,
`styles`), so the agentic pipeline can consume them alongside Java classes.

Pure framework glue (NgModules) and type-only files (`*.model.ts` interfaces) carry
no business logic; they are reported in `skipped` (with a reason) rather than
converted — and surfaced in the completeness ledger so nothing is hidden.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from src.textio import read_text_or_empty

FRONTEND_COMPONENT_LAYER = "Component"

_CLASS_RE = re.compile(r"export\s+class\s+(\w+)")
_SELECTOR_RE = re.compile(r"selector\s*:\s*['\"]([^'\"]+)['\"]")
_TEMPLATE_URL_RE = re.compile(r"templateUrl\s*:\s*['\"]([^'\"]+)['\"]")
_STYLE_URLS_RE = re.compile(r"styleUrls\s*:\s*\[([^\]]*)\]")
_INPUT_RE = re.compile(r"@Input\(\)\s+(\w+)")
_OUTPUT_RE = re.compile(r"@Output\(\)\s+(\w+)")
_CONSTRUCTOR_RE = re.compile(r"constructor\s*\(([^)]*)\)", re.DOTALL)
# `private readonly foo: BarService` / `public foo: BarService`
_INJECT_PARAM_RE = re.compile(r"(?:private|public|protected|readonly|\s)+\w+\s*:\s*(\w+)")
# method or getter declarations: `foo(...) {` / `get total(): number {`
_METHOD_RE = re.compile(r"^\s*(?:public\s+|private\s+|protected\s+)?(?:async\s+)?(?:get\s+)?(\w+)\s*\([^)]*\)\s*(?::[^\{]+)?\{",
                        re.MULTILINE)
_TYPE_REF_RE = re.compile(r"\b([A-Z]\w+)\b")

_TS_KEYWORD_TYPES = {
    "Observable", "EventEmitter", "OnInit", "OnDestroy", "Component", "Input",
    "Output", "Injectable", "NgModule", "HttpClient", "BehaviorSubject", "Subject",
    "Promise", "Array", "Math", "Object", "String", "Number", "Boolean", "Date",
    "JSON", "Map", "Set",
}


def _read(path: Path) -> str:
    try:
        return read_text_or_empty(path)
    except (OSError, UnicodeDecodeError):
        return ""


def _methods(source: str) -> list[dict]:
    seen, out = set(), []
    lifecycle = {"constructor", "ngOnInit", "ngOnDestroy", "ngOnChanges", "if", "for", "while", "switch"}
    for m in _METHOD_RE.finditer(source):
        name = m.group(1)
        if name in lifecycle or name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "return_type": "", "parameters": []})
    return out


def _injected_services(source: str) -> list[str]:
    m = _CONSTRUCTOR_RE.search(source)
    if not m:
        return []
    params = m.group(1)
    return [t for t in _INJECT_PARAM_RE.findall(params) if t.endswith("Service")]


def _referenced_types(source: str, class_name: str) -> list[str]:
    refs = {t for t in _TYPE_REF_RE.findall(source)
            if t not in _TS_KEYWORD_TYPES and t != class_name}
    return sorted(refs)


def _parse_component(ts_path: Path, service_sources: dict) -> dict | None:
    source = _read(ts_path)
    cm = _CLASS_RE.search(source)
    if not cm or "@Component" not in source:
        return None
    class_name = cm.group(1)

    selector = (_SELECTOR_RE.search(source) or [None, ""])[1] if _SELECTOR_RE.search(source) else ""

    # Pull the paired template + styles (inline the referenced files).
    template = styles = ""
    tm = _TEMPLATE_URL_RE.search(source)
    if tm:
        tpl = (ts_path.parent / tm.group(1)).resolve()
        template = _read(tpl)
    sm = _STYLE_URLS_RE.search(source)
    if sm:
        for raw in re.findall(r"['\"]([^'\"]+)['\"]", sm.group(1)):
            styles += _read((ts_path.parent / raw).resolve()) + "\n"

    inputs = _INPUT_RE.findall(source)
    outputs = _OUTPUT_RE.findall(source)
    injected = _injected_services(source)
    # Attach the source of each injected service so the LLM can wire the data layer.
    svc_src = {name: service_sources[name] for name in injected if name in service_sources}

    return {
        "class_name": class_name,
        "layer": FRONTEND_COMPONENT_LAYER,
        "annotations": ["Component"],
        "fields": [],
        "methods": _methods(source),
        "referenced_types": _referenced_types(source, class_name),
        "source": source,
        "file": ts_path.name,
        # frontend extras
        "selector": selector,
        "inputs": inputs,
        "outputs": outputs,
        "injected": injected,
        "services_source": svc_src,
        "template": template.strip(),
        "styles": styles.strip(),
    }


def ingest_frontend(input_dir: str) -> dict:
    """Discover Angular components + services under `input_dir`.

    Returns {"components": [class-dict, ...], "skipped": [{class_name, layer, reason}, ...]}.
    """
    root = Path(input_dir)
    component_files, service_files, module_files, model_files = [], [], [], []
    for base, _dirs, files in os.walk(root):
        if "node_modules" in base:
            continue
        for f in files:
            p = Path(base) / f
            if f.endswith(".component.ts"):
                component_files.append(p)
            elif f.endswith(".service.ts"):
                service_files.append(p)
            elif f.endswith(".module.ts"):
                module_files.append(p)
            elif f.endswith(".model.ts"):
                model_files.append(p)

    # Index service sources by class name so components can inline them.
    service_sources: dict[str, str] = {}
    for sp in service_files:
        src = _read(sp)
        cm = _CLASS_RE.search(src)
        if cm:
            service_sources[cm.group(1)] = src

    components = []
    for cp in component_files:
        comp = _parse_component(cp, service_sources)
        if comp:
            components.append(comp)

    # Framework glue / type-only files: converted logic lives in the components, so
    # these carry no business logic. Record them (with a reason) instead of hiding them.
    skipped = []
    for mp in module_files:
        cm = _CLASS_RE.search(_read(mp))
        skipped.append({"class_name": cm.group(1) if cm else mp.stem,
                        "layer": "Module",
                        "reason": "Angular NgModule — framework glue, no business logic"})
    for mp in model_files:
        cm = _CLASS_RE.search(_read(mp))
        name = cm.group(1) if cm else mp.stem
        skipped.append({"class_name": name, "layer": "Model",
                        "reason": "TypeScript interface — type declaration only "
                                  "(maps to existing SObject fields)"})

    return {"components": components, "skipped": skipped}
