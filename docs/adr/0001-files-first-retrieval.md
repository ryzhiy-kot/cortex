# 0001: Files-first retrieval

**Status**: accepted

The Chroma index stores one embedding per OKF concept (title + description + body) and search returns **concept pointers** (path + metadata + snippet), never answer content. The agent or consumer reads the full concept from the bundle via `GET /concepts/{path}`. Answers are always grounded in the current source markdown, never in index snapshots.

**Context**: Traditional RAG chunks documents and returns chunks as the answer surface. We deliberately chose the opposite: the vector index answers "*where* should I look?", never "what is the answer?". This matches OKF's own consumption philosophy (progressive disclosure via `index.md`, agents read concept files) and keeps the index small, cheap to refresh, and immune to drift from the bundle.

**Why**: The Q5 research survey (A-RAG, AgenticRAG, READ, okf-agents) converged on one pattern — the interface matters more than the iteration. READ measured 58.8% vs 15.7% for chunk-based dense retrieval on structured documents. An OKF concept file is already a coherent unit of curated insight; chunking tears apart the headings/tables that make it readable. Files-first also makes `POST /ingest` near-free (one vector per concept) and answers auditable (cited concept paths in real files).

**Considered options**:
- **Vector-first RAG** (chunk → embed → answer from chunks): rejected — context fragmentation, index/bundle drift, coarse but large index to keep fresh, invisible retrieval failures.
- **Files-only, no vector store** (pure grep + `index.md` walk): viable at small scale, but loses semantic lookup for terms that don't appear lexically. Chroma adds the semantic pre-filter over the lexical walk.

**Consequences**:
- Search is a "go look here" signal, not an answer provider. Any consumer wanting an answer does a second read.
- Whole-document granularity is coarse for very large concepts (>1 doc that is genuinely huge). Heading-aware chunking of oversized concepts is a deferred, non-breaking enhancement.
- The read path (`GET /concepts/{path}`) is load-bearing: it must always return the live bundle content, never a cached copy.