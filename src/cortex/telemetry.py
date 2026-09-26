import json
import logging
import os
import time
from collections.abc import Mapping
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar

from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter

LOGGER_NAME = "cortex"
logger = logging.getLogger(LOGGER_NAME)


class _JsonFormatter(logging.Formatter):
    _STANDARD: ClassVar[set[str]] = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": record.created,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in self._STANDARD and not key.startswith("_")
        }
        if extra:
            entry["attrs"] = extra
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


class JsonlSpanExporter(SpanExporter):
    """Appends one JSON line per finished span to the trace file of its run.

    A run's file is `{traces_path}/{task}/{run_id}.jsonl`. The mapping from
    OTel trace id to file is bound when the run's parent span starts, so every
    span sharing that trace id — including vendor LLM spans — lands in the same
    file. Unbound spans fall back to `errors/<span_id>.jsonl`.
    """

    def __init__(self, traces_path: Path, retention_days: int) -> None:
        self._traces_path = traces_path
        self._retention_days = retention_days
        self._bound: dict[str, Path] = {}
        self.prune()

    def configure(self, traces_path: Path, retention_days: int) -> None:
        self._traces_path = traces_path
        self._retention_days = retention_days
        self.prune()

    def bind(self, trace_id: int, task: str, run_id: str) -> Path:
        task = task.replace("/", "_")
        run_id = run_id.replace("/", "_")
        path = self._traces_path / task / f"{run_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._bound[str(trace_id)] = path
        return path

    def export(self, spans: list[ReadableSpan]) -> None:
        for span in spans:
            line = _serialize_span(span)
            if line is None:
                continue
            path = self._bound.get(str(span.context.trace_id))
            if path is None:
                fallback = self._traces_path / "errors" / f"{span.context.span_id:x}.jsonl"
                fallback.parent.mkdir(parents=True, exist_ok=True)
                path = fallback
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
        self.prune()

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    def prune(self) -> None:
        if not self._traces_path.is_dir():
            return
        cutoff = time.time() - self._retention_days * 86400
        for trace_file in self._traces_path.rglob("*.jsonl"):
            try:
                if trace_file.stat().st_mtime < cutoff:
                    trace_file.unlink()
            except OSError:
                pass


def _serialize_span(span: ReadableSpan) -> dict | None:
    context = span.context
    if context is None:
        return None
    return {
        "ts": span.start_time,
        "trace_id": f"{context.trace_id:032x}",
        "span_id": f"{context.span_id:016x}",
        "parent_span_id": f"{span.parent.span_id:016x}" if span.parent else None,
        "name": span.name,
        "status": span.status.status_code.value if span.status else 0,
        "duration_ms": round((span.end_time - span.start_time) / 1e6, 3)
        if span.end_time and span.start_time
        else None,
        "attributes": _coerce(span.attributes),
        "events": [
            {
                "name": event.name,
                "ts": event.timestamp,
                "attributes": _coerce(event.attributes),
            }
            for event in span.events
        ],
    }


def _coerce(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _coerce(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_coerce(item) for item in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


_provider: TracerProvider | None = None
_exporter: JsonlSpanExporter | None = None
_instrumented = False


def setup_logging(log_path: Path, level: str = "info") -> None:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level.upper())
    log_path.parent.mkdir(parents=True, exist_ok=True)
    for handler in list(logger.handlers):
        if isinstance(handler, RotatingFileHandler):
            logger.removeHandler(handler)
            handler.close()
    file_handler = RotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=3
    )
    file_handler.setFormatter(_JsonFormatter())
    logger.addHandler(file_handler)
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(console)
    logging.getLogger().addHandler(logging.NullHandler())


def init_tracing(traces_path: Path, retention_days: int) -> tuple[TracerProvider, JsonlSpanExporter]:
    global _provider, _exporter
    if _provider is None:
        _exporter = JsonlSpanExporter(traces_path, retention_days)
        _provider = TracerProvider()
        _provider.add_span_processor(SimpleSpanProcessor(_exporter))
        trace.set_tracer_provider(_provider)
        os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true")
    else:
        assert _exporter is not None
        _exporter.configure(traces_path, retention_days)
    return _provider, _exporter


def tracer() -> trace.Tracer:
    provider = trace.get_tracer_provider()
    return provider.get_tracer("cortex")


def bind_run_trace(trace_id: int, task: str, run_id: str) -> Path:
    assert _exporter is not None, "init_tracing must run before binding a run"
    return _exporter.bind(trace_id, task, run_id)


@contextmanager
def task_run(task: str, run_id: str, **attributes):
    """Wrap a task run in a span and bind its trace file.

    Child spans started inside the context share the run's trace id and land in
    the same `{traces path}/{task}/{run_id}.jsonl` file. Exceptions that escape
    the context are recorded on the span as an `exception` event (status ERROR).
    The span stays open until the context exits, so callers can set status
    attributes mid-run.
    """
    span = tracer().start_span(f"{task}.run", attributes=attributes)
    bind_run_trace(span.context.trace_id, task, run_id)
    with trace.use_span(span, end_on_exit=False):
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
            raise
        finally:
            span.end()


def instrument_ollama() -> None:
    global _instrumented
    if _instrumented:
        return
    from opentelemetry.instrumentation.ollama import OllamaInstrumentor

    OllamaInstrumentor().instrument()
    _instrumented = True


def prune() -> None:
    if _exporter is not None:
        _exporter.prune()