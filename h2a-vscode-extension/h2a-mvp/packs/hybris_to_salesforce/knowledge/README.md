# Bundled knowledge base (RAG scaffold)

A small, curated set of Salesforce / Apex / fflib reference notes that the
agentic core retrieves from to ground generation and review in real facts
(instead of the model relying on memory). See `src/agentic/retriever.py`.

**This is a scaffold, deliberately.** It uses lightweight lexical (TF‑IDF)
retrieval over these few files — no embeddings, no vector database, no network.
That keeps it dependency-free, deterministic, and fully testable.

**To grow it into production RAG:** drop in the full Salesforce documentation
corpus and swap the lexical index in `retriever.py` for a semantic one
(embeddings + a vector store). The `Retriever` interface — `retrieve(query, k)`
and `grounding_block(query, k)` — stays the same, so nothing downstream changes.

Files here are plain Markdown; each `##` heading becomes a retrievable chunk.
