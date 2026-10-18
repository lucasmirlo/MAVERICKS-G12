"""Consultas de lectura y serialización para la API pública. Nunca leen evaluation_labels."""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import utcnow
from .incidents import requires_update
from .models import (
    CONTEXT_EXERCISE,
    CONTEXT_RSS,
    Alert,
    Analysis,
    AppState,
    Article,
    ArticleVersion,
    ImportBatch,
    Incident,
    IncidentArticle,
    Job,
    Material,
    MaterialProduct,
    Source,
    Supplier,
    SupplierAssessment,
)
from .texts import explanation

CONTEXT_LABELS = {CONTEXT_EXERCISE: "Ejercicio", CONTEXT_RSS: "Noticias reales"}


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def get_state(db: Session, key: str, default=None):
    row = db.get(AppState, key)
    return row.value if row else default


def set_state(db: Session, key: str, value) -> None:
    row = db.get(AppState, key)
    if row is None:
        db.add(AppState(key=key, value=value))
    else:
        row.value = value
    db.commit()


def context_clock(db: Session, context_id: str, batch_id: str | None = None) -> tuple[datetime, str]:
    if context_id == CONTEXT_RSS:
        return utcnow(), "real"
    override = get_state(db, f"clock:{context_id}")
    if override:
        return datetime.fromisoformat(override), "presenter"
    stmt = (select(func.max(Article.published_at)).join(Analysis, Analysis.article_id == Article.id)
            .where(Article.context_id == context_id, Analysis.status.in_(("done", "review"))))
    if batch_id:
        stmt = stmt.where(Article.batch_id == batch_id)
    latest = db.scalar(stmt)
    return (latest or utcnow()), ("logical" if latest else "real")


# ---------------------------------------------------------------- proveedores

def supplier_brief(s: Supplier) -> dict:
    return {"supplier_id": s.supplier_id, "name": s.name, "country": s.country, "city": s.city, "category": s.category,
            "material": s.material, "criticality": s.criticality, "single_source": s.single_source, "alternate_id": s.alternate_id}


def supplier_full(s: Supplier, policy: dict) -> dict:
    applicability = "not_applicable" if s.category in policy["buffer_not_applicable_categories"] else "physical"
    return {**supplier_brief(s), "annual_spend_eur": s.annual_spend_eur, "share_category_pct": s.share_category_pct,
            "lead_days": s.lead_days, "inventory_days": s.inventory_days, "quality_score": s.quality_score,
            "inventory_applicability": applicability, "data_issues": s.data_issues or [],
            "cover_below_lead": (s.inventory_days < s.lead_days) if (s.inventory_days is not None and s.lead_days) else None}


def products_by_supplier(db: Session) -> dict[str, dict]:
    mats = list(db.scalars(select(Material)))
    prods: dict[str, list[str]] = {}
    for mp in db.scalars(select(MaterialProduct)):
        prods.setdefault(mp.material_id, []).append(mp.product)
    out: dict[str, dict] = {}
    for m in mats:
        for sid, role in ((m.primary_supplier_id, "primary"), (m.alternate_supplier_id, "alternate")):
            if not sid:
                continue
            entry = out.setdefault(sid, {"materials": [], "products": set()})
            entry["materials"].append({"material_id": m.material_id, "name": m.name, "role": role, "category": m.category,
                                       "monthly_requirement": m.monthly_requirement, "unit": m.unit,
                                       "primary_supplier_id": m.primary_supplier_id, "alternate_supplier_id": m.alternate_supplier_id,
                                       "products": sorted(prods.get(m.material_id, []))})
            entry["products"].update(prods.get(m.material_id, []))
    for v in out.values():
        v["products"] = sorted(v["products"])
    return out


DEADLINE_ORDER = {"hoy": 0, "esta_semana": 1, "proximo_informe": 2}


