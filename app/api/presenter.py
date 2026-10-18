"""Mutaciones protegidas por sesión de presentador + CSRF."""
from __future__ import annotations

import json
import time
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import incidents as incident_engine
from .. import jobqueue
from .. import queries as q
from ..config import get_settings, load_json
from ..db import get_db, utcnow
from ..evaluation import run as run_evaluation
from ..importer import ImportFailure, import_workbook
from ..jev.client import JevClient, JevError
from ..jev.questions import QUESTION_VERSION
from ..models import (
    CONTEXT_EXERCISE,
    CONTEXTS,
    Alert,
    Analysis,
    Article,
    ArticleVersion,
    Draft,
    EvaluationRun,
    ImportBatch,
    Incident,
    JevCall,
    Job,
    Source,
    Supplier,
    SupplierAssessment,
)
from ..pipeline import engine_mode
from ..policy import active_policy, create_version
from ..security import COOKIE, MAX_AGE, ApiError, Presenter, check_rate, issue_session, presenter_configured, verify_password
from ..texts import PROMPT_DRAFT, PROMPT_EXPLAIN, alternate_draft, context_hash, explanation, generate, supplier_draft
from .public import draft_dict

router = APIRouter()


class LoginBody(BaseModel):
    password: str = Field(min_length=1, max_length=200)


@router.post("/session")
def login(body: LoginBody, request: Request, response: Response):
    if not presenter_configured():
        raise ApiError(503, "presenter_not_configured", "El acceso de presentador no está configurado en el servidor (ADMIN_PASSWORD y SESSION_SECRET).")
    check_rate(request.client.host if request.client else "unknown")
    if not verify_password(body.password):
        raise ApiError(401, "invalid_password", "Contraseña incorrecta.")
    token, csrf = issue_session()
    response.set_cookie(COOKIE, token, max_age=MAX_AGE, httponly=True, secure=get_settings().secure_cookies, samesite="lax", path="/")
    return {"presenter": True, "csrf": csrf}


@router.delete("/session")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"presenter": False}


# ---------------------------------------------------------------- importación y lotes

@router.post("/imports", dependencies=[Presenter])
async def upload(file: UploadFile = File(...), context_id: str = Form(CONTEXT_EXERCISE), db: Session = Depends(get_db)):
    if context_id != CONTEXT_EXERCISE:
        raise ApiError(400, "invalid_context", "Los Excel del reto se importan en el contexto Ejercicio.")
    limit = get_settings().import_max_bytes
    data = await file.read(limit + 1)
    try:
        return import_workbook(db, data, file.filename or "archivo.xlsx", context_id)
    except ImportFailure as exc:
        db.rollback()
        raise ApiError(400, exc.code, exc.message, exc.details) from exc


class ManifestImport(BaseModel):
    path: str


@router.post("/imports/manifest", dependencies=[Presenter])
def import_from_manifest(body: ManifestImport, db: Session = Depends(get_db)):
    """Importa una entrada declarada en evidence/input_manifest.json. Nunca recorre carpetas."""
    settings = get_settings()
    manifest = load_json(settings.resolve(settings.input_manifest_path))
    entry = next((f for f in manifest["files"] if f["path"] == body.path and f["path"].endswith(".xlsx")), None)
    if entry is None:
        raise ApiError(400, "not_in_manifest", "La ruta no es un Excel declarado en el manifiesto de entradas.")
    data = settings.resolve(entry["path"]).read_bytes()
    try:
        return import_workbook(db, data, entry["path"].split("/")[-1], CONTEXT_EXERCISE)
    except ImportFailure as exc:
        db.rollback()
        raise ApiError(400, exc.code, exc.message, exc.details) from exc


@router.get("/imports/manifest", dependencies=[Presenter])
def manifest_entries():
    settings = get_settings()
    manifest = load_json(settings.resolve(settings.input_manifest_path))
    return {"files": [{"path": f["path"], "purpose": f["purpose"], "source_name": f["source_name"]} for f in manifest["files"] if f["path"].endswith(".xlsx")]}


