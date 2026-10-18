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
from .models import Analysis, ImportBatch, Job, Source, Supplier
from .adjudication import adjudicate_analysis, needs_adjudication
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
                _enqueue_plan_summaries(db, incidents.rebuild_context(db, analysis.context_id), job.priority)
                if needs_adjudication(analysis):
                    # Los resultados de JEV ya están publicados; las parejas dudosas quedan «en análisis».
                    # Fuera del modo llm la opinión no decide: va al final de la cola para no retrasar el lote.
                    decides = (analysis.urgency_mode or "llm") == "llm"
                    jobqueue.enqueue(db, "adjudicate_article", {"analysis_id": analysis.id, "version_id": version_id},
                                     priority=job.priority if decides else job.priority + 30, idempotency_key=f"adjudicate:{analysis.id}:{analysis.finished_at.timestamp():.3f}",
                                     batch_id=job.batch_id if decides else None,
                                     max_attempts=1)
                    db.commit()
                jobqueue.complete(db, job.id, worker_id)
            except AnalysisFailed as exc:
                outcome = jobqueue.fail(db, job.id, worker_id, code=exc.error.code, message=exc.error.message,
                                        retryable=exc.error.retryable)
                log.warning("job=%s analyze failed code=%s outcome=%s", job.id, exc.error.code, outcome)
            _maybe_finish_batch(db, job.batch_id)
        elif job.kind == "adjudicate_article":
            try:
                result = adjudicate_analysis(db, job.payload["analysis_id"])
                an = db.get(Analysis, job.payload["analysis_id"])
                if an is not None:
                    _enqueue_plan_summaries(db, incidents.rebuild_context(db, an.context_id), job.priority)
                log.info("job=%s adjudication %s", job.id, result)
            finally:
                jobqueue.complete(db, job.id, worker_id)
            _maybe_finish_batch(db, job.batch_id)
        elif job.kind == "plan_summary":
            from .actions import summarize_with_llm
            try:
                log.info("job=%s plan_summary %s", job.id, summarize_with_llm(db, job.payload["plan_id"]))
            finally:
                jobqueue.complete(db, job.id, worker_id)
        elif job.kind == "sync_source":
            result = rss.sync_source(db, job.payload["source_id"], worker_id)
            if result.get("outcome") == "skipped_locked" and job.payload.get("manual"):
                # Otra sincronización de la misma fuente está en curso; la manual se considera atendida.
                pass
            jobqueue.complete(db, job.id, worker_id)
        else:
            jobqueue.fail(db, job.id, worker_id, code="unknown_kind", message=f"Tipo de trabajo desconocido: {job.kind}", retryable=False)


def _enqueue_plan_summaries(db, rebuild: dict, priority: int) -> None:
    """El resumen del LLM es aparte: no retrasa el lote ni la exportación."""
    from . import llm
    if not rebuild.get("plans_changed") or not llm.is_available():
        return
    for pid in rebuild["plans_changed"]:
        jobqueue.enqueue(db, "plan_summary", {"plan_id": pid}, priority=priority + 20, max_attempts=1,
                         idempotency_key=f"plan_summary:{pid}:{int(time.time())}")
    db.commit()


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
        # Reconstrucción idempotente: aplica la lógica vigente de incidentes (p. ej. separación por lote) a los datos existentes.
        for context_id in ("exercise", "rss"):
            incidents.rebuild_context(db, context_id)
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
