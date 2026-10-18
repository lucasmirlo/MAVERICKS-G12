"""El LLM decide solo los casos dudosos; un fallo conserva la regla y nunca se convierte en N."""
import json

import pytest
from sqlalchemy import select

from app import llm
from app.adjudication import adjudicate_analysis, build_case
from app.export import export_status
from app.llm import FakeProvider
from app.models import Analysis
from app.pipeline import analyze_version

from .helpers import ScriptedJev, add_article, add_catalog

# EXS01 (High, fuente única): P ≈ 83 ≥ umbral → regla Y. Con p_urgent 0,2 JEV dice N → caso dudoso.
DOUBT = {"EXS01": {"link": 0.95, "risk": 0.95, "urgent": 0.2, "severity": 9}}
FIRM = {"EXS01": {"link": 0.95, "risk": 0.95, "urgent": 0.9, "severity": 9}}


def answer(urgente=False, confianza="media"):
    return json.dumps({"razonamiento": "La noticia describe un incendio con parada breve ya contenida.", "vinculado": True,
                       "es_riesgo": True, "urgente": urgente, "confianza": confianza})


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "urgency_mode", "llm")  # estas pruebas cubren el modo del sprint 2
    yield
    llm.set_provider(None)


def analyze(db, script, provider):
    llm.set_provider(provider)
    add_catalog(db)
    _, v, batch = add_article(db, "Fire at Aster Labs", "A fire halted production at the plant.")
    an = analyze_version(db, v.id, client=ScriptedJev(script).client())
    return an, batch


def test_llm_decides_doubtful_pair(db):
    fake = FakeProvider(lambda s, u: answer(urgente=False, confianza="media"))
    an, batch = analyze(db, DOUBT, fake)
    a = an.assessments[0]
    assert a.doubtful and a.llm_status == "pendiente" and a.urgent == "Y" and a.decision_source == "regla"
    assert not export_status(db, batch)["ready"]  # «en análisis» hasta que responda el LLM
    result = adjudicate_analysis(db, an.id)
    db.expire_all()
    an = db.get(Analysis, an.id)
    a = an.assessments[0]
    assert result["decided"] == 1 and len(fake.calls) == 1
    assert a.decision_source == "llm" and a.urgent == "N" and a.llm_decision["razonamiento"].startswith("La noticia")
    assert an.urgent == "N" and an.is_risk == "Y" and export_status(db, batch)["ready"]


def test_firm_pair_never_calls_llm(db):
    fake = FakeProvider(lambda s, u: answer())
    an, _ = analyze(db, FIRM, fake)
    a = an.assessments[0]
    assert a.decision_source == "regla+jev" and not a.doubtful and a.llm_status == "no_necesaria"
    assert adjudicate_analysis(db, an.id)["pending"] == 0 and fake.calls == []


def test_llm_failure_keeps_rule_and_never_n(db):
    an, batch = analyze(db, DOUBT, FakeProvider(lambda s, u: "esto no es JSON"))
    result = adjudicate_analysis(db, an.id)
    db.expire_all()
    a = db.get(Analysis, an.id).assessments[0]
    assert result["failed"] == 1 and a.llm_status == "sin_segunda_opinion" and a.urgent == "Y" and a.decision_source == "regla"
    assert "sin_segunda_opinion" in a.review_reasons and export_status(db, batch)["ready"]  # no bloquea el lote


def test_low_confidence_stays_in_review_with_proposal(db):
    an, _ = analyze(db, DOUBT, FakeProvider(lambda s, u: answer(urgente=False, confianza="baja")))
    adjudicate_analysis(db, an.id)
    db.expire_all()
    a = db.get(Analysis, an.id).assessments[0]
    assert a.llm_status == "baja_confianza" and a.decision_source == "regla" and a.urgent == "Y"
    assert "llm_low_confidence" in a.review_reasons and a.llm_decision["urgente"] is False


def test_case_payload_has_facts_and_no_labels(db):
    fake = FakeProvider(lambda s, u: answer())
    an, _ = analyze(db, DOUBT, fake)
    case = build_case(db, an, an.assessments[0], {"buffer_not_applicable_categories": ["Logistics", "Services"],
                                                    "thresholds": {"urgent_priority": 50}})
    assert case["proveedor"]["fuente_unica"] == "Y" and case["prioridad"]["umbral_urgencia"] == 50
    assert case["jev"]["p_urgencia"] == 0.2 and "urgency_disagreement" in case["motivos_de_duda"]
    encoded = json.dumps(case)
    for marker in ("Is_Risk", "Explanation", "Affected_Supplier_IDs"):
        assert marker not in encoded


def test_without_llm_doubtful_pairs_get_no_second_opinion(db):
    an, batch = analyze(db, DOUBT, None)  # conftest: LLM_PROVIDER=none
    a = an.assessments[0]
    assert a.llm_status == "sin_segunda_opinion" and a.urgent == "Y" and export_status(db, batch)["ready"]
    assert db.scalar(select(Analysis)).urgent == "Y"
