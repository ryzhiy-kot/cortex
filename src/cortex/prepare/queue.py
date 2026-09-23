import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from cortex.models import PrepareJob, PrepareStatus
from cortex.prepare.pipeline import PrepareRunner


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
        self._runner.run(job, item["payload"], item["filename"], item["bundle"])

    def get(self, job_id: str) -> PrepareJob | None:
        return self._jobs.get(job_id)
