"""purge_batch borra un lote y todo lo derivado sin tocar otros lotes."""
from sqlalchemy import func, select

from app import incidents
from app.maintenance import purge_batch
from app.models import ActionPlan, Alert, Analysis, Article, ArticleVersion, Draft, ImportBatch, Incident, JevCall, Job, SupplierAssessment
from app.pipeline import analyze_version

from .helpers import ScriptedJev, add_article, add_catalog

RISK = {"EXS01": {"link": 0.95, "risk": 0.95, "urgent": 0.9, "severity": 9}}


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_purge_batch_removes_everything_derived(db):
    add_catalog(db)
    _, keep_v, keep_b = add_article(db, "Fire at Aster Labs", "Fire halted production.", news_id="K1")
    art, purge_v, purge_b = add_article(db, "Aster Labs fire update", "Still halted.", news_id="P1")
    for v in (keep_v, purge_v):
        analyze_version(db, v.id, client=ScriptedJev(RISK).client())
    incidents.rebuild_context(db, "exercise")
    inc = db.scalar(select(Incident).where(Incident.batch_id == purge_b.id))
    db.add(Draft(kind="supplier", supplier_id="EXS01", target_supplier_id="EXS01", incident_id=inc.id, article_id=art.id,
                 subject="s", body="b", factual_context={}, factual_context_hash="h"))
    db.add(Job(kind="analyze_article", payload={"version_id": purge_v.id}, batch_id=purge_b.id, idempotency_key="pj"))
    db.commit()
    assert count(db, Incident) == 2 and count(db, Alert) == 2 and count(db, ActionPlan) == 2
    keep_inc = db.scalar(select(Incident).where(Incident.batch_id == keep_b.id))
    keep_drafts = db.scalar(select(func.count()).select_from(Draft).where(Draft.incident_id == keep_inc.id))

    result = purge_batch(db, purge_b.id)
    db.expire_all()
    assert result["articles"] == 1 and result["drafts"] >= 1 and result["alerts"] == 1
    assert db.get(ImportBatch, purge_b.id) is None
    assert db.scalar(select(Article).where(Article.batch_id == purge_b.id)) is None
    assert count(db, ArticleVersion) == 1 and count(db, Analysis) == 1 and count(db, SupplierAssessment) == 1
    assert count(db, Incident) == 1 and db.scalar(select(Incident)).batch_id == keep_b.id
    assert count(db, Alert) == 1 and count(db, Job) == 0
    assert count(db, ActionPlan) == 1 and db.scalar(select(ActionPlan)).incident_id == keep_inc.id
    assert db.scalar(select(func.count()).select_from(Draft).where(Draft.incident_id == inc.id)) == 0
    assert db.scalar(select(func.count()).select_from(Draft).where(Draft.incident_id == keep_inc.id)) == keep_drafts
    # La caché JEV del lote conservado sigue ahí.
    assert count(db, JevCall) >= 1