def attention_desk(db: Session, context_id: str, batch_id: str | None = None, limit: int = 6) -> list[dict]:
    """Mesa de atención: incidentes activos ordenados por urgencia y prioridad, con la siguiente acción de su plan."""
    from .models import ActionPlan
    stmt = select(Incident).where(Incident.context_id == context_id, Incident.status != "resolved")
    if batch_id:
        stmt = stmt.where(Incident.batch_id == batch_id)
    incs = sorted(db.scalars(stmt), key=lambda i: (i.urgent != "Y", -(i.current_priority or 0), i.supplier_id))[:limit]
    out = []
    for inc in incs:
        s = db.get(Supplier, inc.supplier_id)
        plan = db.scalar(select(ActionPlan).where(ActionPlan.incident_id == inc.id))
        actions = sorted(plan.actions if plan else [], key=lambda a: (DEADLINE_ORDER.get(a["deadline"], 9), a["code"] == "monitor"))
        a = db.scalar(select(SupplierAssessment).where(SupplierAssessment.incident_id == inc.id)
                      .order_by(SupplierAssessment.priority.desc().nulls_last()).limit(1))
        link = db.scalar(select(IncidentArticle).where(IncidentArticle.incident_id == inc.id).order_by(IncidentArticle.published_at.desc()).limit(1))
        art = db.get(Article, link.article_id) if link else None
        ver = db.get(ArticleVersion, art.current_version_id) if art else None
        facts = plan.facts if plan else {}
        out.append({
            "incident_id": inc.id, "supplier_id": s.supplier_id, "supplier_name": s.name, "material": s.material,
            "city": s.city, "country": s.country, "criticality": s.criticality, "single_source": s.single_source,
            "priority": inc.current_priority, "priority_band": inc.priority_band, "urgent": inc.urgent,
            "event_type": inc.event_type, "needs_review": inc.needs_review, "decision_source": a.decision_source if a else None,
            "headline": ver.headline if ver else None, "article_id": art.id if art else None,
            "published_at": iso(art.published_at) if art else None,
            "next_actions": [{"code": x["code"], "label": x["label"], "deadline": x["deadline"]} for x in actions[:2]],
            "stock_margin": (facts.get("stock") or {}).get("margen_dias"), "products": facts.get("productos"),
            "summary": (plan.summary_llm if plan and plan.summary_source == "llm" else plan.summary_template) if plan else None,
            "summary_source": plan.summary_source if plan else None,
        })
    return out


def plan_dict(db: Session, incident_id: str) -> dict | None:
    from .actions import DEADLINE_LABELS
    from .models import ActionPlan, Draft
    plan = db.scalar(select(ActionPlan).where(ActionPlan.incident_id == incident_id))
    if plan is None:
        return None
    drafts = [{"id": d.id, "kind": d.kind, "language": d.language, "subject": d.subject, "edited": d.edited,
               "target_supplier_id": d.target_supplier_id}
              for d in db.scalars(select(Draft).where(Draft.plan_id == plan.id).order_by(Draft.kind.desc()))]
    return {"id": plan.id, "rules_version": plan.rules_version,
            "actions": [{**a, "deadline_label": DEADLINE_LABELS.get(a["deadline"], a["deadline"])} for a in plan.actions],
            "facts": plan.facts, "summary": plan.summary_llm if plan.summary_source == "llm" else plan.summary_template,
            "summary_source": plan.summary_source, "summary_error": plan.summary_error, "drafts": drafts,
            "updated_at": iso(plan.updated_at)}


