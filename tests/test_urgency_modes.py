"""URGENCY_MODE (sprint 3): jev por defecto, regla_y_jev y llm. La IA solo decide en modo llm."""
import json

import pytest

from app import llm
from app.adjudication import adjudicate_analysis
from app.config import get_settings
from app.export import export_status
from app.llm import FakeProvider
from app.models import Analysis
from app.pipeline import analyze_version

from .helpers import ScriptedJev, add_article, add_catalog
from .test_decision import pair, run as run_llm_mode, SUP, POLICY
from app import decision

DOUBT = {"EXS01": {"link": 0.95, "risk": 0.95, "urgent": 0.2, "severity": 9}}  # regla Y (P alto), JEV N


def run(mode, *pairs):
    return decision.evaluate_article(POLICY, list(pairs), SUP, event_type="fire_incident", mode=mode)


def test_default_mode_is_jev():
    assert get_settings().urgency_mode == "jev"


def test_jev_mode_follows_p_urgent():
    r = run("jev", pair(p_urgent=0.2))[0]
    assert r["urgent"] == "N" and r["decision_source"] == "jev" and r["urgent_rule"]  # la regla dice Y, decide JEV
    r = run("jev", pair(p_urgent=0.9))[0]
    assert r["urgent"] == "Y" and r["decision_source"] == "jev" and r["sound_eligible"]


def test_policy_1_1_2_urgent_threshold():
    # 1.1.2: 0,64, centro del hueco de training (falsa alarma más alta 0,59, urgente real más baja 0,68).
    assert POLICY["version"] == "1.1.2" and POLICY["thresholds"]["urgent"] == 0.64
    assert run("jev", pair(p_urgent=0.59))[0]["urgent"] == "N"
    assert run("jev", pair(p_urgent=0.64))[0]["urgent"] == "Y"
    assert run("jev", pair(p_urgent=0.68))[0]["urgent"] == "Y"


def test_regla_y_jev_requires_both():
    assert run("regla_y_jev", pair(p_urgent=0.2))[0]["urgent"] == "N"
    assert run("regla_y_jev", pair(p_urgent=0.9))[0]["urgent"] == "Y"
    low_p = pair(severity_jev=2.0, p_urgent=0.9)  # P bajo: la regla dice N
    assert run("regla_y_jev", low_p)[0]["urgent"] == "N" and run("jev", low_p)[0]["urgent"] == "Y"


def test_llm_opinion_does_not_decide_outside_llm_mode():
    opinion = {"razonamiento": "x" * 20, "vinculado": True, "es_riesgo": True, "urgente": True, "confianza": "alta"}
    r = run("jev", pair(p_urgent=0.2, llm=opinion, llm_status="hecha"))[0]
    assert r["urgent"] == "N" and r["decision_source"] == "jev" and "llm_disagrees" in r["review_reasons"]
    assert run_llm_mode(pair(p_urgent=0.2, llm=opinion, llm_status="hecha"))[0]["urgent"] == "Y"  # modo llm sí decide


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        run("otro", pair())


def test_jev_mode_export_does_not_wait_for_llm(db):
    llm.set_provider(FakeProvider(lambda s, u: json.dumps({"razonamiento": "Incendio con parada de la planta del proveedor.",
                                                            "vinculado": True, "es_riesgo": True, "urgente": True, "confianza": "alta"})))
    try:
        add_catalog(db)
        _, v, batch = add_article(db, "Fire at Aster Labs", "A fire halted production.")
        an = analyze_version(db, v.id, client=ScriptedJev(DOUBT).client())
        assert an.urgency_mode == "jev" and an.assessments[0].llm_status == "pendiente"
        assert export_status(db, batch)["ready"]  # la opinión pendiente no bloquea
        assert an.urgent == "N"
        adjudicate_analysis(db, an.id)
        db.expire_all()
        a = db.get(Analysis, an.id).assessments[0]
        assert a.urgent == "N" and a.decision_source == "jev" and "llm_disagrees" in a.review_reasons
        assert a.llm_decision["urgente"] is True  # propuesta visible para revisión humana
    finally:
        llm.set_provider(None)
