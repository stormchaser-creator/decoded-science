"""Redis job queue for the Decoded pipeline."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import redis
import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Queue names
# ---------------------------------------------------------------------------

QUEUE_INGEST = "decoded:queue:ingest"
QUEUE_EXTRACT = "decoded:queue:extract"
QUEUE_CONNECT = "decoded:queue:connect"
QUEUE_CRITIQUE = "decoded:queue:critique"
QUEUE_DEAD = "decoded:queue:dead"

# Key prefixes
JOB_KEY_PREFIX = "decoded:job:"
LOCK_KEY_PREFIX = "decoded:lock:"


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"


@dataclass
class Job:
    """A unit of work in the pipeline queue."""

    job_type: str
    payload: dict[str, Any]
    job_id: str = field(default_factory=lambda: str(uuid4()))
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    error: str | None = None
    priority: int = 0  # higher = more urgent

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "payload": self.payload,
            "status": self.status.value,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        return cls(
            job_id=data["job_id"],
            job_type=data["job_type"],
            payload=data["payload"],
            status=JobStatus(data["status"]),
            attempts=data["attempts"],
            max_attempts=data["max_attempts"],
            created_at=data["created_at"],
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            error=data.get("error"),
            priority=data.get("priority", 0),
        )


class PipelineQueue:
    """Redis-backed job queue with dead-letter support."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._redis = redis.from_url(redis_url, decode_responses=True)

    # ------------------------------------------------------------------
    # Enqueueing
    # ------------------------------------------------------------------

    def enqueue(
        self,
        queue: str,
        job_type: str,
        payload: dict[str, Any],
        priority: int = 0,
        max_attempts: int = 3,
    ) -> Job:
        job = Job(
            job_type=job_type,
            payload=payload,
            priority=priority,
            max_attempts=max_attempts,
        )
        pipe = self._redis.pipeline()
        pipe.set(f"{JOB_KEY_PREFIX}{job.job_id}", json.dumps(job.to_dict()))
        # Use a sorted set: score = priority (higher score = higher priority)
        pipe.zadd(queue, {job.job_id: priority})
        pipe.execute()
        logger.info("job_enqueued", queue=queue, job_id=job.job_id, job_type=job_type)
        return job

    def enqueue_paper_ingest(self, query: str, source: str = "pubmed", max_results: int = 100) -> Job:
        return self.enqueue(
            QUEUE_INGEST,
            job_type="ingest_query",
            payload={"query": query, "source": source, "max_results": max_results},
        )

    def enqueue_extraction(self, paper_id: str | UUID, priority: int = 0) -> Job:
        return self.enqueue(
            QUEUE_EXTRACT,
            job_type="extract_paper",
            payload={"paper_id": str(paper_id)},
            priority=priority,
        )

    def enqueue_connection(self, paper_id: str | UUID) -> Job:
        return self.enqueue(
            QUEUE_CONNECT,
            job_type="discover_connections",
            payload={"paper_id": str(paper_id)},
        )

    def enqueue_critique(self, paper_id: str | UUID) -> Job:
        return self.enqueue(
            QUEUE_CRITIQUE,
            job_type="critique_paper",
            payload={"paper_id": str(paper_id)},
        )

    # ------------------------------------------------------------------
    # Dequeueing
    # ------------------------------------------------------------------

    def dequeue(self, queue: str, timeout: int = 0) -> Job | None:
        """Pop the highest-priority job from the queue."""
        # ZPOPMAX returns list of (member, score) pairs
        result = self._redis.zpopmax(queue, 1)
        if not result:
            if timeout > 0:
                # Blocking wait using a helper loop
                deadline = time.time() + timeout
                while time.time() < deadline:
                    result = self._redis.zpopmax(queue, 1)
                    if result:
                        break
                    time.sleep(0.1)
            if not result:
                return None

        job_id, _score = result[0]
        raw = self._redis.get(f"{JOB_KEY_PREFIX}{job_id}")
        if not raw:
            logger.warning("job_data_missing", job_id=job_id)
            return None

        job = Job.from_dict(json.loads(raw))
        job.status = JobStatus.PROCESSING
        job.attempts += 1
        job.started_at = time.time()
        self._redis.set(f"{JOB_KEY_PREFIX}{job_id}", json.dumps(job.to_dict()))
        return job

    # ------------------------------------------------------------------
    # Completion / failure
    # ------------------------------------------------------------------

    def complete(self, job: Job) -> None:
        job.status = JobStatus.COMPLETED
        job.completed_at = time.time()
        self._redis.set(f"{JOB_KEY_PREFIX}{job.job_id}", json.dumps(job.to_dict()))
        logger.info("job_completed", job_id=job.job_id, job_type=job.job_type)

    def fail(self, job: Job, error: str, requeue: bool = True) -> None:
        job.error = error
        if requeue and job.attempts < job.max_attempts:
            job.status = JobStatus.PENDING
            queue = self._queue_for_type(job.job_type)
            self._redis.set(f"{JOB_KEY_PREFIX}{job.job_id}", json.dumps(job.to_dict()))
            self._redis.zadd(queue, {job.job_id: job.priority})
            logger.warning("job_requeued", job_id=job.job_id, attempts=job.attempts)
        else:
            job.status = JobStatus.DEAD
            job.completed_at = time.time()
            self._redis.set(f"{JOB_KEY_PREFIX}{job.job_id}", json.dumps(job.to_dict()))
            self._redis.zadd(QUEUE_DEAD, {job.job_id: time.time()})
            logger.error("job_dead", job_id=job.job_id, error=error)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def queue_length(self, queue: str) -> int:
        return self._redis.zcard(queue)

    def get_job(self, job_id: str) -> Job | None:
        raw = self._redis.get(f"{JOB_KEY_PREFIX}{job_id}")
        if not raw:
            return None
        return Job.from_dict(json.loads(raw))

    def stats(self) -> dict[str, int]:
        return {
            "ingest": self.queue_length(QUEUE_INGEST),
            "extract": self.queue_length(QUEUE_EXTRACT),
            "connect": self.queue_length(QUEUE_CONNECT),
            "critique": self.queue_length(QUEUE_CRITIQUE),
            "dead": self.queue_length(QUEUE_DEAD),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _queue_for_type(self, job_type: str) -> str:
        mapping = {
            "ingest_query": QUEUE_INGEST,
            "extract_paper": QUEUE_EXTRACT,
            "discover_connections": QUEUE_CONNECT,
            "critique_paper": QUEUE_CRITIQUE,
        }
        return mapping.get(job_type, QUEUE_INGEST)

    def ping(self) -> bool:
        try:
            return self._redis.ping()
        except redis.ConnectionError:
            return False
