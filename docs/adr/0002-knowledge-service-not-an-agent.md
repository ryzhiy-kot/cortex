# 0002: Knowledge service, not an agent

**Status**: accepted (amended by ADR 0004)

Cortex is a knowledge service. Its **serving path** — search, read, list, validate — contains no LLM and no agent orchestration; it exposes a deterministic REST API over an OKF bundle, and the existing agentic system (a separate project, the pydantic-ai consumer) drives all LLM interaction for *querying* by calling that API over HTTP.

**Amended**: the **authoring path** (*Prepare*, see ADR 0004) is the exception — it uses an LLM as an authoring utility to convert source material into OKF. The amendment is scoped: no LLM in search/read/ingest; LLM only inside Prepare.

**Context**: The repo was scaffolded with `pydantic-ai` as a dependency, and the original pitch was "an LLM powered knowledge system." During the design interview (Q1, Q18) we decided the opposite seam: a knowledge service prefers to stay free of agent-framework dependencies so it can be tested deterministically, stay provider-agnostic on the LLM side, and be consumed by any number of agentic systems.

**Why**: Separating knowledge access from agent orchestration keeps the serving layer a library-grade dependency surface (FastAPI + storage + vector index) rather than a coupling point to a specific model provider or orchestration style. It also makes the API contract — the endpoints — the stable artifact the agentic team builds against. `pydantic-ai` is not a dependency of this package; it belongs to the sibling agentic system.

**Considered options**:
- **Agent hosted inside Cortex** (pydantic-ai in this repo): rejected — couples knowledge serving to an orchestration framework and model providers, duplicates the existing agentic system's job, complicates deterministic testing.
- **Knowledge service only** (chosen): lean, deterministic, provider-agnostic, single stable API contract for serving; an LLM-as-utility authoring step (Prepare) is the sole carve-out.

**Consequences**:
- Searching, reading, and ingesting never invoke an LLM; only Prepare does.
- The API contract (endpoints and response schemas) is the integration surface and must stay stable.
- `POST /ingest` and `POST /prepare` are invoked explicitly by the owner of the bundle, not scheduled by Cortex.