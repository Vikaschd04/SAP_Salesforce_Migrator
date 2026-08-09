"""Things a real SAP Commerce estate contains that a demo never does.

Every case here was a genuine failure found by probing the engine with the shapes real
customer code takes. Four of them aborted the entire migration; the rest lost a file
without telling anyone, which is worse — a run that stops is annoying, a run that
quietly forgets a class produces a confident, wrong report.

The rule these encode: **one bad file costs you that file, never the run, and never in
silence.**
"""

import pathlib
import tempfile

import pytest

from src.ingest import ingest
from src.generate import plan_targets
from src.textio import read_source, is_binary

EXT = '<extensioninfo><extension name="acmecore"/></extensioninfo>'
ITEMS = "<items><itemtypes/></items>"


def build(files: dict) -> str:
    """Write a throwaway extension and return its path."""
    d = pathlib.Path(tempfile.mkdtemp())
    base = {"extensioninfo.xml": EXT, "resources/acmecore-items.xml": ITEMS}
    for rel, content in {**base, **files}.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content) if isinstance(content, bytes) else p.write_text(content, encoding="utf-8")
    return str(d)


# ── encodings: the most likely real-world failure of all ──────────────────────

def test_latin1_source_does_not_abort_the_run():
    """Hybris's own extensioninfo.xml is declared ISO-8859-1, and any estate with German,
    French or Nordic developers has Java full of umlauts. One such file used to raise
    UnicodeDecodeError before a single class was read."""
    # Byte literals, not str.encode(): the euro sign has no latin-1 encoding at all, so
    # encoding here would fail in the test rather than exercising the reader.
    src = "// Preisprüfung für Bestellungen über 5000 Euro\npublic class Preisrechner { void go(){} }"
    r = ingest(build({"src/Preisrechner.java": src.encode("iso-8859-1")}))
    assert [c["class_name"] for c in r["classes"]] == ["Preisrechner"]
    assert "Preisprüfung" in r["classes"][0]["source"], "the accented text was mangled"


def test_utf8_with_a_bom_is_read_cleanly():
    """Windows editors add one, and it lands invisibly on the first token."""
    r = ingest(build({"src/B.java": b"\xef\xbb\xbfpublic class B { void go(){} }"}))
    assert [c["class_name"] for c in r["classes"]] == ["B"]
    assert not r["classes"][0]["source"].startswith("﻿")


def test_cp1252_smart_quotes_survive():
    # 0x93/0x94 are cp1252's curly quotes — raw bytes, not encodable characters.
    r = ingest(build({"src/Q.java": b'public class Q { String s = "\x93hello\x94"; }'}))
    assert len(r["classes"]) == 1


def test_a_binary_file_named_java_is_reported_not_raised():
    """Build artefacts, Git LFS pointers and accidental commits all arrive as .java."""
    r = ingest(build({"src/Bad.java": bytes(range(256))}))
    assert r["classes"] == []
    assert len(r["unreadable"]) == 1
    assert "not a text file" in r["unreadable"][0]["unreadable"]


def test_is_binary_does_not_flag_ordinary_source():
    assert is_binary(b"\x00\x01\x02") is True
    assert is_binary("public class A {}".encode()) is False


def test_read_source_reports_which_encoding_it_used():
    d = pathlib.Path(tempfile.mkdtemp()) / "x.java"
    d.write_bytes("class A { String s = \"ü\"; }".encode("iso-8859-1"))
    text, enc = read_source(d)
    assert "ü" in text and enc in ("cp1252", "iso-8859-1")


# ── unparseable, but never invisible ──────────────────────────────────────────

def test_modern_java_is_recorded_rather_than_vanishing():
    """javalang predates records, sealed types and switch expressions. Returning None
    made the class disappear before all_classes, so the completeness ledger could not
    report it either — the guarantee was quietly false."""
    r = ingest(build({"src/Money.java": "public record Money(int amount) {}"}))
    assert r["classes"] == []
    assert len(r["unreadable"]) == 1
    assert "Money" == r["unreadable"][0]["class_name"]
    assert "could not parse" in r["unreadable"][0]["unreadable"]


