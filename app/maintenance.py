"""Operaciones de mantenimiento sobre la base de datos (no expuestas en la API pública)."""
from __future__ import annotations

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from . import incidents
from .models import (
    Alert,
    Analysis,
    Article,
    Draft,
    EvaluationLabel,
    EvaluationRun,
    ImportBatch,
    Incident,
    IncidentArticle,
    JevCall,
    Job,
)


def purge_batch(db: Session, batch_id: str) -> dict:
    """Borra un lote y todo lo que deriva de él: artículos, versiones, análisis, evaluaciones por proveedor,
    incidentes, alertas, borradores, trabajos, etiquetas, evaluaciones y caché JEV de sus peticiones."""
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise ValueError(f"lote {batch_id} no encontrado")
    context_id = batch.context_id
    article_ids = list(db.scalars(select(Article.id).where(Article.batch_id == batch_id)))
    analyses = list(db.scalars(select(Analysis).where(Analysis.article_id.in_(article_ids)))) if article_ids else []
    hashes = {h for an in analyses for h in (an.request_hash_a, an.request_hash_b) if h}
    incident_ids = set(db.scalars(select(Incident.id).where(Incident.batch_id == batch_id)))
    if article_ids:
        incident_ids |= set(db.scalars(select(IncidentArticle.incident_id).where(IncidentArticle.article_id.in_(article_ids))))
    counts = {"articles": len(article_ids), "analyses": len(analyses), "incidents": len(incident_ids)}
    draft_filter = []
    if article_ids:
        draft_filter.append(Draft.article_id.in_(article_ids))
    if incident_ids:
        draft_filter.append(Draft.incident_id.in_(incident_ids))
    counts["drafts"] = db.execute(delete(Draft).where(or_(*draft_filter))).rowcount if draft_filter else 0
    if incident_ids:
        counts["alerts"] = db.execute(delete(Alert).where(Alert.incident_id.in_(incident_ids))).rowcount
        db.execute(delete(Incident).where(Incident.id.in_(incident_ids)))
    else:
        counts["alerts"] = 0
    if hashes:
        counts["jev_cache"] = db.execute(delete(JevCall).where(JevCall.request_hash.in_(hashes))).rowcount
    counts["jobs"] = db.execute(delete(Job).where(Job.batch_id == batch_id)).rowcount
    db.execute(delete(EvaluationRun).where(EvaluationRun.batch_id == batch_id))
    db.execute(delete(EvaluationLabel).where(EvaluationLabel.batch_id == batch_id))
    for an in analyses:
        db.delete(an)  # cascada a supplier_assessments
    db.flush()
    db.delete(batch)  # cascada a artículos y versiones
    db.commit()
    incidents.rebuild_context(db, context_id)
    return counts