class AnalyzeBody(BaseModel):
    retry_errors: bool = True
    force: bool = False


@router.post("/batches/{batch_id}/analyze", status_code=202, dependencies=[Presenter])
def analyze(batch_id: str, body: AnalyzeBody | None = None, db: Session = Depends(get_db)):
    body = body or AnalyzeBody()
    b = db.get(ImportBatch, batch_id)
    if b is None or b.kind != "news":
        raise ApiError(404, "batch_not_found", "Lote no encontrado.")
    mode = engine_mode()
    if mode == "unconfigured":
        raise ApiError(409, "engine_not_configured", "Motor sin configurar: el análisis necesita TYPESAFE_API_KEY en el servidor.")
    if db.scalar(select(Supplier).limit(1)) is None:
        raise ApiError(409, "catalog_missing", "Importa primero el catálogo (Suppliers y Materials).")
    policy = active_policy(db)
    articles = list(db.scalars(select(Article).where(Article.batch_id == b.id).order_by(Article.row_index)))
    job_ids, created, requeued = [], 0, 0
    model = get_settings().jev_model if mode == "jev" else "fixture"
    for art in articles:
        key = f"analyze:{art.current_version_id}:{model}:{policy['version']}:{QUESTION_VERSION}"
        jid, new = jobqueue.enqueue(db, "analyze_article", {"version_id": art.current_version_id, "origin": "excel", "force": body.force},
                                    priority=jobqueue.PRIORITY_MANUAL_BATCH, idempotency_key=key, batch_id=b.id)
        if new:
            created += 1
        else:
            job = db.get(Job, jid)
            if job.status == "failed" and body.retry_errors or (body.force and job.status == "done"):
                jobqueue.requeue(db, job, priority=jobqueue.PRIORITY_MANUAL_BATCH)
                job.payload = {**job.payload, "force": body.force}
                requeued += 1
        job_ids.append(jid)
    if created or requeued or b.analysis_requested_at is None:
        b.analysis_requested_at = utcnow()
        b.analysis_completed_at = None
    db.commit()
    return {"batch_id": b.id, "job_ids": job_ids, "created": created, "requeued": requeued, "engine_mode": mode,
            "policy_version": policy["version"]}


@router.post("/batches/{batch_id}/reset", dependencies=[Presenter])
def reset_batch(batch_id: str, db: Session = Depends(get_db)):
    """Borra análisis, trabajos y caché JEV del lote (no las filas importadas) para repetir un ensayo en directo."""
    b = db.get(ImportBatch, batch_id)
    if b is None or b.kind != "news":
        raise ApiError(404, "batch_not_found", "Lote no encontrado.")
    if db.scalar(select(Job.id).where(Job.batch_id == b.id, Job.status == "running").limit(1)):
        raise ApiError(409, "batch_running", "El lote se está procesando; espera a que termine.")
    article_ids = [a for a in db.scalars(select(Article.id).where(Article.batch_id == b.id))]
    analyses = list(db.scalars(select(Analysis).where(Analysis.article_id.in_(article_ids)))) if article_ids else []
    hashes = {h for an in analyses for h in (an.request_hash_a, an.request_hash_b) if h}
    for an in analyses:
        db.delete(an)
    if hashes:
        db.execute(delete(JevCall).where(JevCall.request_hash.in_(hashes)))
    db.execute(delete(Job).where(Job.batch_id == b.id))
    b.analysis_requested_at = None
    b.analysis_completed_at = None
    db.commit()
    incident_engine.rebuild_context(db, b.context_id)
    return {"batch_id": b.id, "analyses_deleted": len(analyses), "cache_entries_deleted": len(hashes)}


class ManualDecision(BaseModel):
    is_risk: str = Field(pattern="^[YN]$")
    urgent: str = Field(pattern="^[YN]$")
    affected_supplier_ids: list[str] = []
    note: str = Field(min_length=3, max_length=1000)


