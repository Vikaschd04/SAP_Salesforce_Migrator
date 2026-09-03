"""
hybris_source.py — SAP Hybris as a *source*.

Thin by design: every function here calls the same module the v1 path calls. The value is
not new behaviour, it is that the behaviour now has a named seam a second platform can be
plugged into beside it.
"""

from __future__ import annotations

from src import ir


class HybrisSource:
    platform = "hybris"
    label = "SAP Hybris (Java / Spring)"

    def detect(self, root: str) -> dict:
        from src.preflight import inspect
        return inspect(root)

    def read(self, root: str) -> ir.SourceModel:
        """The whole source as an IR model.

        Built from `ingest()` rather than beside it — a second parser would be a second
        thing to keep correct, and the two would drift.
        """
        from src.ingest import ingest
        model = ir.SourceModel.from_ingest(ingest(root), platform=self.platform, root=root)
        model.processes = self._processes(root, {u.name for u in model.units})
        model.hazards = self._hazards(root)
        return model

    def _processes(self, root: str, unit_names: set) -> list:
        from src.processes import discover
        out = []
        for p in discover(root, unit_names):
            out.append(ir.ProcessDef(
                name=p.get("name", ""), file=p.get("file", ""),
                start=p.get("start", ""), on_error=p.get("on_error", ""),
                end_states=list(p.get("end_states") or []),
                unreadable=p.get("unreadable", ""),
                steps=[ir.ProcessStep(id=a.get("id", ""), ref=a.get("bean", ""),
                                      implemented_by=a.get("implemented_by", ""),
                                      transitions=list(a.get("transitions") or []),
                                      kind="action")
                       for a in (p.get("actions") or [])]
                      + [ir.ProcessStep(id=w.get("id", ""), kind=w.get("kind", "wait"),
                                        transitions=[{"name": "", "to": t}
                                                     for t in (w.get("transitions_to") or [])])
                         for w in (p.get("flow") or [])],
            ))
        return out

    def _hazards(self, root: str) -> list:
        from src.radar import scan
        return [ir.Hazard(id=f.get("id", ""), rule=f.get("rule", ""),
                          severity=f.get("severity", ""), file=f.get("file", ""),
                          line=int(f.get("line") or 0),
                          source_unit=f.get("source_class", ""),
                          detail=f.get("detail", ""), fix=f.get("fix", ""))
                for f in (scan(root).get("findings") or [])]

    def symbols(self, text: str) -> list:
        """Java method declarations, for provenance. [2.11]"""
        from src.adapters.braced_symbols import symbols as _s
        return _s(text)

    def mine_behaviours(self, test_classes: list) -> list:
        """Recorded input→output facts from the customer's JUnit suite.

        A source adapter owns this because reading a test suite is a source skill:
        PHPUnit records the same kind of fact in an entirely different shape.
        """
        from src.adapters import java_junit_mining as jm
        return jm.mine(test_classes)

ADAPTER = HybrisSource()
