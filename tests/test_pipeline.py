"""Pipeline completo con PostgreSQL real y JEV simulado por HTTP."""
import json

import pytest
from sqlalchemy import select

from app import incidents
from app.export import build_xlsx, export_status, join_ids
from app.importer import import_workbook
from app.models import Alert, EvaluationLabel, Incident
from app.pipeline import AnalysisFailed, analyze_version

from .helpers import ScriptedJev, add_article, add_catalog


def run(db, version, jev):
    an = analyze_version(db, version.id, client=jev.client())
    incidents.rebuild_context(db, an.context_id)
    return an


def test_positive_news_keeps_supplier_with_n(db):
    add_catalog(db)
    _, v, _ = add_article(db, "Aster Labs expands its approved production line", "Aster Labs announced an additional production line.")
    jev = ScriptedJev({"EXS01": {"link": 0.97, "risk": 0.03, "urgent": 0.02, "impact": "positive"}}, event_type="positive_news", event_state="positive")
    an = run(db, v, jev)
    assert an.affected_supplier_ids == ["EXS01"] and an.is_risk == "N" and an.urgent == "N"
    a = an.assessments[0]
    assert a.priority == 0 and not a.sound_eligible
    assert db.scalar(select(Incident)) is None


def test_homonym_not_linked_and_no_alarm(db):
    add_catalog(db)
    _, v, _ = add_article(db, "Aster Football Club wins local tournament", "The sports club celebrated its final match.")
    an = run(db, v, ScriptedJev({"EXS01": {"link": 0.08}}, event_type="not_relevant", event_state="unrelated"))
    assert an.affected_supplier_ids == [] and an.is_risk == "N" and an.status == "done"
    assert db.scalar(select(Alert)) is None


def test_regional_event_multiple_suppliers_single_stage_b(db):
    add_catalog(db)
    _, v, _ = add_article(db, "Flood closes industrial parks in Lyon", "Road closures halt two packaging plants in Lyon for 10 days.")
    jev = ScriptedJev({"EXS02": {"link": 0.9, "risk": 0.9, "urgent": 0.85, "severity": 7, "duration": "d1"},
                       "EXS03": {"link": 0.88, "risk": 0.9, "urgent": 0.3, "severity": 6}}, event_type="natural_disaster")
    an = run(db, v, jev)
    assert len(jev.requests) == 2  # etapa A + una única etapa B
    stage_b = jev.requests[1]
    assert {s["supplier_id"] for s in stage_b["state"]["suppliers"]} == {"EXS02", "EXS03"}
    assert an.affected_supplier_ids == ["EXS02", "EXS03"] and an.is_risk == "Y" and an.urgent == "Y"
    by = {a.supplier_id: a for a in an.assessments}
    assert by["EXS02"].duration_days == 10 and by["EXS02"].factor_values["B"] == pytest.approx(25 / 45)
    assert "inventory_missing" in by["EXS03"].review_reasons and "B" not in by["EXS03"].factor_values  # A09
    assert by["EXS02"].priority != by["EXS03"].priority  # puntuación por pareja
    # Stage A evalúa los 40/4 proveedores de la cartera
    assert sum(1 for k in jev.requests[0]["questions"] if k.startswith("linked_")) == 4


def test_logistics_not_applicable_inventory(db):
    add_catalog(db)
    _, v, _ = add_article(db, "Port strike at Rotterdam", "Delta Freight trucks halted by a port strike.")
    an = run(db, v, ScriptedJev({"EXS04": {"link": 0.95, "risk": 0.95, "urgent": 0.9, "severity": 6}}, event_type="labour_strike"))
    a = an.assessments[0]
    assert "B" not in a.factor_values and "inventory_missing" not in a.review_reasons and a.priority is not None


def test_payload_sent_to_provider_has_no_labels(db):
    """A03: inspecciona el cuerpo HTTP real enviado al proveedor tras importar el Excel de entrenamiento."""
    data = open("inputs/supplier_training.xlsx", "rb").read()
    res = import_workbook(db, data, "supplier_training.xlsx")
    news_batch = next(b for b in res["batches"] if b["kind"] == "news")
    labels = list(db.scalars(select(EvaluationLabel).where(EvaluationLabel.batch_id == news_batch["batch_id"])))
    assert len(labels) == 30
    from app.models import Article
    arts = list(db.scalars(select(Article).where(Article.batch_id == news_batch["batch_id"]).order_by(Article.row_index)))
    jev = ScriptedJev({}, event_type="other", event_state="unclear")
    for art in arts[:5]:
        analyze_version(db, art.current_version_id, client=jev.client())
    sent = "\n".join(r.content.decode() for r in jev.raw)
    for lab in labels[:5]:
        assert lab.explanation and lab.explanation not in sent
    for key in ("Is_Risk", "Urgent\"", "Affected_Supplier_IDs", "Event_Type", "Explanation"):
        assert key not in sent
    # Todos los 40 proveedores son candidatos en la etapa A
    assert sum(1 for k in jev.requests[0]["questions"] if k.startswith("linked_")) == 40