def incident_summary(db: Session, inc: Incident, clock: datetime, article_cache: dict | None = None) -> dict:
    trigger = None
    links = list(db.scalars(select(IncidentArticle).where(IncidentArticle.incident_id == inc.id).order_by(IncidentArticle.published_at)))
    latest_link = next((l for l in reversed(links) if l.role in ("trigger", "update")), None)
    if latest_link:
        art = (article_cache or {}).get(latest_link.article_id) or db.get(Article, latest_link.article_id)
        ver = db.get(ArticleVersion, art.current_version_id) if art else None
        trigger = {"article_id": art.id, "headline": ver.headline if ver else None, "source_name": art.source_name,
                   "published_at": iso(art.published_at), "url": art.url, "news_id": art.external_id} if art else None
    return {"id": inc.id, "context_id": inc.context_id, "batch_id": inc.batch_id, "supplier_id": inc.supplier_id, "event_type": inc.event_type, "status": inc.status,
            "urgent": inc.urgent, "current_priority": inc.current_priority if inc.status != "resolved" else 0.0,
            "historical_priority": inc.peak_priority, "priority_band": inc.priority_band, "needs_review": inc.needs_review,
            "review_reasons": inc.review_reasons, "sound_eligible": inc.sound_eligible, "opened_at": iso(inc.opened_at),
            "last_evidence_at": iso(inc.last_evidence_at), "resolved_at": iso(inc.resolved_at), "resolution": inc.resolution,
            "revision": inc.revision, "requires_update": requires_update(inc, clock), "article_count": len(links),
            "plan": plan_dict(db, inc.id),
            "latest_article": trigger, "history": inc.history or []}


def ranking(db: Session, context_id: str, batch_id: str | None = None) -> list[dict]:
    from .policy import active_policy
    policy = active_policy(db)
    suppliers = list(db.scalars(select(Supplier).order_by(Supplier.supplier_id)))
    stmt = select(Incident).where(Incident.context_id == context_id)
    if batch_id:
        stmt = stmt.where(Incident.batch_id == batch_id)
    incs = list(db.scalars(stmt))
    clock, _ = context_clock(db, context_id, batch_id)
    prod = products_by_supplier(db)
    names = {s.supplier_id: s.name for s in suppliers}
    rows = []
    for s in suppliers:
        mine = [i for i in incs if i.supplier_id == s.supplier_id]
        active = [i for i in mine if i.status != "resolved"]
        priorities = [i.current_priority for i in active if i.current_priority is not None]
        top = max(active, key=lambda i: (i.current_priority if i.current_priority is not None else -1), default=None)
        reason = None
        if top:
            link = db.scalar(select(IncidentArticle).where(IncidentArticle.incident_id == top.id, IncidentArticle.role.in_(("trigger", "update")))
                             .order_by(IncidentArticle.published_at.desc()).limit(1))
            if link:
                art = db.get(Article, link.article_id)
                ver = db.get(ArticleVersion, art.current_version_id)
                reason = {"event_type": top.event_type, "headline": ver.headline, "article_id": art.id, "published_at": iso(art.published_at)}
        p = prod.get(s.supplier_id)
        rows.append({
            **supplier_brief(s), "alternate_name": names.get(s.alternate_id) if s.alternate_id else None,
            "lead_days": s.lead_days, "inventory_days": s.inventory_days,
            "priority": max(priorities) if priorities else (None if active else 0.0),
            "priority_pending": bool(active) and not priorities,
            "priority_band": top.priority_band if top else None,
            "urgent": "Y" if any(i.urgent == "Y" for i in active) else "N",
            "needs_review": any(i.needs_review for i in active),
            "requires_update": any(requires_update(i, clock) for i in active),
            "active_incidents": len(active), "resolved_incidents": sum(1 for i in mine if i.status == "resolved"),
            "historical_priority": max((i.peak_priority or 0 for i in mine), default=None) if mine else None,
            "last_evidence_at": iso(max((i.last_evidence_at for i in mine if i.last_evidence_at), default=None)),
            "reason": reason, "products": p["products"] if p else [], "products_mapped": bool(p and p["products"]),
            **dependency_index(s, policy),
        })
    # Orden estable: prioridad descendente; incidentes sin prioridad calculable (revisión) justo después de los puntuados.
    # Con incidentes activos manda la prioridad; sin ellos, el índice de dependencia E.
    rows.sort(key=lambda r: (-(r["priority"] if r["active_incidents"] and r["priority"] is not None else 0.01 if r["priority_pending"] else -1),
                             -r["active_incidents"], -(r["dependency_index"] or 0), r["supplier_id"]))
    return rows


