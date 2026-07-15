import json
import hashlib
from pathlib import Path

def calculate_md5(file_path: Path) -> str:
    """Calculate MD5 checksum of a file."""
    if not file_path.exists():
        return ""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def get_domain_source_hash(java_files: list[dict]) -> str:
    """Calculate combined hash of all parsed java files in a domain module."""
    hasher = hashlib.md5()
    # Sort by class name to make the hash deterministic
    for cls in sorted(java_files, key=lambda c: c["class_name"]):
        hasher.update(cls.get("source", "").encode("utf-8"))
    return hasher.hexdigest()

def load_ledger(output_dir: str) -> dict:
    """Load the state ledger from the output directory."""
    ledger_path = Path(output_dir) / ".migration_state.json"
    if ledger_path.exists():
        try:
            with open(ledger_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_ledger(output_dir: str, ledger: dict):
    """Save the state ledger to the output directory."""
    ledger_path = Path(output_dir) / ".migration_state.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(ledger_path, "w", encoding="utf-8") as f:
            json.dump(ledger, f, indent=2)
    except Exception as e:
        print(f"  ⚠ Failed to save migration ledger: {e}")
