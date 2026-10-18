"""Planes de acción: reglas explícitas, hechos desde la base de datos y LLM que solo redacta."""
import copy
import json

import pytest
from sqlalchemy import select

from app import incidents, llm
from app.actions import build_facts, choose_actions, numbers_not_in_facts, summarize_with_llm, template_summary
from app.config import file_policy
from app.llm import FakeProvider
from app.models import ActionPlan, Draft, Incident
from app.pipeline import analyze_version

from .helpers import ScriptedJev, add_article, add_catalog

POLICY = file_policy()


def facts(**over):
    f = {"incidente": {"id": "i", "tipo_evento": "fire_incident", "estado": "active", "urgente": True, "prioridad": 80.0,
                       "umbral_urgencia": 50.0, "fecha_evento": "2026-10-01", "titular": "Fire", "duracion_dias": None,
                       "duracion_es_minima": False, "decision": "regla+jev"},
         "proveedor": {"id": "S", "nombre": "Aster Labs", "ciudad": "Madrid", "pais": "Spain", "categoria": "API",
                       "material": "API X", "fuente_unica": True, "criticidad": "High"},
         "stock": {"margen_dias": 30, "plazo_reposicion_dias": 90, "fecha_rotura_si_continua": "2026-10-31"},
         "productos": ["Producto A"], "alternativo": None}
    for path, value in over.items():
        sec, key = path.split("__")
        if key == "*":
            f[sec] = value
        else:
            f[sec][key] = value
    return f


def codes(f):
    return {a["code"]: a["deadline"] for a in choose_actions(f, POLICY)}


def test_urgent_single_source_without_alternate():
    c = codes(facts())
    assert c == {"contact_supplier": "hoy", "increase_safety_stock": "hoy", "start_dual_sourcing": "esta_semana",
                 "escalate_planning": "hoy"}  # duración desconocida con fuente única → planificación


def test_not_urgent_monitors_and_waits_for_report():
    c = codes(facts(incidente__urgente=False, incidente__prioridad=30.0, stock__margen_dias=60,
                    proveedor__fuente_unica=False, incidente__duracion_dias=5))
    assert c == {"monitor": "proximo_informe", "contact_supplier": "proximo_informe"}


def test_alternate_only_if_not_affected():
    alt = {"id": "A2", "nombre": "Boreal", "ciudad": "Lyon", "pais": "France", "afectado": False}
    assert "shift_to_alternate" in codes(facts(alternativo__x=None) if False else facts(**{"alternativo__*": alt}))
    assert "shift_to_alternate" not in codes(facts(**{"alternativo__*": {**alt, "afectado": True}}))


def test_duration_rules_and_escalation():
    long_event = codes(facts(incidente__duracion_dias=45))  # supera la cobertura de 30
    assert "escalate_planning" in long_event and "increase_safety_stock" in long_event and "start_dual_sourcing" in long_event
    short = codes(facts(incidente__urgente=False, incidente__prioridad=40.0, incidente__duracion_dias=10, stock__margen_dias=60,
                        proveedor__fuente_unica=False))
    assert "increase_safety_stock" not in short and "escalate_planning" not in short  # 10 ≤ 60/2


def test_services_and_logistics_without_inventory():
    services = codes(facts(stock__margen_dias="no aplica", proveedor__categoria="Services"))
    assert "increase_safety_stock" not in services
    logistics = codes(facts(stock__margen_dias="no aplica", proveedor__categoria="Logistics", proveedor__fuente_unica=False))
    assert "reroute_logistics" in logistics and "increase_safety_stock" not in logistics


def test_numbers_check():
    f = facts()
    assert numbers_not_in_facts("Prioridad 80 de 100; margen de 30 días; rotura el 31 de octubre de 2026.", f) == []
    assert numbers_not_in_facts("Hay 500 unidades en stock y el alternativo tiene 12 días de capacidad.", f) == ["500", "12"]
    assert numbers_not_in_facts(template_summary(f, choose_actions(f, POLICY)), f) == []


@pytest.fixture()
def plan(db):
    add_catalog(db)
    _, v, _ = add_article(db, "Fire at Aster Labs", "A fire halted production at the Madrid plant.", published="2026-10-01")
    analyze_version(db, v.id, client=ScriptedJev({"EXS01": {"link": 0.95, "risk": 0.95, "urgent": 0.9, "severity": 9}}).client())
    incidents.rebuild_context(db, "exercise")
    return db.scalar(select(ActionPlan))


def test_plan_facts_come_from_database(db, plan):
    f = plan.facts
    assert f["stock"]["margen_dias"] == 30 and f["stock"]["fecha_rotura_si_continua"] == "2026-10-31"
    assert f["productos"] == "Productos no mapeados" and f["alternativo"] is None and f["proveedor"]["pais"] == "Spain"
    assert {a["code"] for a in plan.actions} >= {"contact_supplier", "increase_safety_stock"}
    drafts = list(db.scalars(select(Draft).where(Draft.plan_id == plan.id)))
    assert len(drafts) == 1 and drafts[0].language == "es" and drafts[0].recipient == "[contacto de compras]"


def test_alternate_draft_language_and_no_commitment(db):
    add_catalog(db)
    _, v, _ = add_article(db, "Strike at Boreal Packaging", "Boreal Packaging halted vial output in Lyon.")
    analyze_version(db, v.id, client=ScriptedJev({"EXS02": {"link": 0.95, "risk": 0.95, "urgent": 0.9, "severity": 9}}).client())
    incidents.rebuild_context(db, "exercise")
    plan = db.scalar(select(ActionPlan))
    assert "shift_to_alternate" in {a["code"] for a in plan.actions}  # EXS03 no está afectado
    alt = db.scalar(select(Draft).where(Draft.plan_id == plan.id, Draft.kind == "alternate"))
    assert alt.language == "en" and "does not commit" in alt.body and alt.recipient == "[contacto de compras]"


def test_llm_summary_rejected_if_it_adds_numbers(db, plan):
    llm.set_provider(FakeProvider(lambda s, u: json.dumps({"texto": "Hay 500 unidades disponibles. " * 15})))
    try:
        assert summarize_with_llm(db, plan.id)["status"] == "template"
        db.refresh(plan)
        assert plan.summary_source == "template" and "500" in plan.summary_error
        good = ("Aster Labs sufre un incendio que detiene su planta de Madrid. Es una fuente única de criticidad alta con "
                "un margen de stock de 30 días, por lo que la prioridad es 83.6 de 100 y el caso es urgente. Hoy se contactará "
                "con el proveedor para conocer el impacto, los pedidos afectados y la fecha de recuperación, se adelantarán "
                "pedidos para subir el stock de seguridad y se avisará a planificación de producción. Esta semana se iniciará la "
                "cualificación de una segunda fuente para reducir la dependencia del material afectado.")
        f = copy.deepcopy(plan.facts)
        llm.set_provider(FakeProvider(lambda s, u: json.dumps({"texto": good.replace("83.6", str(f["incidente"]["prioridad"]))})))
        assert summarize_with_llm(db, plan.id)["status"] == "llm"
        db.refresh(plan)
        assert plan.summary_source == "llm" and plan.summary_meta["provider"] == "fake"
    finally:
        llm.set_provider(None)


def test_resolved_incident_keeps_no_new_plan(db, plan):
    inc = db.get(Incident, plan.incident_id)
    incidents.resolve_manually(db, inc, "Confirmado por el proveedor")
    incidents.rebuild_context(db, "exercise")
    assert db.get(ActionPlan, plan.id) is not None  # el plan se conserva como historial