def dependency_index(s: Supplier, policy: dict) -> dict:
    """E (0–1) del proveedor sin evento: media ponderada de C, U, B (cobertura frente a lead time) y G."""
    from . import scoring
    try:
        r = scoring.priority(policy, is_risk=False, severity=None, criticality=s.criticality, single_source=s.single_source,
                             share_category_pct=s.share_category_pct, inventory_days=s.inventory_days, lead_days=s.lead_days,
                             inventory_applicability=scoring.inventory_applicability(policy, s.category))
    except ValueError:
        return {"dependency_index": None, "dependency_factors": {}, "dependency_weights": policy["weights"]}
    return {"dependency_index": r["exposure"], "dependency_factors": r["factors"], "dependency_contributions": r["contributions"],
            "dependency_weights": policy["weights"]}


# ---------------------------------------------------------------- artículos

def current_analysis(db: Session, article: Article) -> Analysis | None:
    return db.scalar(select(Analysis).where(Analysis.article_version_id == article.current_version_id)
                     .order_by(Analysis.created_at.desc(), Analysis.seq.desc()).limit(1))


def relevance(an: Analysis | None, job: Job | None = None) -> str:
    if an is None or an.status in ("pending", "running"):
        if job and job.error_code == "budget_exceeded" and job.status == "queued":
            return "deferred"
        return "pending"
    if an.status == "error":
        return "error"
    if an.is_risk == "Y" and an.urgent == "Y":
        return "urgent"
    if an.is_risk == "Y":
        return "risk"
    if an.affected_supplier_ids:
        if an.event_type == "positive_news" or any(a.impact_status == "positive" for a in an.assessments):
            return "positive"
        if any(a.is_recovery for a in an.assessments):
            return "recovery"
        return "linked"
    return "unlinked"


def article_brief(db: Session, art: Article, an: Analysis | None = None, version: ArticleVersion | None = None) -> dict:
    version = version or db.get(ArticleVersion, art.current_version_id)
    an = an if an is not None else current_analysis(db, art)
    job = None
    if an is None:
        job = db.scalar(select(Job).where(Job.idempotency_key == f"analyze:{art.current_version_id}"))
    return {"id": art.id, "context_id": art.context_id, "origin": art.origin, "news_id": art.external_id if art.origin == "excel" else None,
            "batch_id": art.batch_id, "row_index": art.row_index, "source_id": art.source_id, "source_name": art.source_name,
            "url": art.url, "published_at": iso(art.published_at), "published_raw": art.published_raw,
            "first_seen_at": iso(art.first_seen_at), "headline": version.headline if version else "", "summary": version.summary if version else "",
            "version": version.version if version else None, "language": art.language,
            "relevance": relevance(an, job), "analysis_status": an.status if an else ("deferred" if job and job.error_code == "budget_exceeded" else "pending"),
            "engine_mode": an.engine_mode if an else None, "is_risk": an.is_risk if an else None, "urgent": an.urgent if an else None,
            "affected_supplier_ids": an.affected_supplier_ids if an else [], "event_type": an.event_type if an else None,
            "needs_review": bool(an and an.review_reasons), "cached": bool(an and an.cached),
            "llm_pending": bool(an and any(x.llm_status == "pendiente" for x in an.assessments)),
            "decision_sources": sorted({x.decision_source for x in an.assessments if x.accepted and x.decision_source}) if an else [],
            "error_code": an.error_code if an else (job.error_code if job else None)}


