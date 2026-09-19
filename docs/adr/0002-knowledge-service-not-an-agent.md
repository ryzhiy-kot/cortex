# 0002: Knowledge service, not an agent

**Status**: accepted

Cortex is a knowledge service. It contains no LLM agent and does not orchestrate tool-calling loops; it exposes a deterministic REST API — search, read, list, ingest — over an OKF bundle, and the existing agentic system (a separate project, the pydantic-ai consumer) drives all LLM interaction by calling that API over HTTP.

**Context**: The repo was scaffolded with `pydantic-ai` as a dependency, and the original pitch was "an LLM powered knowledge system." During the design interview (Q1, Q18) we decided the opposite seam: a knowledge service prefers to stay free of agent-framework dependencies so it can be tested deterministically, stay provider-agnostic on the LLM side, and be consumed by any number of agentic systems.

**Why**: Separating knowledge access from agent orchestration keeps the knowledge layer a library-grade dependency surface (FastAPI + storage + vector index) rather than a coupling point to a specific model provider or orchestration style. It also makes the API contract — four endpoints — the stable artifact the agentic team builds against. `pydantic-ai` is not a dependency of this package; it belongs to the sibling agentic system.

**Considered options**:
- **Agent hosted inside Cortex** (pydantic-ai in this repo): rejected — couples knowledge serving to an orchestration framework and model providers, duplicates the existing agentic system's job, complicates deterministic testing.
- **Knowledge service only** (chosen): lean, deterministic, provider-agnostic, single stable API contract.

**Consequences**:
- No LLM layer in Cortex: no chat endpoint, no tool-calling loop, no memory. Those live in the sibling system.
- The API contract (endpoints and response schemas) is the integration surface and must stay stable.
- `POST /ingest` is invoked explicitly by the owner of the bundle, not scheduled by Cortex.