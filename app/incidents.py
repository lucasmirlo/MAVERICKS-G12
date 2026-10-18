"""Incidentes por proveedor y evento, reconstruidos de forma determinista y en orden cronológico.

- Actualizaciones del mismo evento (mismo proveedor, tipo y ventana temporal) se agrupan: no se suman scores.
- Una recuperación solo resuelve un incidente compatible anterior; si hay varios candidatos, crea revisión.
- Un artículo antiguo recibido tarde se ordena por su fecha y no reabre un incidente resuelto después.
- Los IDs de incidente son deterministas, así que reconocimientos de alertas y resoluciones manuales sobreviven.
- En Ejercicio cada lote Excel es independiente: un incidente nunca agrupa noticias de lotes distintos, para que
  la evaluación y el ranking de cada archivo no se mezclen. En RSS batch_id es None.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from .db import utcnow
from .models import Alert, Analysis, Article, Incident, IncidentArticle, SupplierAssessment

NAMESPACE = uuid.UUID("6f1d2c4e-8a8b-4c55-9d7e-3b1f7d0a9e21")
GROUP_WINDOW = timedelta(days=14)
STALE_AFTER = timedelta(days=7)
BAND_RANK = {None: -1, "low": 0, "medium": 1, "high": 2, "critical": 3}
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def current_analyses(db: Session, context_id: str) -> list[Analysis]:
    """Último análisis terminado (done/review) de la versión vigente de cada artículo."""
    rows = db.execute(
        select(Analysis, Article)
        .join(Article, Article.id == Analysis.article_id)
        .where(Analysis.context_id == context_id, Analysis.status.in_(("done", "review")),
               Analysis.article_version_id == Article.current_version_id)
        .order_by(Analysis.article_id, Analysis.finished_at.desc())
    ).all()
    seen, out = set(), []
    for analysis, _article in rows:
        if analysis.article_id not in seen:
            seen.add(analysis.article_id)
            out.append(analysis)
    return out


def _incident_id(context_id: str, supplier_id: str, article_id: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{context_id}|{supplier_id}|{article_id}"))


def _alert_kind(inc: dict) -> str | None:
    if inc["status"] == "resolved":
        return None
    if inc["urgent"] == "Y":
        return "urgent"
    if inc["band"] == "critical":
        return "discrepancy"  # prioridad crítica sin Urgent=Y: tarea de revisión
    if inc["band"] == "high":
        return "high_priority"
    return None


def rebuild_context(db: Session, context_id: str) -> dict:
    """Reconstruye incidentes y alertas de un contexto. Serializado con un advisory lock por contexto."""
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"incidents:{context_id}"})
    analyses = current_analyses(db, context_id)
    article_ids = [a.article_id for a in analyses]
    articles = {a.id: a for a in db.scalars(select(Article).where(Article.id.in_(article_ids)))} if article_ids else {}
    items = []
    for analysis in analyses:
        art = articles[analysis.article_id]
        for a in analysis.assessments:
            if a.accepted:
                items.append((art.published_at or art.first_seen_at, art.row_index or 0, art.first_seen_at, art, analysis, a))
    items.sort(key=lambda x: (x[0], x[1], x[2]))

    existing = {i.id: i for i in db.scalars(select(Incident).where(Incident.context_id == context_id))}
    incidents: dict[str, dict] = {}
    by_supplier: dict[str, list[str]] = {}
    links: list[dict] = []
    orphan_recoveries = 0

    for date, _row, _seen, art, analysis, a in items:
        sid = a.supplier_id
        scope = (art.batch_id, sid)
        mine = [incidents[i] for i in by_supplier.get(scope, [])]
        if a.is_recovery:
            open_before = [i for i in mine if i["status"] != "resolved" and i["opened_at"] <= date]
            same_type = [i for i in open_before if i["event_type"] == analysis.event_type]
            pool = same_type or open_before
            if len(pool) == 1:
                inc = pool[0]
                inc["status"] = "resolved"
                inc["resolved_at"] = date
                inc["current_priority"] = 0.0
                inc["band"] = "low"
                inc["urgent"] = "N"
                inc["sound_eligible"] = False
                inc["resolution"] = {"manual": False, "article_id": art.id, "at": date.isoformat()}
                inc["history"].append(_hist(date, art, a, "recovery", "resolved"))
                links.append(_link(inc, art, a, "recovery", date))
            elif len(pool) > 1:
                for inc in pool:
                    if "recovery_ambiguous" not in inc["review_reasons"]:
                        inc["review_reasons"].append("recovery_ambiguous")
                    inc["needs_review"] = True
                    inc["history"].append(_hist(date, art, a, "recovery_candidate", inc["status"]))
                    links.append(_link(inc, art, a, "recovery_candidate", date))
            else:
                orphan_recoveries += 1
            continue
        if a.is_risk != "Y":
            continue
        matches = [i for i in mine if i["event_type"] == analysis.event_type and abs(date - i["last_evidence_at"]) <= GROUP_WINDOW]
        open_match = next((i for i in reversed(matches) if i["status"] != "resolved"), None)
        resolved_match = next((i for i in reversed(matches) if i["status"] == "resolved"), None)
        if open_match is None and resolved_match is not None and date <= resolved_match["resolved_at"]:
            # Evidencia anterior a la recuperación, recibida tarde: historial sin reabrir.
            resolved_match["history"].append(_hist(date, art, a, "historical", "resolved"))
            resolved_match["peak_priority"] = max(resolved_match["peak_priority"] or 0, a.priority or 0)
            links.append(_link(resolved_match, art, a, "historical", date))
            continue
        status = "monitoring" if a.impact_status == "monitoring" else "active"
        if open_match is None:
            iid = _incident_id(context_id, sid, art.id)
            inc = {
                "id": iid, "supplier_id": sid, "batch_id": art.batch_id, "event_type": analysis.event_type, "status": status,
                "urgent": a.urgent, "current_priority": a.priority, "peak_priority": a.priority,
                "band": a.priority_band, "needs_review": a.needs_review, "review_reasons": list(a.review_reasons),
                "sound_eligible": a.sound_eligible, "opened_at": date, "last_evidence_at": date, "resolved_at": None,
                "resolution": None, "revision": 1, "history": [_hist(date, art, a, "trigger", status)],
                "trigger_article_id": art.id, "trigger_assessment_id": a.id, "revision_assessments": {1: a},
            }
            incidents[iid] = inc
            by_supplier.setdefault(scope, []).append(iid)
            links.append(_link(inc, art, a, "trigger", date))
            continue
        inc = open_match
        escalated = (a.urgent == "Y" and inc["urgent"] != "Y") or BAND_RANK.get(a.priority_band, -1) > BAND_RANK.get(inc["band"], -1)
        inc["status"] = status
        inc["urgent"] = a.urgent
        inc["current_priority"] = a.priority
        inc["peak_priority"] = max(inc["peak_priority"] or 0, a.priority or 0) if (inc["peak_priority"] is not None or a.priority is not None) else None
        inc["band"] = a.priority_band
        inc["needs_review"] = a.needs_review or "recovery_ambiguous" in inc["review_reasons"]
        inc["review_reasons"] = list(dict.fromkeys(a.review_reasons + [r for r in inc["review_reasons"] if r == "recovery_ambiguous"]))
        inc["sound_eligible"] = a.sound_eligible
        inc["last_evidence_at"] = max(inc["last_evidence_at"], date)
        if escalated:
            inc["revision"] += 1
            inc["revision_assessments"][inc["revision"]] = a
        inc["history"].append(_hist(date, art, a, "update", status))
        links.append(_link(inc, art, a, "update", date))

    # Resoluciones manuales registradas siguen vigentes si no hay evidencia posterior.
    for iid, inc in incidents.items():
        old = existing.get(iid)
        if old and old.resolution and old.resolution.get("manual") and inc["status"] != "resolved":
            cutoff = datetime.fromisoformat(old.resolution["evidence_cutoff"])
            if inc["last_evidence_at"] <= cutoff:
                inc["status"] = "resolved"
                inc["resolved_at"] = old.resolved_at
                inc["resolution"] = old.resolution
                inc["current_priority"] = 0.0
                inc["urgent"] = "N"
                inc["sound_eligible"] = False
                inc["history"].append({"at": old.resolution["at"], "role": "manual_resolution", "status": "resolved",
                                       "note": old.resolution.get("note")})

    # Persistencia
    db.execute(delete(IncidentArticle).where(IncidentArticle.incident_id.in_(list(existing.keys()) or [""])))
    stale_ids = [i for i in existing if i not in incidents]
    if stale_ids:
        db.execute(delete(Incident).where(Incident.id.in_(stale_ids)))
    db.flush()
    supplier_location = {}
    for iid, inc in incidents.items():
        row = existing.get(iid) or Incident(id=iid, context_id=context_id, supplier_id=inc["supplier_id"])
        if iid not in existing:
            db.add(row)
        row.batch_id = inc["batch_id"]
        row.event_type = inc["event_type"]
        row.status = inc["status"]
        row.urgent = inc["urgent"]
        row.current_priority = inc["current_priority"]
        row.peak_priority = inc["peak_priority"]
        row.priority_band = inc["band"]
        row.needs_review = inc["needs_review"]
        row.review_reasons = inc["review_reasons"]
        row.sound_eligible = inc["sound_eligible"] and inc["status"] == "active"
        row.opened_at = inc["opened_at"]
        row.last_evidence_at = inc["last_evidence_at"]
        row.resolved_at = inc["resolved_at"]
        row.resolution = inc["resolution"]
        row.revision = inc["revision"]
        row.history = [{**h, "at": h["at"] if isinstance(h["at"], str) else h["at"].isoformat()} for h in inc["history"]]
        supplier_location[iid] = inc["supplier_id"]
    db.flush()
    seen_links = set()
    assessment_incident: dict[str, str] = {}
    for link in links:
        key = (link["incident_id"], link["article_id"])
        assessment_incident[link["assessment_id"]] = link["incident_id"]
        if key in seen_links:
            continue
        seen_links.add(key)
        db.add(IncidentArticle(**link))
    # Las evaluaciones de análisis antiguos (otra versión de preguntas, política o modo) dejan de apuntar a incidentes.
    current_ids = [an.id for an in analyses]
    stale = select(SupplierAssessment).where(SupplierAssessment.context_id == context_id, SupplierAssessment.incident_id.is_not(None))
    if current_ids:
        stale = stale.where(SupplierAssessment.analysis_id.not_in(current_ids))
    for old in db.scalars(stale):
        old.incident_id = None
    for analysis in analyses:
        for a in analysis.assessments:
            a.incident_id = assessment_incident.get(a.id)

    # Alertas: una por revisión elegible; las existentes conservan su estado de lectura.
    existing_alerts = {(al.incident_id, al.revision): al for al in db.scalars(select(Alert).where(Alert.context_id == context_id))}
    wanted = set()
    for iid, inc in incidents.items():
        for rev, a in inc["revision_assessments"].items():
            snapshot = {"status": "active" if rev <= inc["revision"] else inc["status"], "urgent": a.urgent, "band": a.priority_band}
            kind = _alert_kind(snapshot)
            if kind is None:
                continue
            wanted.add((iid, rev))
            al = existing_alerts.get((iid, rev))
            sound = bool(a.sound_eligible and a.urgent == "Y")
            if al is None:
                db.add(Alert(incident_id=iid, context_id=context_id, batch_id=inc["batch_id"], supplier_id=inc["supplier_id"], article_id=a.article_id,
                             revision=rev, kind=kind, priority=a.priority, urgent=a.urgent, sound_eligible=sound))
            else:
                al.kind, al.priority, al.urgent, al.sound_eligible, al.article_id = kind, a.priority, a.urgent, sound, a.article_id
                al.batch_id = inc["batch_id"]
    for key, al in existing_alerts.items():
        if key not in wanted and key[0] in incidents:
            db.delete(al)
    db.commit()
    # Planes de acción de los incidentes activos (reglas + hechos de la base de datos).
    from .actions import sync_plans
    from .policy import active_policy
    plans_changed = sync_plans(db, context_id, active_policy(db))
    return {"incidents": len(incidents), "orphan_recoveries": orphan_recoveries, "plans_changed": plans_changed}


def _hist(date, art, a: SupplierAssessment, role: str, status: str) -> dict:
    return {"at": date, "article_id": art.id, "news_id": art.external_id, "role": role, "status": status,
            "priority": a.priority, "urgent": a.urgent, "impact_status": a.impact_status}


def _link(inc: dict, art, a: SupplierAssessment, role: str, date) -> dict:
    return {"incident_id": inc["id"], "article_id": art.id, "assessment_id": a.id, "role": role, "published_at": date}


def resolve_manually(db: Session, incident: Incident, note: str) -> Incident:
    now = utcnow()
    incident.resolution = {"manual": True, "note": note, "at": now.isoformat(), "by": "presenter",
                           "evidence_cutoff": (incident.last_evidence_at or now).isoformat()}
    incident.status = "resolved"
    incident.resolved_at = now
    incident.current_priority = 0.0
    incident.urgent = "N"
    incident.sound_eligible = False
    incident.history = list(incident.history or []) + [{"at": now.isoformat(), "role": "manual_resolution", "status": "resolved", "note": note}]
    db.commit()
    return incident


def requires_update(incident: Incident, clock: datetime) -> bool:
    return incident.status != "resolved" and incident.last_evidence_at is not None and clock - incident.last_evidence_at > STALE_AFTER
