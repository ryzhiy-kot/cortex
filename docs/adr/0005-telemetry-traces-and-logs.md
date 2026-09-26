# 0005: Telemetry — OTel event model exported to local trace files, cloud later

**Status**: accepted

Prepare and ingest fail silently today: the error string lands on the job object, nowhere else. There is no logging, no way to see what the LLM saw, and a failed run's evidence dies with the process. We decided to add observability in two channels: **native Python `logging`** for general system errors/exceptions and lifecycle (JSON-lines file + console), and a **Trace** per task run — the ordered record of its steps, LLM interactions, and failures — which doubles as the durable diagnostic artifact.

The event model is **OpenTelemetry**: a task run is a span tree (run → review/author/persist → vendor LLM spans), and the trace file is produced by an exporter that appends one JSON line per finished span into `traces/<task>/<run_id>.jsonl`. Full LLM interaction content (prompts, responses, token usage) is captured by the vendors' own GenAI instrumentors (`opentelemetry-instrumentation-ollama` via the official `ollama` SDK) — we don't hand-roll provider telemetry. When Google Cloud Trace is stood up later, migrating is an exporter swap, not a rewrite.

**Considered options**:
- **Hand-rolled provider telemetry** inside `complete()`: rejected — user directive, duplicates what vendor instrumentors emit, and would produce a parallel event model instead of the portable GenAI one.
- **`opentelemetry-instrumentation-httpx`** to cover Ollama's raw calls: rejected — URL/status spans, no prompt, no model, no token usage.
- **Export to Cloud Trace / OTLP now**: rejected for now — no collector or backend exists; local file export gives the diagnosis ability today with identical span data.
- **Instrument Vertex now** (`opentelemetry-instrumentation-vertexai`): deferred — the module is deprecated and only matters when the `embeddings` extra and a Vertex endpoint are actually in use; wire it when Vertex traffic exists.
- **Trace data on the job object only**: rejected — dies on restart, which is when diagnosis happens.

**Consequences**:
- Standard GenAI spans (`gen_ai.*`) and events (`gen_ai.user.message`, `gen_ai.choice`, `exception`) are the single event model; file traces now, OTel/Cloud backends later via a new exporter.
- `ollama` (official SDK) and `opentelemetry-instrumentation-ollama` become runtime dependencies; Ollama embeddings migrate to the SDK too.
- Traces never live under staging (staging is wiped after a run); they live in `CORTEX_TRACES_PATH` (default `.cortex/traces`), pruned by file mtime after `CORTEX_TRACE_RETENTION_DAYS` (default 7) at startup and after runs.
- Every prepare job and every ingest run produces one `.jsonl` file; ingest surfaces its `run_id` in the response so the trace is addressable. Both are readable as NDJSON via read-only endpoints `GET /prepare/{job_id}/trace` and `GET /ingest/{run_id}/trace`.
- General logs: `cortex.*` logger → JSON-lines rotating file plus console; status transitions at `debug`, failures with full traceback at `error`; an HTTP middleware records unhandled 500s as an error log + exception span.
- LLM interaction content lands in trace files; those files are the sensitive surface and are operator-owned via the traces path.