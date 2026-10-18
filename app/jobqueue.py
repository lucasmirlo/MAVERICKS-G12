"""Cola en PostgreSQL: reclamación con FOR UPDATE SKIP LOCKED, lease, heartbeat, reintentos con backoff."""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .db import utcnow
from .models import Job

LEASE_SECONDS = 90
PRIORITY_MANUAL_SYNC = 5
PRIORITY_MANUAL_BATCH = 10
PRIORITY_SCHEDULED_SYNC = 50
PRIORITY_RSS_ANALYSIS = 100


def enqueue(db: Session, kind: str, payload: dict, *, priority: int = 100, idempotency_key: str | None = None,
            batch_id: str | None = None, max_attempts: int = 3, run_at: datetime | None = None,
            error_code: str | None = None, error_message: str | None = None) -> tuple[str, bool]:
    """Inserta el trabajo si su clave no existe. Devuelve (job_id, creado)."""
    values = dict(kind=kind, payload=payload, priority=priority, idempotency_key=idempotency_key, batch_id=batch_id,
                  max_attempts=max_attempts, next_attempt_at=run_at or utcnow(), status="queued",
                  error_code=error_code, error_message=error_message)
    if idempotency_key:
        stmt = insert(Job).values(id=_uuid(), **values).on_conflict_do_nothing(index_elements=["idempotency_key"]).returning(Job.id)
        new_id = db.execute(stmt).scalar()
        if new_id:
            return new_id, True
        existing = db.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
        return existing.id, False
    job = Job(**values)
    db.add(job)
    db.flush()
    return job.id, True


def _uuid() -> str:
    import uuid
    return str(uuid.uuid4())


def requeue(db: Session, job: Job, *, priority: int | None = None) -> None:
    job.status = "queued"
    job.attempts = 0
    job.next_attempt_at = utcnow()
    job.error_code = job.error_message = None
    job.lease_owner = job.lease_until = None
    job.finished_at = None
    job.started_at = None  # para medir cola y proceso de la nueva ejecución
    if priority is not None:
        job.priority = priority


def recover_expired(db: Session) -> int:
    """Trabajos con lease vencida y sin intentos restantes pasan a failed; el resto se reclama de nuevo."""
    res = db.execute(text(
        "UPDATE jobs SET status='failed', error_code='lease_expired', "
        "error_message='El worker dejó de renovar la lease y no quedan intentos.', finished_at=now() "
        "WHERE status='running' AND lease_until < now() AND attempts >= max_attempts"))
    db.commit()
    return res.rowcount or 0


def claim(db: Session, worker_id: str, kinds: tuple[str, ...] | None = None) -> Job | None:
    kind_filter = "AND kind = ANY(:kinds)" if kinds else ""
    row = db.execute(text(f"""
        UPDATE jobs SET status='running', lease_owner=:w, lease_until=now() + make_interval(secs => :lease),
               heartbeat_at=now(), attempts=attempts+1, started_at=COALESCE(started_at, now())
        WHERE id = (
            SELECT id FROM jobs
            WHERE ((status='queued' AND next_attempt_at <= now())
                   OR (status='running' AND lease_until < now() AND attempts < max_attempts)) {kind_filter}
            ORDER BY priority, next_attempt_at, seq
            FOR UPDATE SKIP LOCKED
            LIMIT 1)
        RETURNING id"""), {"w": worker_id, "lease": LEASE_SECONDS, "kinds": list(kinds or [])}).scalar()
    db.commit()
    return db.get(Job, row, populate_existing=True) if row else None


def heartbeat(db: Session, job_id: str, worker_id: str) -> bool:
    res = db.execute(text("UPDATE jobs SET heartbeat_at=now(), lease_until=now() + make_interval(secs => :lease) "
                          "WHERE id=:id AND lease_owner=:w AND status='running'"),
                     {"id": job_id, "w": worker_id, "lease": LEASE_SECONDS})
    db.commit()
    return bool(res.rowcount)


def complete(db: Session, job_id: str, worker_id: str) -> None:
    db.execute(update(Job).where(Job.id == job_id, Job.lease_owner == worker_id)
               .values(status="done", finished_at=utcnow(), lease_until=None, error_code=None, error_message=None))
    db.commit()


def fail(db: Session, job_id: str, worker_id: str, *, code: str, message: str, retryable: bool,
         retry_after: float | None = None) -> str:
    job = db.get(Job, job_id)
    if job is None or job.lease_owner != worker_id:
        db.rollback()
        return "lost"
    job.error_code = code
    job.error_message = message[:2000]
    job.lease_until = None
    if retryable and job.attempts < job.max_attempts:
        delay = retry_after if retry_after is not None else min(60, 5 * 2 ** (job.attempts - 1)) + random.uniform(0, 2)
        job.status = "queued"
        job.next_attempt_at = utcnow() + timedelta(seconds=delay)
        outcome = "retry"
    else:
        job.status = "failed"
        job.finished_at = utcnow()
        outcome = "failed"
    db.commit()
    return outcome