def assessment_dict(a: SupplierAssessment, evidence: list[dict]) -> dict:
    by_id = {e["id"]: e for e in evidence}
    return {"id": a.id, "supplier_id": a.supplier_id, "accepted": a.accepted, "p_link": a.p_link, "p_risk": a.p_risk, "p_urgent": a.p_urgent,
            "is_risk": a.is_risk, "urgent": a.urgent, "severity": a.severity, "severity_confidence": a.severity_confidence,
            "impact_status": a.impact_status, "impact_confidence": a.impact_confidence, "priority": a.priority,
            "active_priority": a.active_priority, "priority_band": a.priority_band, "exposure": a.exposure,
            "factor_values": a.factor_values, "contributions": a.contributions, "needs_review": a.needs_review,
            "review_reasons": a.review_reasons, "evidence": [by_id[e] for e in a.evidence_ids if e in by_id],
            "duration_days": a.duration_days, "duration_is_lower_bound": a.duration_is_lower_bound,
            "sound_eligible": a.sound_eligible, "is_recovery": a.is_recovery, "policy_version": a.policy_version,
            "link_basis": a.link_basis, "decision_source": a.decision_source, "urgent_rule": a.urgent_rule,
            "jev_urgent": a.jev_urgent, "doubtful": a.doubtful, "doubt_reasons": a.doubt_reasons or [],
            "llm_status": a.llm_status, "llm_decision": a.llm_decision, "alternate_affected": a.alternate_affected,
            "incident_id": a.incident_id}


def explanation_context(db: Session, a: SupplierAssessment, an: Analysis, art: Article, version: ArticleVersion, policy: dict) -> dict:
    s = db.get(Supplier, a.supplier_id)
    alt = db.get(Supplier, s.alternate_id) if s and s.alternate_id else None
    prod = products_by_supplier(db).get(a.supplier_id)
    by_id = {e["id"]: e for e in an.evidence}
    missing = []
    if s and s.category not in policy["buffer_not_applicable_categories"]:
        if s.inventory_days is None:
            missing.append("inventario")
        if s.lead_days is None:
            missing.append("lead time")
    return {"supplier_id": a.supplier_id, "supplier_name": s.name if s else a.supplier_id, "material": s.material if s else None,
            "country": s.country if s else None, "city": s.city if s else None, "article_headline": version.headline,
            "article_url": art.url, "published_at": (art.published_at.date().isoformat() if art.published_at else art.published_raw),
            "evidence_quotes": [by_id[e]["text"] for e in a.evidence_ids if e in by_id], "event_type": an.event_type,
            "impact_status": a.impact_status, "is_risk": a.is_risk, "urgent": a.urgent, "severity": a.severity, "priority": a.priority,
            "factor_values": a.factor_values, "inventory_days": s.inventory_days if s else None, "lead_days": s.lead_days if s else None,
            "duration_days": a.duration_days, "duration_is_lower_bound": a.duration_is_lower_bound,
            "alternate_supplier_name": alt.name if alt else None, "alternate_supplier_id": alt.supplier_id if alt else None,
            "alternate_approved": bool(alt), "products_known": prod["products"] if prod else [], "missing_fields": missing,
            "review_reasons": a.review_reasons, "potential_exposure": art.context_id == CONTEXT_RSS}


