"""
signature_registry.py — Registry storing and propagating method declarations
across decoupled domain translation executions.
"""


class SignatureRegistry:
    def __init__(self):
        self.signatures = {}  # domain_name -> { class_name -> list[sigs] }

    def register(self, domain: str, class_name: str, sigs: list[str]):
        """Register public signatures for a compiled class in a domain."""
        if domain not in self.signatures:
            self.signatures[domain] = {}
        self.signatures[domain][class_name] = sigs

    def get_all_signatures(self) -> dict[str, list[str]]:
        """Flatten registry into a format readable by generation modules."""
        flat = {}
        for domain_name, classes in self.signatures.items():
            for class_name, sigs in classes.items():
                flat[class_name] = sigs
        return flat

    def get_signatures_for_domains(self, domains) -> list[str]:
        """Return a flat list of signatures owned by the given domains only (scoped context)."""
        wanted = set(domains)
        out: list[str] = []
        for domain_name, classes in self.signatures.items():
            if domain_name not in wanted:
                continue
            for sigs in classes.values():
                out.extend(sigs)
        return out
