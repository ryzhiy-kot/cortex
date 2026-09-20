# 0003: Usage documentation lives in the OpenAPI contract

**Status**: accepted

Cortex documents how to use its API in the OpenAPI specification generated from the FastAPI code — summaries, tags, per-endpoint docstrings describing semantics and error conditions, `openapi_examples` on request bodies, and field-level `examples` on models — and not in the README.

**Context**: The API is the stable integration surface for external agentic systems (ADR 0002), so the machine- and human-readable contract itself is the documentation that travels with every deployment (`/docs`, `openapi.json`). The initial plan was to write an ingest walkthrough in the README duplicating the example payloads already carried in the OpenAPI; during the design interview we decided that the drift risk of maintaining the same payloads in two places outweighed the value of a prose walkthrough, and that agents consume the OpenAPI, not the README.

**Why**: The code is the single source of truth for usage examples — exact, runnable against `examples/bundles`, and regenerated on every change. A README copy would stale-drift and add no information the contract does not already carry. The README stays high-level (what Cortex is, quick start, config), and all usage-level documentation lives in the contract.

**Considered options**:
- **README walkthrough + OpenAPI examples** (rejected): duplicate payloads in Markdown and Pydantic drift apart as bundles evolve; agents don't read the README.
- **OpenAPI only** (chosen): one source of truth that ships with every deployment and is self-served by `/docs`.

**Consequences**:
- The README does not demonstrate ingest/search/read calls in prose.
- Examples in `routes.py`/`models.py` must stay runnable against the shipped example bundles — treat them as testable documentation.
- Agents and humans alike should use `/docs` or `openapi.json` as the usage reference.