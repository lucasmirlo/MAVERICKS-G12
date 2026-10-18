"""Worker persistente: atiende la cola de PostgreSQL y programa el sondeo RSS cada RSS_POLL_SECONDS.

Ejecutar con `python -m app.worker`. No ejecuta migraciones: espera a que el esquema esté en head.
"""
from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time
import uuid

from sqlalchemy import func, select, text

from . import incidents, jobqueue, rss
from .config import get_settings
from .db import SessionLocal, utcnow
from .logging_setup import setup_logging
from .models import ImportBatch, Job, Source, Supplier
from .pipeline import AnalysisFailed, analyze_version
from .policy import ensure_seeded

log = logging.getLogger("srr.worker")
stop_event = threading.Event()


def schema_ready() -> bool:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(Config(str(get_settings().resolve("alembic.ini")))).get_current_head()
    try:
        with SessionLocal() as db:
            current = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        return current == head
    except Exception:
        return False


def handle(job: Job, worker_id: str) -> None:
    with SessionLocal() as db:
        if job.kind == "analyze_article":
            version_id = job.payload["version_id"]
            try:
                analysis = analyze_version(db, version_id, force=bool(job.payload.get("force")))
                incidents.rebuild_context(db, analysis.context_id)
                jobqueue.complete(db, job.id, worker_id)
            except AnalysisFailed as exc:
                outcome = jobqueue.fail(db, job.id, worker_id, code=exc.error.code, message=exc.error.message,
                                        retryable=exc.error.retryable)
                log.warning("job=%s analyze failed code=%s outcome=%s", job.id, exc.error.code, outcome)
            _maybe_finish_batch(db, job.batch_id)
        elif job.kind == "sync_source":
            result = rss.sync_source(db, job.payload["source_id"], worker_id)
            if result.get("outcome") == "skipped_locked" and job.payload.get("manual"):
                # Otra sincronización de la misma fuente está en curso; la manual se considera atendida.
                pass
            jobqueue.complete(db, job.id, worker_id)
        else:
            jobqueue.fail(db, job.id, worker_id, code="unknown_kind", message=f"Tipo de trabajo desconocido: {job.kind}", retryable=False)


def _maybe_finish_batch(db, batch_id: str | None) -> None:
    if not batch_id:
        return
    pending = db.scalar(select(func.count(Job.id)).where(Job.batch_id == batch_id, Job.status.in_(("queued", "running"))))
    if pending == 0:
        batch = db.get(ImportBatch, batch_id)
        if batch and batch.analysis_completed_at is None:
            batch.analysis_completed_at = utcnow()
            db.commit()


def _heartbeat_loop(job_id: str, worker_id: str, done: threading.Event) -> None:
    while not done.wait(20):
        try:
            with SessionLocal() as db:
                jobqueue.heartbeat(db, job_id, worker_id)
        except Exception:  # noqa: BLE001
            log.exception("heartbeat failed job=%s", job_id)


def job_loop(worker_id: str) -> None:
    while not stop_event.is_set():
        try:
            with SessionLocal() as db:
                job = jobqueue.claim(db, worker_id)
            if job is None:
                stop_event.wait(1.0)
                continue
            done = threading.Event()
            hb = threading.Thread(target=_heartbeat_loop, args=(job.id, worker_id, done), daemon=True)
            hb.start()
            t0 = time.monotonic()
            try:
                handle(job, worker_id)
            except Exception as exc:  # noqa: BLE001
                log.exception("job=%s kind=%s crashed", job.id, job.kind)
                with SessionLocal() as db:
                    jobqueue.fail(db, job.id, worker_id, code="internal_error", message=f"{exc.__class__.__name__}", retryable=True)
            finally:
                done.set()
            log.info("job=%s kind=%s attempt=%s duration_ms=%s", job.id, job.kind, job.attempts, int((time.monotonic() - t0) * 1000))
        except Exception:  # noqa: BLE001
            log.exception("job loop error")
            stop_event.wait(3)


def schedule_rss() -> int:
    settings = get_settings()
    if not settings.rss_enabled:
        return 0
    created = 0
    now = utcnow()
    with SessionLocal() as db:
        for src in db.scalars(select(Source).where(Source.enabled.is_(True))):
            poll = src.poll_seconds or settings.rss_poll_seconds
            if src.last_attempt_at is None or (now - src.last_attempt_at).total_seconds() >= poll:
                window = int(now.timestamp() // poll)
                _, new = jobqueue.enqueue(db, "sync_source", {"source_id": src.id, "manual": False},
                                          priority=jobqueue.PRIORITY_SCHEDULED_SYNC, idempotency_key=f"sync:{src.id}:{window}",
                                          max_attempts=1)
                created += int(new)
        db.commit()
    return created


def scheduler_loop(worker_id: str) -> None:
    from .queries import set_state

    while not stop_event.is_set():
        try:
            with SessionLocal() as db:
                set_state(db, "worker_heartbeat", {"at": utcnow().isoformat(), "id": worker_id})
                # Trabajos que fallaron solo por falta de clave o de catálogo vuelven a la cola cuando ya existen.
                resolved = []
                if get_settings().jev_configured or get_settings().demo_fixtures_enabled:
                    resolved.append("engine_not_configured")
                if db.scalar(select(Supplier.supplier_id).limit(1)) is not None:
                    resolved.append("catalog_missing")
                if resolved:
                    db.execute(text("UPDATE jobs SET status='queued', attempts=0, next_attempt_at=now(), error_code=NULL, "
                                    "error_message=NULL, finished_at=NULL WHERE status='failed' AND error_code = ANY(:codes)"),
                               {"codes": resolved})
                    db.commit()
                recovered = jobqueue.recover_expired(db)
                if recovered:
                    log.warning("marked %s expired jobs as failed", recovered)
            schedule_rss()
        except Exception:  # noqa: BLE001
            log.exception("scheduler error")
        stop_event.wait(15)


def main() -> None:
    setup_logging()
    settings = get_settings()
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
    log.info("worker starting id=%s threads=%s engine=%s", worker_id, settings.worker_threads,
             "jev" if settings.jev_configured else ("fixture" if settings.demo_fixtures_enabled else "unconfigured"))
    while not schema_ready():
        log.info("waiting for database schema (alembic head)")
        if stop_event.wait(5):
            return
    with SessionLocal() as db:
        ensure_seeded(db)
        rss.seed_sources(db)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: stop_event.set())
        except ValueError:
            pass
    threads = [threading.Thread(target=job_loop, args=(f"{worker_id}#{n}",), daemon=True, name=f"job-{n}")
               for n in range(settings.worker_threads)]
    threads.append(threading.Thread(target=scheduler_loop, args=(worker_id,), daemon=True, name="scheduler"))
    for t in threads:
        t.start()
    while not stop_event.is_set():
        stop_event.wait(1)
    log.info("worker stopping")


if __name__ == "__main__":
    main()