def article_detail(db: Session, art: Article, policy: dict) -> dict:
    version = db.get(ArticleVersion, art.current_version_id)
    an = current_analysis(db, art)
    out = article_brief(db, art, an, version)
    out["versions"] = [{"version": v.version, "fetched_at": iso(v.fetched_at), "content_hash": v.content_hash[:12]} for v in art.versions]
    out["geo"] = art.geo
    if an:
        names = {s.supplier_id: s.name for s in db.scalars(select(Supplier))}
        out["analysis"] = {
            "id": an.id, "status": an.status, "engine_mode": an.engine_mode, "model_id": an.model_id, "requested_model": an.requested_model,
            "question_version": an.question_version, "policy_version": an.policy_version, "cached": an.cached,
            "event_type": an.event_type, "event_type_confidence": an.event_type_confidence, "event_state": an.event_state,
            "review_reasons": an.review_reasons, "error_code": an.error_code, "error_message": an.error_message, "retryable": an.retryable,
            "duration_ms": an.duration_ms, "finished_at": iso(an.finished_at), "evidence": an.evidence, "manual_decision": an.manual_decision,
            "candidates_considered": sorted([{"supplier_id": k, "name": names.get(k), "p_link": v} for k, v in (an.link_scores or {}).items() if v >= 0.2],
                                            key=lambda x: -x["p_link"]),
            "assessments": [],
        }
        for a in an.assessments:
            d = assessment_dict(a, an.evidence)
            d["supplier_name"] = names.get(a.supplier_id)
            d["explanation"] = explanation(explanation_context(db, a, an, art, version, policy))
            out["analysis"]["assessments"].append(d)
    return out


# ---------------------------------------------------------------- lotes y fuentes

def batch_progress(db: Session, batch: ImportBatch) -> dict:
    total = batch.row_count
    articles = list(db.scalars(select(Article).where(Article.batch_id == batch.id)))
    counts = {"done": 0, "review": 0, "error": 0, "running": 0, "pending": 0, "not_started": 0}
    durations = []
    llm_stats = {"doubtful_pairs": 0, "pending": 0, "decided": 0, "low_confidence": 0, "no_second_opinion": 0, "latencies_ms": [],
                 "sources": {}}
    for art in articles:
        an = current_analysis(db, art)
        if an is not None:
            for x in an.assessments:
                if x.accepted or x.doubtful:
                    llm_stats["sources"][x.decision_source or "-"] = llm_stats["sources"].get(x.decision_source or "-", 0) + 1
                if not x.doubtful:
                    continue
                llm_stats["doubtful_pairs"] += 1
                key = {"pendiente": "pending", "hecha": "decided", "baja_confianza": "low_confidence"}.get(x.llm_status, "no_second_opinion")
                llm_stats[key] += 1
                lat = ((x.llm_decision or {}).get("meta") or {}).get("latency_ms")
                if lat and x.llm_status in ("hecha", "baja_confianza"):
                    llm_stats["latencies_ms"].append(lat)
        if an is None:
            counts["not_started"] += 1
        else:
            counts[an.status if an.status in counts else "pending"] += 1
            if an.status in ("done", "review") and an.duration_ms and not an.cached:
                durations.append(an.duration_ms)
    jobs = db.execute(select(Job.status, func.count()).where(Job.batch_id == batch.id).group_by(Job.status)).all()
    elapsed = None
    queue_seconds = processing_seconds = None
    if batch.analysis_requested_at:
        end = batch.analysis_completed_at or utcnow()
        elapsed = (end - batch.analysis_requested_at).total_seconds()
        first_start = db.scalar(select(func.min(Job.started_at)).where(Job.batch_id == batch.id, Job.kind == "analyze_article",
                                                                        Job.started_at >= batch.analysis_requested_at))
        if first_start:
            queue_seconds = max(0.0, (first_start - batch.analysis_requested_at).total_seconds())
            processing_seconds = max(0.0, (end - first_start).total_seconds())
    return {"id": batch.id, "kind": batch.kind, "split": batch.split, "context_id": batch.context_id, "file_name": batch.file_name,
            "sheet_name": batch.sheet_name, "file_sha256": batch.file_sha256[:12], "row_count": total, "has_labels": batch.has_labels,
            "logical_date": iso(batch.logical_date), "created_at": iso(batch.created_at), "diagnostics": batch.diagnostics,
            "analysis_requested_at": iso(batch.analysis_requested_at), "analysis_completed_at": iso(batch.analysis_completed_at),
            "elapsed_seconds": elapsed, "queue_seconds": queue_seconds, "processing_seconds": processing_seconds, "counts": counts, "jobs": {s: n for s, n in jobs},
            "completed": counts["done"] + counts["review"], "latency": latency(durations),
            "llm": {**{k: v for k, v in llm_stats.items() if k != "latencies_ms"}, "n_calls": len(llm_stats["latencies_ms"]),
                    "mean_latency_ms": int(sum(llm_stats["latencies_ms"]) / len(llm_stats["latencies_ms"])) if llm_stats["latencies_ms"] else None}}


