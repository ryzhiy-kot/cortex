# 0004: Prepare — LLM-assisted authoring of OKF bundles

**Status**: accepted

Cortex gains a `Prepare` capability: source material (a single file or a zip archive, uploaded by the caller) is converted into OKF concepts under the bundles root. An LLM reviews the source against the existing bundles and decides per source file whether to front new knowledge, consolidate into an existing concept by rewriting it in place, or create a new bundle. `POST /prepare` returns a job id; the caller polls `GET /prepare/{job}`. `Prepare` never indexes — the already-existing `POST /ingest` remains the only path into Chroma.

**Context**: Cortex's serving path is deliberately LLM-free (ADR 0002). But the owner of a knowledge base needs a way to turn raw, non-OKF material (a folder of docs, a spec file) into a conformant bundle without hand-authoring YAML frontmatter. Doing that transform mechanically produced low-quality OKF — no merged dedup, no review against what already exists — and the design interview settled on an LLM review step as the authoring utility. The LLM is a utility here, not an executive agent: used in a bounded, deterministic pipeline (review → decide → author), not a tool-calling loop.

**Why**:
- *Deduplication by construction*: Prepare never blindly appends. Each source file is compared against existing concepts before anything is written; if the knowledge already exists, the new information is consolidated in place rather than duplicated.
- *OKF conformance*: the model is handed the OKF SPEC and must author parseable frontmatter; Cortex re-parses every written concept and fails the whole job on the first invalid one (atomic).
- *Separation of concerns*: Prepare writes OKF only — no embedding, no `index.md`. Integests after Prepare stays explicit and re-runnable.

**Key decisions**:
- **Async job model**: `POST /prepare` returns `202 {job_id}`; poll `GET /prepare/{job}`. Jobs run serially (FIFO) and live in memory — a restart orphans them.
- **Source upload**: one file or one zip per request, staged under `.cortex/staging/{job_id}`.
- **Target selection**: optional `bundle` field forces a target (created if missing); absent, the LLM derives a bundle name. Append-to-existing vs create-new is decided by the review.
- **Consolidation semantics**: in-place rewrite of the existing concept, preserving its path, appending to `sources`.
- **Provenance**: every prepared concept carries a `sources` frontmatter field — a hard requirement, set at creation and extended on consolidation.
- **Atomicity**: a single invalid or unparseable concept output fails the entire job; nothing is written.
- **Non-text files** in a source folder are reported as skipped, never fatal.

**Considered options**:
- **Mechanical conversion without LLM** (rejected): no dedup review, arbitrary `type` stamping, no merge judgement; low-quality OKF.
- **Full agent/orchestrator inside Cortex** (rejected): violates ADR 0002's serving-path determinism and duplicates the sibling agentic system.
- **Authoring delegated to the sibling agentic system** (rejected): splits Prepare and Ingest ownership across two services, complicates provenance, and the design interview chose self-contained Prepare.

**Consequences**:
- `POST /prepare` serializes through one worker; parallel workers are a future optimization, not a correctness problem.
- The LLM is a new provider surface (`CORTEX_LLM_PROVIDER`), config-switchable like embeddings; tests use an injected stub model.
- A later `POST /review` endpoint can reuse Prepare's provenance + concept scan to find cross-bundle redundancy, but is out of scope here.
- ADR 0002 is amended: "no LLM" now applies to the serving path only.