@router.post("/analyses/{analysis_id}/manual", dependencies=[Presenter])
def manual_decision(analysis_id: str, body: ManualDecision, db: Session = Depends(get_db)):
    an = db.get(Analysis, analysis_id)
    if an is None:
        raise ApiError(404, "analysis_not_found", "Análisis no encontrado.")
    if an.status != "error":
        raise ApiError(409, "not_an_error", "Solo un análisis con error admite resolución manual explícita.")
    known = {s.supplier_id for s in db.scalars(select(Supplier))}
    ids = sorted(set(body.affected_supplier_ids))
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise ApiError(400, "unknown_suppliers", "IDs de proveedor desconocidos.", unknown)
    urgent = body.urgent if body.is_risk == "Y" else "N"
    an.manual_decision = {"is_risk": body.is_risk, "urgent": urgent, "affected_supplier_ids": ids, "note": body.note,
                          "at": utcnow().isoformat(), "by": "presenter"}
    db.commit()
    return {"analysis_id": an.id, "manual_decision": an.manual_decision}


# ---------------------------------------------------------------- RSS y motor

@router.post("/sources/sync", status_code=202, dependencies=[Presenter])
def sync_now(db: Session = Depends(get_db)):
    window = int(time.time() // 30)
    ids = []
    for s in db.scalars(select(Source).where(Source.enabled.is_(True))):
        jid, _ = jobqueue.enqueue(db, "sync_source", {"source_id": s.id, "manual": True}, priority=jobqueue.PRIORITY_MANUAL_SYNC,
                                  idempotency_key=f"manual-sync:{s.id}:{window}", max_attempts=1)
        ids.append(jid)
    db.commit()
    return {"job_ids": ids, "sources": len(ids)}


@router.post("/engine/test", dependencies=[Presenter])
def engine_test(db: Session = Depends(get_db)):
    """Prueba de conexión autenticada mínima (una pregunta Noul trivial)."""
    if engine_mode() != "jev":
        raise ApiError(409, "engine_not_configured", "Motor sin configurar: falta TYPESAFE_API_KEY.")
    s = get_settings()
    body = {"model": s.jev_model, "state": {"text": "The warehouse reopened on Monday after a short closure."},
            "questions": {"reopened": {"type": "noul", "instructions": "Does state.text say the warehouse reopened?"}}}
    t0 = time.monotonic()
    try:
        res = JevClient(max_retries=0).decide(body)
        noul = res.response.get("answers", {}).get("reopened", {}).get("noul")
        result = {"ok": isinstance(noul, (int, float)), "status": 200, "model": res.model, "requested_model": s.jev_model,
                  "latency_ms": res.duration_ms, "usage": res.usage, "at": utcnow().isoformat()}
    except JevError as exc:
        result = {"ok": False, "status": exc.status, "code": exc.code, "message": exc.message,
                  "latency_ms": int((time.monotonic() - t0) * 1000), "requested_model": s.jev_model, "at": utcnow().isoformat()}
    q.set_state(db, "engine_last_test", result)
    return result


# ---------------------------------------------------------------- alertas e incidentes

@router.post("/alerts/{alert_id}/ack", dependencies=[Presenter])
def ack(alert_id: str, db: Session = Depends(get_db)):
    al = db.get(Alert, alert_id)
    if al is None:
        raise ApiError(404, "alert_not_found", "Alerta no encontrada.")
    if al.status != "acknowledged":
        al.status = "acknowledged"
        al.acknowledged_at = utcnow()
        db.commit()
    return q.alert_dict(db, al)


@router.post("/alerts/ack-all", dependencies=[Presenter])
def ack_all(context_id: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Alert).where(Alert.status == "unread")
    if context_id:
        stmt = stmt.where(Alert.context_id == context_id)
    n = 0
    for al in db.scalars(stmt):
        al.status, al.acknowledged_at = "acknowledged", utcnow()
        n += 1
    db.commit()
    return {"acknowledged": n}


class ResolveBody(BaseModel):
    note: str = Field(min_length=5, max_length=1000)


@router.post("/incidents/{incident_id}/resolve", dependencies=[Presenter])
def resolve(incident_id: str, body: ResolveBody, db: Session = Depends(get_db)):
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise ApiError(404, "incident_not_found", "Incidente no encontrado.")
    if inc.status == "resolved":
        raise ApiError(409, "already_resolved", "El incidente ya está resuelto.")
    incident_engine.resolve_manually(db, inc, body.note)
    clock, _ = q.context_clock(db, inc.context_id)
    return q.incident_summary(db, inc, clock)


class ClockBody(BaseModel):
    date: str | None = None


@router.put("/context/{context_id}/clock", dependencies=[Presenter])
def set_clock(context_id: str, body: ClockBody, db: Session = Depends(get_db)):
    if context_id != CONTEXT_EXERCISE:
        raise ApiError(400, "invalid_context", "Solo el contexto Ejercicio usa reloj lógico.")
    if body.date:
        try:
            dt = datetime.fromisoformat(body.date)
        except ValueError as exc:
            raise ApiError(400, "invalid_date", "Fecha no válida (AAAA-MM-DD).") from exc
        if dt.tzinfo is None:
            from datetime import timezone
            dt = dt.replace(tzinfo=timezone.utc)
        q.set_state(db, f"clock:{context_id}", dt.isoformat())
    else:
        q.set_state(db, f"clock:{context_id}", None)
    clock, kind = q.context_clock(db, context_id)
    return {"clock": q.iso(clock), "clock_kind": kind}


# ---------------------------------------------------------------- borradores y explicaciones

class DraftCreate(BaseModel):
    kind: str = Field(pattern="^(supplier|alternate)$")
    supplier_id: str
    incident_id: str | None = None
    article_id: str | None = None
    use_generator: bool = False


def _draft_context(db: Session, supplier: Supplier, article_id: str | None, policy: dict) -> dict:
    art = db.get(Article, article_id) if article_id else None
    if art is None:
        alt = db.get(Supplier, supplier.alternate_id) if supplier.alternate_id else None
        return {"supplier_id": supplier.supplier_id, "supplier_name": supplier.name, "material": supplier.material,
                "alternate_supplier_name": alt.name if alt else None, "alternate_supplier_id": alt.supplier_id if alt else None,
                "alternate_approved": bool(alt)}
    version = db.get(ArticleVersion, art.current_version_id)
    an = q.current_analysis(db, art)
    a = next((x for x in an.assessments if x.supplier_id == supplier.supplier_id), None) if an else None
    if a is None:
        raise ApiError(409, "no_assessment", "La noticia no tiene una evaluación para este proveedor.")
    ctx = q.explanation_context(db, a, an, art, version, policy)
    ctx["article_version_id"] = version.id
    return ctx


@router.post("/drafts", dependencies=[Presenter])
def create_draft(body: DraftCreate, db: Session = Depends(get_db)):
    supplier = db.get(Supplier, body.supplier_id)
    if supplier is None:
        raise ApiError(404, "supplier_not_found", "Proveedor desconocido.")
    article_id = body.article_id
    if body.incident_id and not article_id:
        inc = db.get(Incident, body.incident_id)
        if inc is None:
            raise ApiError(404, "incident_not_found", "Incidente no encontrado.")
        last = next((h for h in reversed(inc.history or []) if h.get("article_id") and h.get("role") in ("trigger", "update")), None)
        article_id = last["article_id"] if last else None
    ctx = _draft_context(db, supplier, article_id, active_policy(db))
    if body.kind == "alternate":
        if not ctx.get("alternate_supplier_name"):
            raise ApiError(409, "no_alternate", "No hay alternativo aprobado para este material; no se genera la consulta.")
        subject, template = alternate_draft(ctx)
        target = ctx["alternate_supplier_id"]
    else:
        subject, template = supplier_draft(ctx)
        target = supplier.supplier_id
    text, generator, gen_error = (generate(PROMPT_DRAFT, ctx, template) if body.use_generator else (template, "template", None))
    d = Draft(kind=body.kind, supplier_id=supplier.supplier_id, target_supplier_id=target, incident_id=body.incident_id, article_id=article_id,
              recipient=None, subject=subject, body=text, generator=generator, factual_context=json.loads(json.dumps(ctx, default=str)),
              factual_context_hash=context_hash(ctx))
    db.add(d)
    db.commit()
    out = draft_dict(d)
    out["generator_error"] = gen_error
    return out


class DraftPatch(BaseModel):
    subject: str | None = Field(None, max_length=500)
    body: str | None = Field(None, max_length=20000)
    recipient: str | None = Field(None, max_length=255)


@router.patch("/drafts/{draft_id}", dependencies=[Presenter])
def patch_draft(draft_id: str, body: DraftPatch, db: Session = Depends(get_db)):
    d = db.get(Draft, draft_id)
    if d is None:
        raise ApiError(404, "draft_not_found", "Borrador no encontrado.")
    for field in ("subject", "body", "recipient"):
        v = getattr(body, field)
        if v is not None:
            setattr(d, field, v)
    d.edited = True
    db.commit()
    return draft_dict(d)


@router.post("/assessments/{assessment_id}/explanation", dependencies=[Presenter])
def explain(assessment_id: str, db: Session = Depends(get_db)):
    a = db.get(SupplierAssessment, assessment_id)
    if a is None:
        raise ApiError(404, "assessment_not_found", "Evaluación no encontrada.")
    an = db.get(Analysis, a.analysis_id)
    art = db.get(Article, an.article_id)
    version = db.get(ArticleVersion, an.article_version_id)
    ctx = q.explanation_context(db, a, an, art, version, active_policy(db))
    template = explanation(ctx)
    text, generator, err = generate(PROMPT_EXPLAIN, ctx, template)
    return {"text": text, "generator": generator, "template": template, "error": err}


# ---------------------------------------------------------------- evaluación y política

@router.post("/evaluations/{batch_id}", dependencies=[Presenter])
def evaluate(batch_id: str, db: Session = Depends(get_db)):
    try:
        r = run_evaluation(db, batch_id)
    except ValueError as exc:
        raise ApiError(409, "evaluation_unavailable", str(exc)) from exc
    return {"id": r.id, "batch_id": r.batch_id, "split": r.split, "policy_version": r.policy_version, "model_id": r.model_id,
            "metrics": r.metrics, "created_at": q.iso(r.created_at)}


@router.get("/evaluations", dependencies=[Presenter])
def evaluations(batch_id: str | None = None, db: Session = Depends(get_db)):
    stmt = select(EvaluationRun).order_by(EvaluationRun.created_at.desc())
    if batch_id:
        stmt = stmt.where(EvaluationRun.batch_id == batch_id)
    return {"items": [{"id": r.id, "batch_id": r.batch_id, "split": r.split, "policy_version": r.policy_version, "model_id": r.model_id,
                       "metrics": r.metrics, "created_at": q.iso(r.created_at)} for r in db.scalars(stmt.limit(20))]}


class PolicyChange(BaseModel):
    weights: dict[str, float] | None = None
    thresholds: dict[str, float] | None = None
    note: str = Field(min_length=3, max_length=500)


@router.put("/policy", dependencies=[Presenter])
def change_policy(body: PolicyChange, db: Session = Depends(get_db)):
    current = active_policy(db)
    try:
        row = create_version(db, base_version=current["version"], changes=body.model_dump(exclude_none=True), note=body.note)
    except ValueError as exc:
        raise ApiError(400, "invalid_policy", str(exc)) from exc
    return {"version": row.version, "data": row.data,
            "note": "La nueva versión se aplica a los próximos análisis; vuelve a analizar un lote para recalcular (las respuestas JEV en caché se reutilizan)."}