def test_an_unreadable_file_reaches_the_completeness_ledger():
    from src.agentic.blackboard import Blackboard
    bb = Blackboard("in", "out")
    bb.unreadable = [{"class_name": "Money", "unreadable": "could not parse Java: X",
                      "file": "Money.java"}]
    rows = bb.completeness_ledger()
    assert any(r["outcome"] == "unreadable" and r["source"] == "Money" for r in rows)
    assert "by hand" in next(r for r in rows if r["source"] == "Money")["note"]


def test_empty_and_whitespace_only_sources_are_harmless():
    r = ingest(build({"src/Empty.java": "", "src/Blank.java": "   \n\n  \n"}))
    assert isinstance(r["classes"], list)


# ── malformed configuration ───────────────────────────────────────────────────

def test_a_malformed_items_xml_costs_its_types_not_the_run():
    """A hand-edited type system with an unclosed tag is common in a long-lived estate."""
    r = ingest(build({"resources/acmecore-items.xml": "<items><itemtypes><itemtype code='X'>",
                      "src/A.java": "public class A { void go(){} }"}))
    assert [c["class_name"] for c in r["classes"]] == ["A"]
    assert r["item_types"] == []


# ── name collisions, which Apex cannot express ────────────────────────────────

def _sources(targets):
    return [c.get("file") for t in targets for c in t["source_classes"]]


def test_two_extensions_sharing_a_class_name_keep_both_sources():
    """acmecore and acmeb2b both shipping DefaultOrderService is routine. Apex has no
    namespaces so they must land in one artifact — but deduping by name alone dropped
    one of them, taking its logic with it."""
    targets = plan_targets([
        {"class_name": "DefaultOrderService", "layer": "Service", "file": "acmecore/DefaultOrderService.java"},
        {"class_name": "DefaultOrderService", "layer": "Service", "file": "acmeb2b/DefaultOrderService.java"},
    ])
    assert len(targets) == 1
    assert sorted(_sources(targets)) == ["acmeb2b/DefaultOrderService.java",
                                         "acmecore/DefaultOrderService.java"]


def test_the_same_class_listed_twice_is_not_duplicated():
    """Idempotence: a class reaching plan_targets twice must not be sent to the model twice."""
    cls = {"class_name": "DefaultOrderService", "layer": "Service", "file": "a/DefaultOrderService.java"}
    targets = plan_targets([cls, dict(cls)])
    assert len(_sources(targets)) == 1


# ── shapes that are valid but unusual ─────────────────────────────────────────

def test_crlf_line_endings():
    r = ingest(build({"src/W.java": "public class W {\r\n  public void go(){}\r\n}\r\n"}))
    assert [c["class_name"] for c in r["classes"]] == ["W"]


def test_interfaces_and_abstract_classes_are_ingested():
    r = ingest(build({
        "src/IThing.java": "public interface IThing { void go(); }",
        "src/AbstractThing.java": "public abstract class AbstractThing { protected abstract void go(); }"}))
    assert {c["class_name"] for c in r["classes"]} == {"IThing", "AbstractThing"}


def test_deep_nesting_and_long_names():
    name = "Default" + "Very" * 15 + "Service"
    path = "src/" + "/".join(["a"] * 12) + f"/{name}.java"
    r = ingest(build({path: f"public class {name} {{ void go(){{}} }}"}))
    assert [c["class_name"] for c in r["classes"]] == [name]


def test_an_extension_with_no_java_at_all():
    """A sampledata extension is ImpEx and XML only — valid, and must not crash."""
    r = ingest(build({"resources/impex/projectdata.impex": "INSERT_UPDATE Product;code\n;X"}))
    assert r["classes"] == [] and r["unreadable"] == []
