"""Rutas públicas de lectura. No exponen etiquetas de evaluación, claves ni respuestas JEV en bruto."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import queries as q
from ..config import get_settings
from ..db import get_db, utcnow
from ..export import build_xlsx, export_status
from ..models import (
    CONTEXT_EXERCISE,
    CONTEXT_RSS,
    CONTEXTS,
    Alert,
    Analysis,
    Article,
    ArticleVersion,
    Draft,
    ImportBatch,
    Incident,
    Job,
    Source,
    Supplier,
    SupplierAssessment,
)
from ..jev.questions import QUESTION_VERSION
from ..pipeline import engine_mode
from ..revision import code_revision
from ..policy import active_policy
from ..security import ApiError, presenter_configured, read_session
from ..llm import status as llm_status
from ..texts import explanation, generator_available

router = APIRouter()


def batch_param(db: Session, context_id: str, batch_id: str | None) -> str | None:
    """Lote Excel seleccionado (solo en Ejercicio). Valida que exista y pertenezca al contexto."""
    if not batch_id or context_id == CONTEXT_RSS:
        return None
    b = db.get(ImportBatch, batch_id)
    if b is None or b.kind != "news" or b.context_id != context_id:
        raise ApiError(404, "batch_not_found", "Lote no encontrado en este contexto.")
    return b.id


def ctx_param(context_id: str = Query(CONTEXT_EXERCISE)) -> str:
    if context_id not in CONTEXTS:
        raise ApiError(400, "invalid_context", "Contexto desconocido.")
    return context_id


@router.get("/session")
def session_info(request: Request):
    session = read_session(request)
    return {"presenter": bool(session), "csrf": session["csrf"] if session else None, "login_available": presenter_configured()}


@router.get("/meta")
def meta(request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    policy = active_policy(db)
    mode = engine_mode()
    hb = q.get_state(db, "worker_heartbeat")
    worker_alive = bool(hb and utcnow() - datetime.fromisoformat(hb["at"]) < timedelta(seconds=60))
    is_presenter = bool(read_session(request))
    engine = {"mode": mode, "configured": mode == "jev", "model": s.jev_model if mode == "jev" else ("fixture-local-0" if mode == "fixture" else None),
              "last_test": q.get_state(db, "engine_last_test")}
    if is_presenter and mode != "jev":
        engine["missing_variable"] = "TYPESAFE_API_KEY"
    return {
        "app": "Supplier Risk Radar", "company": "Helixa Pharmaceuticals", "timezone": s.app_timezone,
        "contexts": [{"id": CONTEXT_EXERCISE, "label": "Ejercicio"}, {"id": CONTEXT_RSS, "label": "Noticias reales"}],
        "engine": engine, "fixtures_enabled": s.demo_fixtures_enabled and mode == "fixture",
        "policy": {"version": policy["version"], "status": policy["status"], "thresholds": policy["thresholds"],
                   "weights": policy["weights"], "bands": policy["bands"], "question_version": QUESTION_VERSION,
                   "criticality": policy["criticality"], "severity_floor": policy["severity_floor"], "exposure_weight": policy["exposure_weight"],
                   "buffer_not_applicable_categories": policy["buffer_not_applicable_categories"],
                   "event_types": list(policy["event_types"].keys())},
        "audio": policy["audio"],
        "worker": {"alive": worker_alive, "last_heartbeat": hb["at"] if hb else None, "revision": (hb or {}).get("revision"),
                   "web_revision": code_revision(), "compatible": bool(hb and hb.get("revision") == code_revision())},
        "rss": {"poll_seconds": s.rss_poll_seconds, "daily_budget": s.rss_daily_analysis_budget, "enabled": s.rss_enabled},
        "generator_available": generator_available(),
        "llm": llm_status(), "urgency_mode": s.urgency_mode,
        "catalog": {"suppliers": db.scalar(select(func.count(Supplier.supplier_id))) or 0},
    }


@router.get("/overview")
def overview(context_id: str = Depends(ctx_param), batch_id: str | None = None, db: Session = Depends(get_db)):
    batch_id = batch_param(db, context_id, batch_id)
    rank = q.ranking(db, context_id, batch_id)
    clock, clock_kind = q.context_clock(db, context_id, batch_id)
    inc_stmt = select(Incident).where(Incident.context_id == context_id)
    art_stmt = select(Article).where(Article.context_id == context_id)
    if batch_id:
        inc_stmt = inc_stmt.where(Incident.batch_id == batch_id)
        art_stmt = art_stmt.where(Article.batch_id == batch_id)
    incs = list(db.scalars(inc_stmt))
    active = [i for i in incs if i.status != "resolved"]
    articles = list(db.scalars(art_stmt))
    total_articles = len(articles)
    analyses = {a.id: q.current_analysis(db, a) for a in articles}
    status_counts = {"processed": 0, "review": 0, "error": 0, "pending": 0, "linked": 0, "risk": 0, "urgent": 0, "positive": 0}
    durations = []
    linked_suppliers = set()
    for an in analyses.values():
        if an is None or an.status in ("pending", "running"):
            status_counts["pending"] += 1
            continue
        if an.status == "error":
            status_counts["error"] += 1
            continue
        status_counts["processed"] += 1
        if an.status == "review":
            status_counts["review"] += 1
        if an.affected_supplier_ids:
            status_counts["linked"] += 1
            linked_suppliers.update(an.affected_supplier_ids)
        if an.is_risk == "Y":
            status_counts["risk"] += 1
        if an.urgent == "Y":
            status_counts["urgent"] += 1
        if an.event_type == "positive_news":
            status_counts["positive"] += 1
        if an.duration_ms and not an.cached:
            durations.append(an.duration_ms)
    # Las fuentes RSS (pitch) solo se muestran en Noticias reales; Ejercicio usa sus archivos Excel (evaluados).
    sources = [q.source_dict(db, s) for s in db.scalars(select(Source).order_by(Source.name))] if context_id == CONTEXT_RSS else []
    excel = [] if context_id == CONTEXT_RSS else [
        {**q.batch_progress(db, b), "export": export_status(db, b)}
        for b in db.scalars(select(ImportBatch).where(ImportBatch.context_id == context_id, ImportBatch.kind == "news"))]
    excel.sort(key=lambda b: ["training", "validation", "test", "liveday", "other"].index(b["split"]) if b["split"] in ("training", "validation", "test", "liveday", "other") else 9)
    bands = {"low": 0, "medium": 0, "high": 0, "critical": 0, "pending": 0}
    for i in active:
        bands[i.priority_band if i.priority_band in bands and i.current_priority is not None else "pending"] += 1
    by_source: dict[str, int] = {}
    if context_id == CONTEXT_RSS:
        for a in articles:
            by_source[a.source_name or "?"] = by_source.get(a.source_name or "?", 0) + 1
    latest = sorted(articles, key=lambda a: (a.published_at or a.first_seen_at, -(a.row_index or 0)), reverse=True)[:8]
    last_analysis = max((an.finished_at for an in analyses.values() if an and an.finished_at), default=None)
    return {
        "context_id": context_id, "context_label": q.CONTEXT_LABELS.get(context_id, context_id), "batch_id": batch_id,
        "clock": q.iso(clock), "clock_kind": clock_kind, "last_analysis_at": q.iso(last_analysis),
        "kpis": {
            "urgent_suppliers": sum(1 for r in rank if r["urgent"] == "Y"), "suppliers_total": len(rank),
            "active_incidents": len(active), "requires_update": sum(1 for r in rank if r["requires_update"]),
            "incidents_total": len(incs), "articles_total": total_articles, **status_counts,
            "linked_suppliers": len(linked_suppliers),
            "sources_operational": sum(1 for s in sources if s["healthy"]), "sources_total": len(sources),
            "batches_analyzed": sum(1 for b in excel if b["counts"]["done"] + b["counts"]["review"] == b["row_count"] and b["row_count"]),
            "batches_total": len(excel),
        },
        "ranking": rank[:12], "latest": [q.article_brief(db, a, analyses[a.id]) for a in latest], "sources": sources,
        "attention": q.attention_desk(db, context_id, batch_id),
        "priority_distribution": bands, "by_source": by_source, "latency": q.latency(durations),
        "batches": excel,
    }


@router.get("/suppliers")
def suppliers(context_id: str = Depends(ctx_param), search: str | None = Query(None, alias="q"), category: str | None = None,
              criticality: str | None = None, single_source: str | None = None, has_alternate: bool | None = None,
              urgent: bool | None = None, active_only: bool = False, products: str | None = None,
              batch_id: str | None = None,
              page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    rows = q.ranking(db, context_id, batch_param(db, context_id, batch_id))
    if search:
        needle = search.lower()
        rows = [r for r in rows if needle in " ".join(str(r.get(k) or "") for k in ("supplier_id", "name", "country", "city", "material", "category")).lower()]
    if category:
        rows = [r for r in rows if r["category"] == category]
    if criticality:
        rows = [r for r in rows if r["criticality"] == criticality]
    if single_source in ("Y", "N"):
        rows = [r for r in rows if r["single_source"] == single_source]
    if has_alternate is not None:
        rows = [r for r in rows if bool(r["alternate_id"]) == has_alternate]
    if urgent is not None:
        rows = [r for r in rows if (r["urgent"] == "Y") == urgent]
    if active_only:
        rows = [r for r in rows if r["active_incidents"]]
    if products == "mapped":
        rows = [r for r in rows if r["products_mapped"]]
    elif products == "unmapped":
        rows = [r for r in rows if not r["products_mapped"]]
    total = len(rows)
    start = (page - 1) * page_size
    categories = sorted({s.category for s in db.scalars(select(Supplier)) if s.category})
    return {"items": rows[start:start + page_size], "total": total, "page": page, "page_size": page_size, "categories": categories}


@router.get("/suppliers/{supplier_id}")
def supplier_detail(supplier_id: str, context_id: str = Depends(ctx_param), batch_id: str | None = None, db: Session = Depends(get_db)):
    s = db.get(Supplier, supplier_id)
    if s is None:
        raise ApiError(404, "supplier_not_found", f"No existe el proveedor {supplier_id}.")
    batch_id = batch_param(db, context_id, batch_id)
    policy = active_policy(db)
    clock, _ = q.context_clock(db, context_id, batch_id)
    alt = db.get(Supplier, s.alternate_id) if s.alternate_id else None
    backed_up_by = [q.supplier_brief(x) for x in db.scalars(select(Supplier).where(Supplier.alternate_id == supplier_id))]
    prod = q.products_by_supplier(db).get(supplier_id)
    inc_stmt = select(Incident).where(Incident.context_id == context_id, Incident.supplier_id == supplier_id)
    if batch_id:
        inc_stmt = inc_stmt.where(Incident.batch_id == batch_id)
    incs = list(db.scalars(inc_stmt.order_by(Incident.last_evidence_at.desc())))
    inc_dicts = [q.incident_summary(db, i, clock) for i in incs]
    # Noticias vinculadas: parejas aceptadas de análisis vigentes en este contexto.
    news = []
    rows = db.execute(select(SupplierAssessment, Analysis, Article).join(Analysis, Analysis.id == SupplierAssessment.analysis_id)
                      .join(Article, Article.id == Analysis.article_id)
                      .where(SupplierAssessment.supplier_id == supplier_id, Article.context_id == context_id,
                             Analysis.article_version_id == Article.current_version_id,
                             *( [Article.batch_id == batch_id] if batch_id else [] ))
                      .order_by(Article.published_at.desc(), Analysis.created_at.desc())).all()
    seen = set()
    for a, an, art in rows:
        if art.id in seen:
            continue
        seen.add(art.id)
        version = db.get(ArticleVersion, art.current_version_id)
        news.append({"article": q.article_brief(db, art, an, version), "assessment": q.assessment_dict(a, an.evidence),
                     "explanation": explanation(q.explanation_context(db, a, an, art, version, policy))})
    active = [i for i in inc_dicts if i["status"] != "resolved"]
    top = max(active, key=lambda i: i["current_priority"] or -1, default=None)
    breakdown = None
    if top:
        a = db.scalar(select(SupplierAssessment).where(SupplierAssessment.incident_id == top["id"], SupplierAssessment.supplier_id == supplier_id)
                      .order_by(SupplierAssessment.priority.desc().nulls_last()).limit(1))
        if a:
            breakdown = {"priority": a.priority, "severity": a.severity, "exposure": a.exposure, "factors": a.factor_values,
                         "contributions": a.contributions, "weights": policy["weights"], "severity_floor": policy["severity_floor"],
                         "exposure_weight": policy["exposure_weight"], "policy_version": a.policy_version,
                         "duration_days": a.duration_days, "duration_is_lower_bound": a.duration_is_lower_bound,
                         "review_reasons": a.review_reasons}
    drafts = [draft_dict(d) for d in db.scalars(select(Draft).where(Draft.supplier_id == supplier_id).order_by(Draft.updated_at.desc()))]
    return {"supplier": q.supplier_full(s, policy), "alternate": q.supplier_full(alt, policy) if alt else None,
            "backup_for": backed_up_by, "materials": prod["materials"] if prod else [], "products": prod["products"] if prod else [],
            "products_mapped": bool(prod and prod["products"]), "incidents": inc_dicts,
            "priority": max((i["current_priority"] for i in active if i["current_priority"] is not None), default=0.0 if not active else None),
            "historical_priority": max((i["historical_priority"] or 0 for i in inc_dicts), default=None) if inc_dicts else None,
            "breakdown": breakdown, "news": news, "drafts": drafts, "context_id": context_id, "clock": q.iso(clock)}


@router.get("/articles")
def articles(context_id: str = Depends(ctx_param), source_id: str | None = None, batch_id: str | None = None,
             relevance: str | None = None, event_type: str | None = None, search: str | None = Query(None, alias="q"),
             date_from: str | None = Query(None, alias="from"), date_to: str | None = Query(None, alias="to"),
             page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)):
    stmt = select(Article).where(Article.context_id == context_id)
    if source_id:
        stmt = stmt.where(Article.source_id == source_id)
    if batch_id:
        stmt = stmt.where(Article.batch_id == batch_id)
    if date_from:
        stmt = stmt.where(Article.published_at >= datetime.fromisoformat(date_from))
    if date_to:
        stmt = stmt.where(Article.published_at < datetime.fromisoformat(date_to) + timedelta(days=1))
    if search:
        like = f"%{search}%"
        stmt = stmt.join(ArticleVersion, ArticleVersion.id == Article.current_version_id).where(
            or_(ArticleVersion.headline.ilike(like), ArticleVersion.summary.ilike(like), Article.external_id.ilike(like)))
    order = (Article.batch_id, Article.row_index) if batch_id else (Article.published_at.desc().nulls_last(), Article.first_seen_at.desc())
    items = [q.article_brief(db, a) for a in db.scalars(stmt.order_by(*order))]
    if relevance:
        wanted = set(relevance.split(","))
        items = [i for i in items if i["relevance"] in wanted or (("review" in wanted) and i["needs_review"])]
    if event_type:
        items = [i for i in items if i["event_type"] == event_type]
    counts: dict[str, int] = {}
    for i in items:
        counts[i["relevance"]] = counts.get(i["relevance"], 0) + 1
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": len(items), "page": page, "page_size": page_size, "counts": counts}


@router.get("/articles/{article_id}")
def article(article_id: str, db: Session = Depends(get_db)):
    art = db.get(Article, article_id)
    if art is None:
        raise ApiError(404, "article_not_found", "Noticia no encontrada.")
    return q.article_detail(db, art, active_policy(db))


@router.get("/batches")
def batches(context_id: str = Depends(ctx_param), db: Session = Depends(get_db)):
    rows = db.scalars(select(ImportBatch).where(ImportBatch.context_id == context_id).order_by(ImportBatch.created_at.desc()))
    out = []
    for b in rows:
        if b.kind == "news":
            d = q.batch_progress(db, b)
            d["export"] = export_status(db, b)
            out.append(d)
        else:
            out.append({"id": b.id, "kind": b.kind, "file_name": b.file_name, "sheet_name": b.sheet_name, "row_count": b.row_count,
                        "created_at": q.iso(b.created_at), "diagnostics": b.diagnostics})
    return {"items": out}


@router.get("/batches/{batch_id}")
def batch(batch_id: str, db: Session = Depends(get_db)):
    b = db.get(ImportBatch, batch_id)
    if b is None or b.kind != "news":
        raise ApiError(404, "batch_not_found", "Lote no encontrado.")
    d = q.batch_progress(db, b)
    d["export"] = export_status(db, b)
    d["errors"] = [{"news_id": a.external_id, "article_id": a.id, "error_code": an.error_code, "error_message": an.error_message,
                    "retryable": an.retryable, "analysis_id": an.id}
                   for a in db.scalars(select(Article).where(Article.batch_id == b.id).order_by(Article.row_index))
                   if (an := q.current_analysis(db, a)) is not None and an.status == "error"]
    return d


@router.get("/batches/{batch_id}/export.xlsx")
def export(batch_id: str, db: Session = Depends(get_db)):
    b = db.get(ImportBatch, batch_id)
    if b is None or b.kind != "news":
        raise ApiError(404, "batch_not_found", "Lote no encontrado.")
    status = export_status(db, b)
    if not status["ready"]:
        raise ApiError(409, "export_blocked", "La exportación final está bloqueada: hay filas pendientes, con error o de fixture.", status)
    data = build_xlsx(db, b)
    name = f"supplier_risk_radar_{b.split or 'lote'}_{b.sheet_name}.xlsx"
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/batches/{batch_id}/export.csv")
def export_csv(batch_id: str, db: Session = Depends(get_db)):
    import csv
    import io
    from ..export import EXPORT_COLUMNS, batch_rows, csv_safe, join_ids
    b = db.get(ImportBatch, batch_id)
    if b is None or b.kind != "news":
        raise ApiError(404, "batch_not_found", "Lote no encontrado.")
    status = export_status(db, b)
    if not status["ready"]:
        raise ApiError(409, "export_blocked", "La exportación final está bloqueada: hay filas pendientes, con error o de fixture.", status)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(EXPORT_COLUMNS)
    for r in batch_rows(db, b):
        w.writerow([csv_safe(r["news_id"]), r["is_risk"], r["urgent"], csv_safe(join_ids(r["affected"]))])
    name = f"supplier_risk_radar_{b.split or 'lote'}_{b.sheet_name}.csv"
    return Response(content=buf.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/jobs/{job_id}")
def job(job_id: str, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if j is None:
        raise ApiError(404, "job_not_found", "Trabajo no encontrado.")
    out = {"id": j.id, "kind": j.kind, "status": j.status, "priority": j.priority, "attempts": j.attempts, "max_attempts": j.max_attempts,
           "next_attempt_at": q.iso(j.next_attempt_at), "error_code": j.error_code, "error_message": j.error_message,
           "created_at": q.iso(j.created_at), "started_at": q.iso(j.started_at), "finished_at": q.iso(j.finished_at), "batch_id": j.batch_id}
    if j.batch_id:
        b = db.get(ImportBatch, j.batch_id)
        if b:
            out["batch"] = q.batch_progress(db, b)
    return out


@router.get("/sources")
def sources(db: Session = Depends(get_db)):
    items = [q.source_dict(db, s) for s in db.scalars(select(Source).order_by(Source.name))]
    pending = db.scalar(select(func.count(Job.id)).where(Job.kind == "analyze_article", Job.priority == 100, Job.status.in_(("queued", "running")))) or 0
    deferred = db.scalar(select(func.count(Job.id)).where(Job.kind == "analyze_article", Job.status == "queued", Job.error_code == "budget_exceeded")) or 0
    sync_jobs = db.scalar(select(func.count(Job.id)).where(Job.kind == "sync_source", Job.status.in_(("queued", "running")))) or 0
    from ..rss import budget_used_today
    return {"items": items, "operational": sum(1 for s in items if s["healthy"]), "total": len(items),
            "analysis_queue": pending, "deferred_by_budget": deferred, "sync_in_progress": sync_jobs,
            "budget": {"used_today": budget_used_today(db), "daily": get_settings().rss_daily_analysis_budget}}


@router.get("/alerts")
def alerts(context_id: str | None = Query(None), after: int = Query(0, ge=0), status: str | None = None,
           batch_id: str | None = None, limit: int = Query(100, ge=1, le=200), db: Session = Depends(get_db)):
    stmt = select(Alert)
    if context_id:
        if context_id not in CONTEXTS:
            raise ApiError(400, "invalid_context", "Contexto desconocido.")
        stmt = stmt.where(Alert.context_id == context_id)
        batch_id = batch_param(db, context_id, batch_id)
        if batch_id:
            stmt = stmt.where(Alert.batch_id == batch_id)
    if after:
        stmt = stmt.where(Alert.seq > after)
    if status in ("unread", "acknowledged"):
        stmt = stmt.where(Alert.status == status)
    rows = list(db.scalars(stmt.order_by(Alert.seq.desc()).limit(limit)))
    items = [q.alert_dict(db, a) for a in rows]
    cursor = db.scalar(select(func.max(Alert.seq))) or 0
    unread_stmt = select(func.count(Alert.id)).where(Alert.status == "unread")
    if context_id:
        unread_stmt = unread_stmt.where(Alert.context_id == context_id)
    return {"items": items, "cursor": cursor, "unread": db.scalar(unread_stmt) or 0,
            "unread_by_context": {c: n for c, n in db.execute(select(Alert.context_id, func.count()).where(Alert.status == "unread").group_by(Alert.context_id)).all()}}


@router.get("/incidents/{incident_id}")
def incident(incident_id: str, db: Session = Depends(get_db)):
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise ApiError(404, "incident_not_found", "Incidente no encontrado.")
    clock, _ = q.context_clock(db, inc.context_id)
    return q.incident_summary(db, inc, clock)


def draft_dict(d: Draft) -> dict:
    return {"id": d.id, "kind": d.kind, "supplier_id": d.supplier_id, "target_supplier_id": d.target_supplier_id, "incident_id": d.incident_id,
            "article_id": d.article_id, "recipient": d.recipient, "subject": d.subject, "body": d.body, "generator": d.generator,
            "factual_context_hash": d.factual_context_hash, "edited": d.edited, "created_at": q.iso(d.created_at), "updated_at": q.iso(d.updated_at)}


@router.get("/materials")
def materials(context_id: str = Depends(ctx_param), batch_id: str | None = None, db: Session = Depends(get_db)):
    """Materiales con proveedor principal y alternativo, productos y riesgo activo de cada uno en el contexto/lote."""
    from ..models import Material, MaterialProduct
    batch_id = batch_param(db, context_id, batch_id)
    stmt = select(Incident).where(Incident.context_id == context_id, Incident.status != "resolved")
    if batch_id:
        stmt = stmt.where(Incident.batch_id == batch_id)
    active: dict[str, dict] = {}
    for inc in db.scalars(stmt):
        cur = active.setdefault(inc.supplier_id, {"priority": None, "urgent": False, "incidents": 0})
        cur["incidents"] += 1
        cur["urgent"] = cur["urgent"] or inc.urgent == "Y"
        if inc.current_priority is not None and (cur["priority"] is None or inc.current_priority > cur["priority"]):
            cur["priority"] = inc.current_priority
    names = {s.supplier_id: s for s in db.scalars(select(Supplier))}
    prods: dict[str, list[str]] = {}
    for mp in db.scalars(select(MaterialProduct)):
        prods.setdefault(mp.material_id, []).append(mp.product)

    def side(sid):
        if not sid:
            return None
        s = names.get(sid)
        return {"supplier_id": sid, "name": s.name if s else sid, "city": s.city if s else None, "country": s.country if s else None,
                "single_source": s.single_source if s else None, "inventory_days": s.inventory_days if s else None,
                "risk": active.get(sid)}

    items = []
    for m in db.scalars(select(Material).order_by(Material.row_index)):
        prim, alt = side(m.primary_supplier_id), side(m.alternate_supplier_id)
        prim_risk = bool(prim and prim["risk"])
        alt_risk = bool(alt and alt["risk"])
        if prim_risk and (alt is None or alt_risk):
            status = "sin_salida"  # principal afectado y sin alternativo libre
        elif prim_risk:
            status = "con_alternativo"
        elif alt_risk:
            status = "alternativo_afectado"
        else:
            status = "sin_incidentes"
        items.append({"material_id": m.material_id, "name": m.name, "category": m.category, "monthly_requirement": m.monthly_requirement,
                      "unit": m.unit, "products": sorted(prods.get(m.material_id, [])), "primary": prim, "alternate": alt, "status": status})
    order = {"sin_salida": 0, "con_alternativo": 1, "alternativo_afectado": 2, "sin_incidentes": 3}
    items.sort(key=lambda x: (order[x["status"]], -(((x["primary"] or {}).get("risk") or {}).get("priority") or 0), x["material_id"]))
    in_materials = {x[k]["supplier_id"] for x in items for k in ("primary", "alternate") if x[k]}
    return {"items": items, "products": sorted({p for v in prods.values() for p in v}),
            "suppliers_without_material": sorted(set(names) - in_materials)}


@router.get("/drafts")
def drafts_list(supplier_id: str | None = None, kind: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Draft).order_by(Draft.updated_at.desc())
    if supplier_id:
        stmt = stmt.where(Draft.supplier_id == supplier_id)
    if kind:
        stmt = stmt.where(Draft.kind == kind)
    names = {s.supplier_id: s.name for s in db.scalars(select(Supplier))}
    out = []
    for d in db.scalars(stmt.limit(300)):
        item = draft_dict(d)
        item.update({"supplier_name": names.get(d.supplier_id), "target_name": names.get(d.target_supplier_id), "language": d.language,
                     "plan_id": d.plan_id})
        out.append(item)
    return {"items": out, "total": len(out)}


@router.get("/drafts/{draft_id}")
def draft(draft_id: str, db: Session = Depends(get_db)):
    d = db.get(Draft, draft_id)
    if d is None:
        raise ApiError(404, "draft_not_found", "Borrador no encontrado.")
    out = draft_dict(d)
    out["evidence_changed"] = False
    if d.article_id and d.factual_context.get("article_version_id"):
        art = db.get(Article, d.article_id)
        out["evidence_changed"] = bool(art and art.current_version_id != d.factual_context["article_version_id"])
    return out