def test_error_never_becomes_n_and_blocks_export(db):
    add_catalog(db)
    art, v, batch = add_article(db, "Aster Labs fire", "A fire halted production.")
    jev = ScriptedJev({}, status_codes=[401])
    with pytest.raises(AnalysisFailed):
        analyze_version(db, v.id, client=jev.client())
    db.expire_all()
    status = export_status(db, batch)
    assert not status["ready"] and status["blockers"][0]["reason"] == "error"
    from app.models import Analysis
    an = db.scalar(select(Analysis))
    assert an.status == "error" and an.is_risk is None and an.urgent is None and an.error_code == "unauthorized"


def test_invalid_response_is_error_not_cached(db):
    add_catalog(db)
    _, v, _ = add_article(db, "x", "y")

    class Broken(ScriptedJev):
        def __call__(self, request):
            resp = super().__call__(request)
            body = resp.json()
            body["answers"].pop("linked_EXS01")
            import httpx
            return httpx.Response(200, json=body)
    with pytest.raises(AnalysisFailed) as e:
        analyze_version(db, v.id, client=Broken().client())
    assert e.value.error.code == "invalid_response"
    from app.models import JevCall
    assert db.scalar(select(JevCall)) is None


def test_cache_reuses_identical_request(db):
    add_catalog(db)
    _, v, _ = add_article(db, "Aster Labs fire", "A fire halted production.")
    jev = ScriptedJev({"EXS01": {"link": 0.95, "risk": 0.9, "urgent": 0.9}})
    an = analyze_version(db, v.id, client=jev.client())
    n = len(jev.requests)
    an2 = analyze_version(db, v.id, client=jev.client(), force=True)
    assert len(jev.requests) == n and an2.cached


def test_export_blocked_while_reanalysis_queued(db):
    from app import jobqueue
    add_catalog(db)
    art, v, batch = add_article(db, "Quiet day", "Nothing.")
    run(db, v, ScriptedJev({}, event_type="not_relevant", event_state="unrelated"))
    assert export_status(db, batch)["ready"]
    jobqueue.enqueue(db, "analyze_article", {"version_id": v.id}, batch_id=batch.id, idempotency_key="re")
    db.commit()
    status = export_status(db, batch)
    assert not status["ready"] and status["blockers"][0]["reason"] == "pending"


def test_export_format(db):
    add_catalog(db)
    art1, v1, batch = add_article(db, "Flood in Lyon", "Plants halted.", news_id="N1")
    from app.models import Article, ArticleVersion
    from app.textutil import content_hash
    art2 = Article(context_id="exercise", origin="excel", batch_id=batch.id, row_index=1, external_id="=N2", identity_key="k2",
                   source_name="T", language="en", source_row={"News_ID": "=N2"})
    db.add(art2); db.flush()
    v2 = ArticleVersion(article_id=art2.id, version=1, headline="Quiet day", summary="Nothing.", content_hash=content_hash("Quiet day", "Nothing."))
    db.add(v2); db.flush(); art2.current_version_id = v2.id; db.commit()
    run(db, v1, ScriptedJev({"EXS03": {"link": 0.9, "risk": 0.9, "urgent": 0.9}, "EXS02": {"link": 0.9, "risk": 0.9, "urgent": 0.2}}))
    run(db, v2, ScriptedJev({}, event_type="not_relevant", event_state="unrelated"))
    assert export_status(db, batch)["ready"]
    import io, openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(build_xlsx(db, batch)))
    rows = list(wb["Resultados"].iter_rows(values_only=True))
    assert rows[0] == ("News_ID", "Is_Risk", "Urgent", "Affected_Supplier_IDs")
    assert rows[1] == ("N1", "Y", "Y", "EXS02; EXS03")
    assert rows[2][:3] == ("=N2", "N", "N") and rows[2][3] in (None, "")
    assert wb["Resultados"]["A3"].data_type == "s"  # nunca fórmula
    assert join_ids(["S2", "S1", "S2", " "]) == "S1; S2"
