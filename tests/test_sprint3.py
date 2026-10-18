"""Sprint 3: mesa de atención, verificación de vínculo, materiales, borradores, CSV, ejecuciones y revisión."""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import incidents
from app.actions import choose_actions
from app.config import file_policy
from app.main import app
from app.models import ActionPlan, Draft, Material
from app.pipeline import analyze_version
from app.queries import attention_desk
from app.revision import code_revision

from .helpers import ScriptedJev, add_article, add_catalog
from .test_actions import facts

POLICY = file_policy()


@pytest.fixture()
def scenario(db):
    """Dos incidentes: Aster (urgente, P alto) y Boreal (no urgente, vínculo solo regional)."""
    add_catalog(db)
    db.add(Material(material_id="M1", name="Vials", primary_supplier_id="EXS02", alternate_supplier_id="EXS03", row_index=0))
    db.commit()
    _, v1, batch = add_article(db, "Fire at Aster Labs", "A fire halted production at the Madrid plant.", news_id="N1")
    _, v2, _ = add_article(db, "Flooding in the Rhone valley", "Roads closed near industrial parks.", news_id="N2", batch=batch, row=1)
    analyze_version(db, v1.id, client=ScriptedJev({"EXS01": {"link": 0.95, "risk": 0.95, "urgent": 0.9, "severity": 9}}).client())
    analyze_version(db, v2.id, client=ScriptedJev({"EXS02": {"link": 0.7, "risk": 0.9, "urgent": 0.2, "severity": 5}},
                                                  event_type="natural_disaster").client())
    incidents.rebuild_context(db, "exercise")
    return batch


def test_attention_desk_orders_by_urgency_then_priority(db, scenario):
    desk = attention_desk(db, "exercise")
    assert [d["supplier_id"] for d in desk] == ["EXS01", "EXS02"]
    assert desk[0]["urgent"] == "Y" and desk[0]["next_actions"][0]["deadline"] == "hoy"
    assert all(len(d["next_actions"]) <= 2 for d in desk) and desk[0]["stock_margin"] == 30


def test_weak_link_gets_verification_action_and_draft(db, scenario):
    plan = next(p for p in db.scalars(select(ActionPlan)) if p.supplier_id == "EXS02")
    codes = [a["code"] for a in plan.actions]
    assert "verify_link" in codes  # vínculo solo regional (ni nombre ni ciudad en la noticia)
    draft = db.scalar(select(Draft).where(Draft.plan_id == plan.id, Draft.kind == "verification"))
    assert draft.language == "en" and "not confirmed" in draft.body and draft.recipient == "[contacto de compras]"
    strong = facts(**{"incidente__vinculo": {"base": "identity", "p_vinculo": 0.95, "ia_discrepa": False}})
    assert "verify_link" not in {a["code"] for a in choose_actions(strong, POLICY)}
    disagree = facts(**{"incidente__vinculo": {"base": "identity", "p_vinculo": 0.95, "ia_discrepa": True}})
    assert "verify_link" in {a["code"] for a in choose_actions(disagree, POLICY)}


def test_materials_status_and_drafts_list(db, scenario):
    c = TestClient(app)
    m = c.get("/api/materials").json()
    row = m["items"][0]
    assert row["material_id"] == "M1" and row["status"] == "con_alternativo"  # EXS02 afectado, EXS03 libre
    assert "EXS01" in m["suppliers_without_material"]
    kinds = {d["kind"] for d in c.get("/api/drafts").json()["items"]}
    assert {"supplier", "verification", "alternate"} <= kinds


def test_csv_export_matches_rules(db, scenario):
    c = TestClient(app)
    r = c.get(f"/api/batches/{scenario.id}/export.csv")
    assert r.status_code == 200
    lines = r.content.decode("utf-8-sig").splitlines()
    assert lines[0] == "News_ID,Is_Risk,Urgent,Affected_Supplier_IDs" and lines[1] == "N1,Y,Y,EXS01" and len(lines) == 3


def test_article_runs_and_model_config(db, scenario):
    c = TestClient(app)
    art = c.get("/api/articles?context_id=exercise&page_size=10").json()["items"][0]
    runs = c.get(f"/api/articles/{art['id']}/runs").json()["items"]
    assert runs and runs[0]["question_version"] == "1.3.0" and runs[0]["urgency_mode"] == "jev" and runs[0]["current"]
    cfg = c.get("/api/model/config").json()
    assert cfg["urgency_mode"] == "jev" and cfg["question_version"] == "1.3.0" and "jev" in cfg["decision_sources_accepted_pairs"]


def test_model_consensus_reads_saved_runs(tmp_path, monkeypatch):
    from app.api import model
    (tmp_path / "consenso_News_Test_20990101_0000_votacion.json").write_text(json.dumps({
        "sheet": "News_Test", "rows": 1, "unanimous_rows": 1, "xlsx": "x.xlsx", "runs": [{"run": 1, "elapsed_s": 5.0}],
        "voted": [{"news_id": "T1", "is_risk": "Y", "urgent": "N", "affected": ["S1"], "unanimous": True,
                   "votes": {"is_risk": ["Y"], "urgent": ["N"], "ids": {"S1": 1}}}]}), encoding="utf-8")
    (tmp_path / "consenso_News_Test_20990101_0000_ejecucion1.json").write_text(json.dumps({"urgency_mode": "jev", "question_version": "1.3.0"}), encoding="utf-8")
    monkeypatch.setattr(model, "RUNS_DIR", tmp_path)
    items = TestClient(app).get("/api/model/consensus").json()["items"]
    assert items[0]["stamp"] == "20990101_0000" and items[0]["urgency_mode"] == "jev" and items[0]["voted"][0]["news_id"] == "T1"


def test_meta_reports_web_revision(db):
    meta = TestClient(app).get("/api/meta").json()
    assert meta["worker"]["web_revision"] == code_revision() and len(code_revision()) == 12


def test_reanalysis_unlinks_old_assessments(db):
    from app.config import get_settings
    from app.models import SupplierAssessment
    add_catalog(db)
    _, v, _ = add_article(db, "Fire at Aster Labs", "A fire halted production.")
    script = {"EXS01": {"link": 0.95, "risk": 0.95, "urgent": 0.9, "severity": 9}}
    old = analyze_version(db, v.id, client=ScriptedJev(script).client())
    incidents.rebuild_context(db, "exercise")
    # Nueva versión de la política → nuevo análisis de la misma versión del artículo.
    from app.policy import create_version
    create_version(db, base_version=old.policy_version, changes={"thresholds": {"link": 0.5}}, note="prueba")
    new = analyze_version(db, v.id, client=ScriptedJev(script).client())
    incidents.rebuild_context(db, "exercise")
    db.expire_all()
    linked = list(db.scalars(select(SupplierAssessment).where(SupplierAssessment.incident_id.is_not(None))))
    assert [a.analysis_id for a in linked] == [new.id]
