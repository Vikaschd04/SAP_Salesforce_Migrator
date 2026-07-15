"""
retriever.py — RAG scaffold: lexical retrieval over a small bundled doc set.

Before an agent generates or reviews Apex, it can pull the most relevant facts
from the bundled Salesforce/Apex/fflib notes (src/agentic/knowledge/) and inject
them into the prompt — so the model cites real governor limits and patterns
instead of relying on memory.

Deliberately a **scaffold**: it uses dependency-free TF-IDF cosine similarity
(no embeddings, no vector DB, no network), which is deterministic and fully
testable. The `Retriever` interface (`retrieve` / `grounding_block`) is the seam:
to go to production RAG, point it at the full Salesforce corpus and swap the
lexical index for a semantic one — nothing downstream changes.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Very common words carry no retrieval signal.
_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
         "is", "are", "be", "by", "as", "at", "it", "this", "that", "from",
         "use", "used", "using", "not", "no", "do", "does", "per", "one", "all"}


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1 and t not in _STOP]


@dataclass
class Chunk:
    doc: str          # source file name
    heading: str      # the ## heading this chunk sits under
    text: str         # the chunk body
    tf: dict          # term -> count (internal)


class Retriever:
    """Lexical (TF-IDF) retriever over a directory of Markdown notes."""

    def __init__(self, docs_dir: str | Path | None = None, top_k: int = 3):
        self.docs_dir = Path(docs_dir) if docs_dir else Path(__file__).resolve().parent / "knowledge"
        self.top_k = top_k
        self.chunks: list[Chunk] = []
        self._idf: dict[str, float] = {}
        self._norms: list[float] = []
        self._build()

    # ── index ──
    def _build(self) -> None:
        for md in sorted(self.docs_dir.glob("*.md")):
            if md.name.lower() == "readme.md":
                continue
            self._chunk_file(md)
        if not self.chunks:
            return
        n = len(self.chunks)
        df: dict[str, int] = {}
        for c in self.chunks:
            for term in c.tf:
                df[term] = df.get(term, 0) + 1
        self._idf = {t: math.log((n + 1) / (d + 1)) + 1 for t, d in df.items()}
        for c in self.chunks:
            self._norms.append(math.sqrt(sum(
                (freq * self._idf.get(t, 0.0)) ** 2 for t, freq in c.tf.items())) or 1.0)

    def _chunk_file(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        heading = path.stem
        buf: list[str] = []

        def flush():
            body = "\n".join(buf).strip()
            if body:
                toks = _tokens(heading + " " + body)
                tf: dict[str, int] = {}
                for t in toks:
                    tf[t] = tf.get(t, 0) + 1
                self.chunks.append(Chunk(doc=path.name, heading=heading, text=body, tf=tf))

        for line in text.splitlines():
            if line.startswith("## "):
                flush()
                buf = []
                heading = line[3:].strip()
            elif line.startswith("# "):
                heading = line[2:].strip()
            else:
                buf.append(line)
        flush()

    @property
    def n_chunks(self) -> int:
        return len(self.chunks)

    @property
    def available(self) -> bool:
        return bool(self.chunks)

    # ── query ──
    def retrieve(self, query: str, k: int | None = None) -> list[Chunk]:
        if not self.chunks:
            return []
        k = k or self.top_k
        q_tf: dict[str, int] = {}
        for t in _tokens(query):
            q_tf[t] = q_tf.get(t, 0) + 1
        q_vec = {t: freq * self._idf.get(t, 0.0) for t, freq in q_tf.items()}
        q_norm = math.sqrt(sum(w * w for w in q_vec.values())) or 1.0

        scored = []
        for i, c in enumerate(self.chunks):
            dot = sum(w * c.tf.get(t, 0) * self._idf.get(t, 0.0) for t, w in q_vec.items())
            if dot > 0:
                scored.append((dot / (q_norm * self._norms[i]), c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:k]]

    def grounding_block(self, query: str, k: int | None = None,
                        label: str = "Salesforce reference (retrieved — use these facts, don't invent APIs)") -> str:
        hits = self.retrieve(query, k)
        if not hits:
            return ""
        parts = [f"== {label} =="]
        for c in hits:
            parts.append(f"[{c.doc} · {c.heading}]\n{c.text.strip()}")
        return "\n\n".join(parts)


def build_retriever(config: dict) -> Retriever | None:
    """Return a Retriever if `agentic.rag.enabled`, else None (RAG off)."""
    rag = (config.get("agentic") or {}).get("rag") or {}
    if not rag.get("enabled", False):
        return None
    r = Retriever(top_k=rag.get("top_k", 3))
    return r if r.available else None
