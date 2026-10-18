"""Agrupación de eventos, recuperación y llegada tardía (A07, A08, EX07, EX12)."""
from sqlalchemy import select

from app import incidents
from app.models import Alert, Incident
from app.pipeline import analyze_version
from app.queries import ranking

from .helpers import ScriptedJev, add_article, add_catalog

RISK = {"EXS01": {"link": 0.95, "risk": 0.95, "urgent": 0.9, "severity": 9}}
RECOVERY = {"EXS01": {"link": 0.95, "risk": 0.05, "urgent": 0.02, "impact": "resolved"}}


def analyze(db, v, script, event_type="fire_incident", state="active"):
    an = analyze_version(db, v.id, client=ScriptedJev(script, event_type=event_type, event_state=state).client())
    incidents.rebuild_context(db, "exercise")
    return an


def test_duplicates_grouped_without_summing(db):
    add_catalog(db)
    _, v1, b = add_article(db, "Fire at Aster Labs", "Fire halted production.", published="2026-10-01", news_id="N1")
    _, v2, _ = add_article(db, "Aster Labs fire update", "Production still halted.", published="2026-10-02", news_id="N2")
    analyze(db, v1, RISK)
    analyze(db, v2, RISK)
    incs = list(db.scalars(select(Incident)))
    assert len(incs) == 1 and incs[0].current_priority == incs[0].peak_priority
    row = next(r for r in ranking(db, "exercise") if r["supplier_id"] == "EXS01")
    assert row["active_incidents"] == 1 and row["priority"] == incs[0].current_priority  # máximo, no suma


def test_distinct_event_stays_independent(db):
    add_catalog(db)
    _, v1, _ = add_article(db, "Fire at Aster Labs", "Fire halted production.", published="2026-10-01", news_id="N1")
    _, v2, _ = add_article(db, "Aster Labs warning letter", "Regulator restricts output.", published="2026-10-03", news_id="N2")
    analyze(db, v1, RISK)
    analyze(db, v2, {"EXS01": {"link": 0.95, "risk": 0.9, "urgent": 0.2, "severity": 5}}, event_type="regulatory_action")
    incs = list(db.scalars(select(Incident)))
    assert len(incs) == 2
    row = next(r for r in ranking(db, "exercise") if r["supplier_id"] == "EXS01")
    assert row["active_incidents"] == 2 and row["priority"] == max(i.current_priority for i in incs)


def test_recovery_resolves_matching_and_keeps_history(db):
    add_catalog(db)
    _, v1, _ = add_article(db, "Fire at Aster Labs", "Fire halted production.", published="2026-10-01", news_id="N1")
    _, v2, _ = add_article(db, "Aster Labs warning letter", "Regulator restricts output.", published="2026-10-02", news_id="N2")
    _, v3, _ = add_article(db, "Aster Labs restarts plant after fire", "Production resumed.", published="2026-10-05", news_id="N3")
    analyze(db, v1, RISK)
    analyze(db, v2, {"EXS01": {"link": 0.95, "risk": 0.9, "urgent": 0.2, "severity": 5}}, event_type="regulatory_action")
    analyze(db, v3, RECOVERY, event_type="fire_incident", state="resolved")
    incs = {i.event_type: i for i in db.scalars(select(Incident))}
    assert incs["fire_incident"].status == "resolved" and incs["fire_incident"].peak_priority > 0
    assert incs["regulatory_action"].status == "active"  # no se cierran todos
    assert [h["role"] for h in incs["fire_incident"].history] == ["trigger", "recovery"]


def test_recovery_processed_first_still_resolves(db):
    """Orden de procesamiento distinto del orden de publicación (worker paralelo)."""
    add_catalog(db)
    _, v1, _ = add_article(db, "Fire at Aster Labs", "Fire halted production.", published="2026-10-01", news_id="N1")
    _, v3, _ = add_article(db, "Aster Labs restarts plant", "Production resumed.", published="2026-10-05", news_id="N3")
    analyze(db, v3, RECOVERY, event_type="recovery", state="resolved")
    analyze(db, v1, RISK)
    inc = db.scalar(select(Incident))
    assert inc.status == "resolved"


def test_late_old_article_does_not_reopen(db):
    add_catalog(db)
    _, v1, _ = add_article(db, "Fire at Aster Labs", "Fire halted production.", published="2026-10-01", news_id="N1")
    _, v3, _ = add_article(db, "Aster Labs restarts", "Production resumed.", published="2026-10-05", news_id="N3")
    _, v2, _ = add_article(db, "Fire at Aster Labs: day two", "Still halted.", published="2026-10-02", news_id="N2")
    analyze(db, v1, RISK)
    analyze(db, v3, RECOVERY, event_type="recovery", state="resolved")
    analyze(db, v2, RISK)  # recibido tarde, fecha anterior a la recuperación
    incs = list(db.scalars(select(Incident)))
    assert len(incs) == 1 and incs[0].status == "resolved"


def test_alert_stable_across_rebuilds_and_ack_kept(db):
    add_catalog(db)
    _, v1, _ = add_article(db, "Fire at Aster Labs", "Fire halted production.", published="2026-10-01", news_id="N1")
    analyze(db, v1, RISK)
    alerts = list(db.scalars(select(Alert)))
    assert len(alerts) == 1 and alerts[0].sound_eligible and alerts[0].urgent == "Y"
    alerts[0].status = "acknowledged"
    db.commit()
    incidents.rebuild_context(db, "exercise")
    again = list(db.scalars(select(Alert)))
    assert len(again) == 1 and again[0].id == alerts[0].id and again[0].status == "acknowledged"


def test_review_blocks_sound(db):
    add_catalog(db)
    _, v, _ = add_article(db, "Cedar Glass fire", "Fire at the vial plant.", news_id="N9")
    analyze(db, v, {"EXS03": {"link": 0.95, "risk": 0.95, "urgent": 0.95, "severity": 9}})  # inventario ausente → revisión
    al = db.scalar(select(Alert))
    assert al is not None and al.urgent == "Y" and not al.sound_eligible


def test_manual_resolution_survives_rebuild(db):
    add_catalog(db)
    _, v1, _ = add_article(db, "Fire at Aster Labs", "Fire halted production.", news_id="N1")
    analyze(db, v1, RISK)
    inc = db.scalar(select(Incident))
    incidents.resolve_manually(db, inc, "Confirmado por el proveedor")
    incidents.rebuild_context(db, "exercise")
    db.expire_all()
    inc = db.scalar(select(Incident))
    assert inc.status == "resolved" and inc.resolution["manual"]
