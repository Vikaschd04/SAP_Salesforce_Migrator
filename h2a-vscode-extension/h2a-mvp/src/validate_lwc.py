"""
validate_lwc.py — objective checks for a generated LWC bundle.

The LWC counterpart to validate.py's role for Apex: deterministic, offline structural
checks that catch the common Angular→LWC porting mistakes a compiler would reject on
deploy — most importantly, expressions left inside template bindings (LWC allows only
property/getter references in `{ }`).

Returns a list of issue dicts: {severity: ERROR|WARNING, rule, message}.
"""

from __future__ import annotations

import re

# Binding content that is a bare property path (allowed): `foo`, `foo.bar`, `obj?.x`.
_PROP_RE = re.compile(r"^[A-Za-z_$][\w$]*(?:\??\.[A-Za-z_$][\w$]*)*$")
# Directive/loop bindings that are legitimately braces: for:item, iterator, key, etc.
_ALLOWED_BINDINGS = ("for:each", "for:item", "for:index", "iterator:", "key=", "if:true",
                     "if:false", "lwc:if", "lwc:elseif", "lwc:else")


def validate_lwc(bundle: dict) -> list[dict]:
    issues: list[dict] = []
    html = bundle.get("html", "") or ""
    js = bundle.get("js", "") or ""
    meta = bundle.get("meta", "") or ""

    # 1. JS must be a proper LWC module.
    if "extends LightningElement" not in js:
        issues.append({"severity": "ERROR", "rule": "lwc_class",
                       "message": "LWC JS must define a class that extends LightningElement."})
    if "export default" not in js:
        issues.append({"severity": "ERROR", "rule": "lwc_export",
                       "message": "LWC JS must have a default export."})

    # 2. Template must be wrapped in a single <template> root.
    if html and "<template" not in html:
        issues.append({"severity": "ERROR", "rule": "lwc_template_root",
                       "message": "LWC markup must be wrapped in a <template> root element."})

    # 3. THE KEY RULE — no expressions in `{ }` bindings (must be a property/getter ref).
    for m in re.finditer(r"\{([^{}]+)\}", html):
        expr = m.group(1).strip()
        if not expr or any(tok in expr for tok in _ALLOWED_BINDINGS):
            continue
        if _PROP_RE.match(expr):
            continue  # bare property path — fine
        issues.append({"severity": "ERROR", "rule": "lwc_template_expression",
                       "message": f"Template binding '{{{expr}}}' is an expression; LWC allows only "
                                  "a property or getter reference — lift it into a JS getter."})

    # 4. for:each must carry a key.
    for m in re.finditer(r"<template[^>]*for:each=", html):
        segment = html[m.start():m.start() + 400]
        if "key=" not in segment:
            issues.append({"severity": "WARNING", "rule": "lwc_iterator_key",
                           "message": "A for:each iterator should set a unique key= on its child."})
            break

    # 5. Meta config must be valid enough to deploy.
    if "<apiVersion>" not in meta:
        issues.append({"severity": "ERROR", "rule": "lwc_meta_apiversion",
                       "message": ".js-meta.xml must declare <apiVersion>."})
    if "<isExposed>" not in meta:
        issues.append({"severity": "WARNING", "rule": "lwc_meta_isexposed",
                       "message": ".js-meta.xml should declare <isExposed>."})

    return issues