def latency(durations: list[int]) -> dict:
    if not durations:
        return {"n": 0, "p50_ms": None, "p95_ms": None}
    ds = sorted(durations)
    p95 = ds[min(len(ds) - 1, int(round(0.95 * (len(ds) - 1))))]
    return {"n": len(ds), "p50_ms": int(statistics.median(ds)), "p95_ms": p95}


def source_dict(db: Session, s: Source) -> dict:
    poll = s.poll_seconds or get_settings().rss_poll_seconds
    healthy = s.last_outcome in ("ok", "not_modified") and s.last_success_at is not None and (utcnow() - s.last_success_at) < timedelta(seconds=poll * 3)
    since = utcnow() - timedelta(hours=24)
    count = db.scalar(select(func.count(Article.id)).where(Article.source_id == s.id)) or 0
    recent = db.scalar(select(func.count(Article.id)).where(Article.source_id == s.id, Article.first_seen_at >= since)) or 0
    return {"id": s.id, "name": s.name, "url": s.url, "language": s.language, "topic": s.topic, "enabled": s.enabled, "poll_seconds": poll,
            "last_attempt_at": iso(s.last_attempt_at), "last_success_at": iso(s.last_success_at), "last_status": s.last_status,
            "last_outcome": s.last_outcome, "last_item_count": s.last_item_count, "last_new_count": s.last_new_count,
            "last_duration_ms": s.last_duration_ms, "error_count": s.error_count, "consecutive_errors": s.consecutive_errors,
            "error_message": s.error_message, "healthy": healthy, "syncing": bool(s.lease_until and s.lease_until > utcnow()),
            "articles_total": count, "articles_24h": recent, "never_polled": s.last_attempt_at is None}


def alert_dict(db: Session, al: Alert) -> dict:
    inc = db.get(Incident, al.incident_id)
    s = db.get(Supplier, al.supplier_id)
    art = db.get(Article, al.article_id) if al.article_id else None
    ver = db.get(ArticleVersion, art.current_version_id) if art else None
    an = current_analysis(db, art) if art else None
    a = next((x for x in an.assessments if x.supplier_id == al.supplier_id), None) if an else None
    return {"id": al.id, "seq": al.seq, "incident_id": al.incident_id, "context_id": al.context_id, "batch_id": al.batch_id,
            "batch_split": (db.get(ImportBatch, al.batch_id).split if al.batch_id else None), "supplier_id": al.supplier_id,
            "supplier_name": s.name if s else al.supplier_id, "revision": al.revision, "kind": al.kind, "priority": al.priority,
            "urgent": al.urgent, "sound_eligible": al.sound_eligible and bool(inc and inc.status == "active"),
            "status": al.status, "incident_status": inc.status if inc else None, "created_at": iso(al.created_at),
            "acknowledged_at": iso(al.acknowledged_at), "article_id": al.article_id, "headline": ver.headline if ver else None,
            "source_name": art.source_name if art else None, "published_at": iso(art.published_at) if art else None,
            "event_type": inc.event_type if inc else None, "needs_review": inc.needs_review if inc else False,
            "p_link": a.p_link if a else None, "p_risk": a.p_risk if a else None, "p_urgent": a.p_urgent if a else None,
            "priority_band": a.priority_band if a else None,
            "decision_source": a.decision_source if a else None, "llm_decision": a.llm_decision if a else None,
            "plan": plan_dict(db, al.incident_id)}
