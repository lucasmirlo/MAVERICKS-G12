"""Decisión por pareja: urgencia por P, segunda opinión de JEV y casos dudosos."""
from types import SimpleNamespace

from app import decision
from app.config import file_policy

POLICY = file_policy()
SUP = {
    "A": SimpleNamespace(supplier_id="A", category="API", criticality="High", single_source="Y", share_category_pct=40,
                         inventory_days=30, lead_days=90, alternate_id=None, data_issues=[]),
    "B": SimpleNamespace(supplier_id="B", category="API", criticality="Low", single_source="N", share_category_pct=5,
                         inventory_days=60, lead_days=30, alternate_id="C", data_issues=[]),
    "C": SimpleNamespace(supplier_id="C", category="API", criticality="Low", single_source="N", share_category_pct=5,
                         inventory_days=60, lead_days=30, alternate_id="B", data_issues=[]),
}


def pair(sid="A", **kw):
    p = dict(supplier_id=sid, p_link=0.95, p_risk=0.95, p_urgent=0.9, severity_jev=9.0, severity_confidence=0.9,
             impact_status="active", impact_confidence=0.9, has_evidence=True, duration_days=None, link_basis="identity",
             llm=None, llm_status=None, manual=None)
    p.update(kw)
    return p


def run(*pairs, event_type="fire_incident"):
    return decision.evaluate_article(POLICY, list(pairs), SUP, event_type=event_type)


def test_firm_when_rule_and_jev_agree():
    r = run(pair())[0]
    assert r["urgent"] == "Y" and r["urgent_rule"] and r["jev_urgent"] and r["decision_source"] == "regla+jev"
    assert not r["doubtful"] and r["llm_status"] == "no_necesaria" and r["sound_eligible"]


def test_disagreement_is_doubtful_and_keeps_rule():
    r = run(pair(p_urgent=0.2))[0]  # P alto (regla Y) pero JEV dice no urgente
    assert r["doubtful"] and "urgency_disagreement" in r["doubt_reasons"]
    assert r["urgent"] == "Y" and r["decision_source"] == "regla" and not r["sound_eligible"]
    assert "second_opinion_pending" in r["review_reasons"]
    r2 = run(pair(p_urgent=0.2, llm_status="sin_segunda_opinion"))[0]
    assert r2["urgent"] == "Y" and "sin_segunda_opinion" in r2["review_reasons"]  # nunca se convierte en N


def test_llm_decides_only_doubtful_cases():
    llm = {"razonamiento": "x", "vinculado": True, "es_riesgo": True, "urgente": False, "confianza": "media"}
    r = run(pair(p_urgent=0.2, llm=llm, llm_status="hecha"))[0]
    assert r["decision_source"] == "llm" and r["urgent"] == "N" and r["is_risk"] == "Y"
    low = run(pair(p_urgent=0.2, llm={**llm, "confianza": "baja"}, llm_status="baja_confianza"))[0]
    assert low["decision_source"] == "regla" and low["urgent"] == "Y" and "llm_low_confidence" in low["review_reasons"]


def test_llm_can_unlink_and_humano_overrides():
    llm = {"razonamiento": "x", "vinculado": False, "es_riesgo": False, "urgente": False, "confianza": "alta"}
    r = run(pair(p_link=0.55, llm=llm, llm_status="hecha"))[0]
    assert not r["accepted"] and r["is_risk"] == "N" and r["urgent"] == "N" and r["decision_source"] == "llm"
    h = run(pair(manual={"vinculado": True, "es_riesgo": True, "urgente": False}))[0]
    assert h["decision_source"] == "humano" and h["urgent"] == "N"


def test_review_band_and_inferred_region_are_doubtful():
    assert "probability_in_review_band" in run(pair(p_link=0.6))[0]["doubt_reasons"]
    r = run(pair(link_basis="inferred_region", p_link=0.7))[0]
    assert "inferred_region_link" in r["doubt_reasons"] and not r["sound_eligible"]


def test_alternate_affected_raises_dependency_in_same_article():
    alone = run(pair("B", severity_jev=6.0))[0]
    both = run(pair("B", severity_jev=6.0), pair("C", severity_jev=6.0))
    assert not alone["alternate_affected"] and alone["factor_values"]["U"] == 0
    assert both[0]["alternate_affected"] and both[0]["factor_values"]["U"] == 1 and both[0]["priority"] > alone["priority"]


def test_positive_news_keeps_link_without_urgency():
    r = run(pair(p_risk=0.03, p_urgent=0.02, impact_status="positive"), event_type="positive_news")[0]
    assert r["accepted"] and r["is_risk"] == "N" and r["urgent"] == "N" and r["priority"] == 0
    assert decision.aggregate([r]) == {"affected_supplier_ids": ["A"], "is_risk": "N", "urgent": "N"}
