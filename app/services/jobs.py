"""Background job queue: submit / cancel / get_job (report section 5).

UI-agnostic: the Qt layer passes an on_update callback and re-emits it as a
signal so widgets are only touched on the GUI thread.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime

from app import limits
from app.models import (
    Cancelled,
    ConversionJob,
    ConversionRequest,
    ConversionResult,
    ErrorCode,
    JobStatus,
    QuickConvertError,
)
from app.services import conversion

log = logging.getLogger("quickconvert.jobs")

Runner = Callable[[ConversionRequest, Callable[[], None], str], ConversionResult]


class JobManager:
    def __init__(self, max_workers: int = limits.MAX_CONCURRENT_JOBS,
                 on_update: Callable[[ConversionJob], None] | None = None,
                 runner: Runner = conversion.run):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="qc-job")
        self._lock = threading.Lock()
        self._jobs: dict[str, ConversionJob] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._futures: dict[str, Future] = {}
        self._on_update = on_update
        self._runner = runner

    def submit(self, request: ConversionRequest) -> str:
        """Validate and enqueue; raises QuickConvertError for requests that cannot run."""
        conversion.validate(request)
        job = ConversionJob(request)
        with self._lock:
            self._jobs[job.id] = job
            self._cancel_events[job.id] = threading.Event()
        self._notify(job)
        self._futures[job.id] = self._executor.submit(self._run, job.id)
        return job.id

    def cancel(self, job_id: str) -> bool:
        """Request cancellation. Running jobs stop at the next safe boundary."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status.is_final:
                return False
            self._cancel_events[job_id].set()
            if job.status is JobStatus.QUEUED:
                self._finish(job, JobStatus.CANCELLED)
        if job.status is JobStatus.CANCELLED:
            self._notify(job)
        return True

    def get_job(self, job_id: str) -> ConversionJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dataclasses.replace(job) if job else None

    def wait(self, job_id: str, timeout: float | None = None) -> ConversionJob | None:
        future = self._futures.get(job_id)
        if future is not None:
            future.result(timeout)
        return self.get_job(job_id)

    def shutdown(self) -> None:
        """Cancel everything and wait for workers to clean up their temp files."""
        with self._lock:
            for event in self._cancel_events.values():
                event.set()
        self._executor.shutdown(wait=True, cancel_futures=True)

    # --- worker side -------------------------------------------------------

    def _run(self, job_id: str) -> None:
        event = self._cancel_events[job_id]
        with self._lock:
            job = self._jobs[job_id]
            if job.status is not JobStatus.QUEUED:
                return
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now()
        self._notify(job)

        def check_cancel() -> None:
            if event.is_set():
                raise Cancelled()

        status, result, error = JobStatus.COMPLETED, None, None
        try:
            result = self._runner(job.request, check_cancel, job_id)
        except Cancelled:
            status = JobStatus.CANCELLED
        except QuickConvertError as exc:
            status, error = JobStatus.FAILED, exc
            log.info("job %s failed: %s", job_id, exc.code.value, exc_info=exc.__cause__)
        except Exception as exc:
            status = JobStatus.FAILED
            error = QuickConvertError(ErrorCode.CONVERSION_FAILED, "The conversion failed.")
            log.exception("job %s crashed", job_id, exc_info=exc)

        with self._lock:
            self._finish(job, status, result, error)
        self._notify(job)

    def _finish(self, job: ConversionJob, status: JobStatus,
                result: ConversionResult | None = None,
                error: QuickConvertError | None = None) -> None:
        job.status = status
        job.finished_at = datetime.now()
        job.result = result
        if status is JobStatus.COMPLETED:
            job.progress = 1.0
        if error is not None:
            job.error_code, job.error_message = error.code, error.message

    def _notify(self, job: ConversionJob) -> None:
        if self._on_update is not None:
            try:
                self._on_update(self.get_job(job.id))
            except Exception:
                log.exception("on_update callback failed")
