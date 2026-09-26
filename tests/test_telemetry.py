import json
import time
from pathlib import Path

from cortex.telemetry import JsonlSpanExporter


def _read_trace(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _run_span(spans: list[dict], name: str) -> dict:
    return next(span for span in spans if span["name"] == name)


def test_prepare_writes_trace_file_with_step_spans(cortex, settings, stub_llm):
    job = cortex.prepare.submit(
        payload=b"# Cancellation policy\n\nRefunds within 5 days.",
        filename="policy.md",
        bundle="retail",
    )

    trace_file = settings.traces_path / "prepare" / f"{job.job_id}.jsonl"
    assert trace_file.is_file()
    spans = _read_trace(trace_file)
    names = [span["name"] for span in spans]
    assert set(names) >= {
        "prepare.run",
        "prepare.review",
        "prepare.author",
        "prepare.persist",
    }

    run = _run_span(spans, "prepare.run")
    assert run["status"] != 2  # not ERROR
    assert run["attributes"]["cortex.status"] == "done"
    assert run["attributes"]["source"] == "policy.md"
    assert {span["trace_id"] for span in spans} == {run["trace_id"]}
    assert names.index("prepare.run") > names.index("prepare.review")  # run span wraps its steps


def test_prepare_failed_job_trace_captures_failure_and_logs(cortex, settings, stub_llm):
    stub_llm.author = lambda prompt: "not frontmatter, just broken body"

    job = cortex.prepare.submit(payload=b"one", filename="a.md", bundle="retail")

    assert job.status.value == "failed"
    trace_file = settings.traces_path / "prepare" / f"{job.job_id}.jsonl"
    run = _run_span(_read_trace(trace_file), "prepare.run")
    assert run["status"] == 2  # ERROR
    assert run["attributes"]["cortex.status"] == "failed"
    assert run["attributes"]["cortex.errors"]

    log_file = settings.log_path
    assert log_file.is_file()
    log_lines = log_file.read_text().splitlines()
    assert any(json.loads(line)["level"] == "ERROR" for line in log_lines)


def test_ingest_run_id_and_trace_file(cortex, settings):
    result = cortex.ingest()

    run_id = result["run_id"]
    assert run_id
    trace_file = settings.traces_path / "ingest" / f"{run_id}.jsonl"
    assert trace_file.is_file()
    spans = _read_trace(trace_file)
    run = _run_span(spans, "ingest.run")
    assert [span["name"] for span in spans if span["name"] == "ingest.bundle"]
    assert run["attributes"]["cortex.status"] == "done"

    again = cortex.ingest()
    assert again["run_id"] != run_id


def test_ingest_failure_recorded_in_trace(cortex, settings, bundles_root):
    (bundles_root / "retail" / "tables" / "broken.md").write_text("no frontmatter\n")

    result = cortex.ingest("retail", "tables")
    trace_file = settings.traces_path / "ingest" / f"{result['run_id']}.jsonl"
    lines = _read_trace(trace_file)
    events = [
        event
        for line in lines
        for event in line["events"]
        if event["name"] == "exception"
    ]
    assert any(
        event["attributes"]["concept_path"] == "retail/tables/broken.md"
        for event in events
    )


def test_trace_http_endpoints(client, cortex, settings):
    job = cortex.prepare.submit(payload=b"# X\n\nBody.", filename="x.md", bundle="retail")

    response = client.get(f"/prepare/{job.job_id}/trace")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(part) for part in response.text.splitlines()]
    assert any(line["name"] == "prepare.run" for line in lines)

    missing = client.get("/prepare/does-not-exist/trace")
    assert missing.status_code == 404

    ingest_result = cortex.ingest()
    ingested = client.get(f"/ingest/{ingest_result['run_id']}/trace")
    assert ingested.status_code == 200
    assert any(
        json.loads(part)["name"] == "ingest.run"
        for part in ingested.text.splitlines()
    )

    missing_run = client.get("/ingest/nope/trace")
    assert missing_run.status_code == 404


def test_exporter_prunes_stale_trace_files(tmp_path: Path):
    traces = tmp_path / "traces"
    old = traces / "prepare" / "oldjob.jsonl"
    old.parent.mkdir(parents=True)
    old.write_text("{}\n")
    past = time.time() - 3 * 86400
    import os

    os.utime(old, (past, past))

    exporter = JsonlSpanExporter(traces, retention_days=1)
    exporter.prune()

    assert not old.exists()