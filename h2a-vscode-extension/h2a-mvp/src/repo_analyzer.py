"""
repo_analyzer.py — Crawler and dependency parser analyzing relations between
independent domains in a legacy monolith repository, returning a topological translation schedule.
"""

import os
import re
from pathlib import Path
from src.domain_classifier import classify_domains


def _strip_comments_and_strings(content: str) -> str:
    """Remove comments and string literals so identifier matching avoids false positives."""
    content = re.sub(r"/\*.*?\*/", " ", content, flags=re.DOTALL)   # block comments
    content = re.sub(r"//.*", " ", content)                          # line comments
    content = re.sub(r'"(?:\\.|[^"\\])*"', '""', content)            # string literals
    return content


def build_dependency_graph(input_dir: str) -> tuple[dict[str, list[str]], dict]:
    """
    Crawl the legacy source files, isolate domains, and compute inter-domain
    dependencies via whole-word identifier references (comments/strings stripped),
    so `Order` no longer spuriously matches inside `OrderEntry` or a comment.
    """
    domains = classify_domains(input_dir)

    class_to_domain = {}
    for domain, classes in domains.items():
        for cls in classes:
            class_to_domain[cls["class_name"]] = domain

    # Pre-compile a word-boundary matcher per class name.
    class_patterns = {
        name: re.compile(rf"\b{re.escape(name)}\b")
        for name in class_to_domain
    }

    graph = {domain: set() for domain in domains}
    for domain, classes in domains.items():
        for cls in classes:
            path = Path(cls["absolute_path"])
            if not path.exists():
                continue
            content = _strip_comments_and_strings(path.read_text(encoding="utf-8"))
            for target_cls, target_domain in class_to_domain.items():
                if target_domain == domain:
                    continue
                if class_patterns[target_cls].search(content):
                    graph[domain].add(target_domain)

    adjacency_list = {k: sorted(list(v)) for k, v in graph.items()}
    return adjacency_list, domains


def get_translation_schedule(input_dir: str) -> list[str]:
    """
    Computes a topological sort of domain execution order.
    """
    graph, _ = build_dependency_graph(input_dir)
    
    visited = {}
    order = []

    def visit(node):
        if visited.get(node) == "visiting":
            # Break soft loops to prevent crashes in legacy codebases by skipping back-edges
            return
        if not visited.get(node):
            visited[node] = "visiting"
            for dep in graph.get(node, []):
                visit(dep)
            visited[node] = "visited"
            order.append(node)

    for node in sorted(graph.keys()):
        if not visited.get(node):
            visit(node)

    return order


def extract_method_call_graph(input_dir: str, output_dir: str):
    """
    Scans legacy Java codebase, parses method relationships, and writes .call_graph.json.
    """
    import re
    import json
    
    java_files = []
    for root, _, files in os.walk(input_dir):
        for file in files:
            if file.endswith(".java"):
                java_files.append(Path(root) / file)

    # 1. Map classes and their methods
    class_methods = {}
    class_to_file = {}
    class_fields = {}

    class_decl_pattern = re.compile(r"\b(?:class|interface)\s+(\w+)\b")
    method_decl_pattern = re.compile(r"\bpublic\s+(?:[a-zA-Z0-9_<>]+\s+)?([a-zA-Z0-9_]+)\s*\(([^)]*)\)")
    field_pattern = re.compile(r"\b(?:private|protected|public)?\s+(\w+)\s+(\w+)\s*;")

    for fpath in java_files:
        try:
            content = fpath.read_text(encoding="utf-8")
        except Exception:
            continue

        class_match = class_decl_pattern.search(content)
        if not class_match:
            continue
        class_name = class_match.group(1)
        class_to_file[class_name] = str(fpath)
        class_methods[class_name] = []
        class_fields[class_name] = {}

        for match in field_pattern.finditer(content):
            type_name, var_name = match.groups()
            class_fields[class_name][var_name] = type_name

        for match in method_decl_pattern.finditer(content):
            method_name = match.group(1)
            if method_name not in ("if", "for", "while", "switch", "return", "catch", "synchronized"):
                class_methods[class_name].append(method_name)

    # 2. Trace calls inside methods
    nodes = []
    links = []
    node_ids = set()

    for class_name, methods in class_methods.items():
        fpath = class_to_file[class_name]
        try:
            content = Path(fpath).read_text(encoding="utf-8")
        except Exception:
            continue

        layer = "Utility"
        if "Controller" in class_name:
            layer = "Controller"
        elif "Facade" in class_name:
            layer = "Facade"
        elif "Service" in class_name:
            layer = "Service"
        elif "Dao" in class_name or "DAO" in class_name:
            layer = "DAO"
        elif "Model" in class_name or "DTO" in class_name:
            layer = "Model"

        for method in methods:
            source_id = f"{class_name}.{method}"
            if source_id not in node_ids:
                nodes.append({"id": source_id, "class": class_name, "layer": layer})
                node_ids.add(source_id)

            method_start_idx = content.find(f" {method}(")
            if method_start_idx == -1:
                method_start_idx = content.find(f"\t{method}(")
            if method_start_idx == -1:
                continue
                
            method_body = content[method_start_idx:method_start_idx + 2500]
            
            for call_match in re.finditer(r"\b(\w+)\.(\w+)\s*\(", method_body):
                var_or_cls, called_method = call_match.groups()
                target_class = class_fields[class_name].get(var_or_cls, var_or_cls)
                
                if target_class in class_methods and called_method in class_methods[target_class]:
                    target_id = f"{target_class}.{called_method}"
                    link = {"source": source_id, "target": target_id}
                    if link not in links:
                        links.append(link)

    # Fallback to layer connections
    if not links:
        controllers = [c for c in class_methods if "Controller" in c]
        services = [s for s in class_methods if "Service" in s]
        daos = [d for d in class_methods if "Dao" in d or "DAO" in d]
        
        for c in controllers:
            for s in services:
                c_content = Path(class_to_file[c]).read_text(encoding="utf-8")
                if s in c_content:
                    c_methods = class_methods[c]
                    s_methods = class_methods[s]
                    if c_methods and s_methods:
                        links.append({"source": f"{c}.{c_methods[0]}", "target": f"{s}.{s_methods[0]}"})

        for s in services:
            for d in daos:
                s_content = Path(class_to_file[s]).read_text(encoding="utf-8")
                if d in s_content:
                    s_methods = class_methods[s]
                    d_methods = class_methods[d]
                    if s_methods and d_methods:
                        links.append({"source": f"{s}.{s_methods[0]}", "target": f"{d}.{d_methods[0]}"})

    for link in links:
        for nid in (link["source"], link["target"]):
            if nid not in node_ids:
                cls_part = nid.split(".")[0]
                layer = "Utility"
                if "Controller" in cls_part: layer = "Controller"
                elif "Facade" in cls_part: layer = "Facade"
                elif "Service" in cls_part: layer = "Service"
                elif "Dao" in cls_part or "DAO" in cls_part: layer = "DAO"
                
                nodes.append({"id": nid, "class": cls_part, "layer": layer})
                node_ids.add(nid)

    graph_path = Path(output_dir) / ".call_graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump({"nodes": nodes, "links": links}, f, indent=2)
