import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from opentelemetry import trace

from cortex.models import PrepareJob, PrepareStatus
from cortex.prepare.pipeline import PrepareRunner
from cortex.telemetry import logger, task_run


class PrepareQueue:
    def __init__(
        self,
        runner: PrepareRunner,
        sync: bool = False,
        max_workers: int = 1,
    ) -> None:
        self._runner = runner
        self._sync = sync
        self._jobs: dict[str, PrepareJob] = {}
        self._queue: deque[dict] = deque()
        self._executor = (
            ThreadPoolExecutor(max_workers=max_workers) if not sync else None
        )
        self._futures: list = []

    def submit(
        self, payload: bytes, filename: str, bundle: str | None = None
    ) -> PrepareJob:
        job = PrepareJob(job_id=uuid.uuid4().hex[:12], status=PrepareStatus.QUEUED)
        self._jobs[job.job_id] = job
        item = {"job": job, "payload": payload, "filename": filename, "bundle": bundle}
        if self._sync:
            self._process(item)
        else:
            self._queue.append(item)
            self._drain_async()
        return job

    def _drain_async(self) -> None:
        self._futures = [f for f in self._futures if not f.done()]
        self._futures.append(self._executor.submit(self._drain))

    def _drain(self) -> None:
        while self._queue:
            self._process(self._queue.popleft())

    def _process(self, item: dict) -> None:
        job: PrepareJob = item["job"]
        logger.debug("prepare %s processing source=%s", job.job_id, item["filename"])
        with task_run(
            "prepare", job.job_id, source=item["filename"], bundle=item["bundle"] or ""
        ) as span:
            self._runner.run(job, item["payload"], item["filename"], item["bundle"])
            span.set_attribute("cortex.status", job.status.value)
            if job.status is PrepareStatus.FAILED:
                messages = [str(error.reason) for error in job.errors]
                span.set_attribute("cortex.errors", messages)
                span.set_status(trace.Status(trace.StatusCode.ERROR, "; ".join(messages)))
        if job.status is PrepareStatus.FAILED:
            logger.error(
                "prepare %s failed errors=%s",
                job.job_id,
                [str(error.reason) for error in job.errors],
            )
        else:
            logger.info(
                "prepare %s done created=%d updated=%d skipped=%d",
                job.job_id,
                len(job.created_concepts),
                len(job.updated_concepts),
                len(job.skipped_files),
            )

    def get(self, job_id: str) -> PrepareJob | None:
        return self._jobs.get(job_id)
