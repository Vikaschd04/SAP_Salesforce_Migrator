"""
domain_classifier.py — Dependency and structural modularity classifier.
Clustered legacy code files by domain boundaries to build step-by-step conversion schedules.
"""

import os
from pathlib import Path


def classify_domains(input_dir: str) -> dict:
    """
    Scan the target directory, read class names, and group files into independent domain blocks.
    """
    if not os.path.exists(input_dir):
        raise FileNotFoundError(f"Source directory not found at: {input_dir}")

    java_files = []
    for root, _, files in os.walk(input_dir):
        for file in files:
            if file.endswith(".java"):
                java_files.append(Path(root) / file)

    domains = {}
    for path in java_files:
        class_name = path.stem
        domain = _get_domain_prefix(class_name)
        
        if domain not in domains:
            domains[domain] = []
            
        domains[domain].append({
            "class_name": class_name,
            "file_name": path.name,
            "absolute_path": str(path.resolve())
        })

    return domains


def _get_domain_prefix(class_name: str) -> str:
    """Extract base domain prefix from legacy class names."""
    name = class_name
    if name.startswith("Default"):
        name = name[7:]
    for suffix in ["Dao", "DAO", "Service", "Facade", "Controller", "Data", "Job"]:
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return name
