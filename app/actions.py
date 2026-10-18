"""Planes de acción por incidente (sprint 2).

Python elige las acciones con reglas explícitas (versionadas en policy.action_rules) y calcula todas las cifras
desde la base de datos. El LLM solo redacta un resumen a partir de `facts` y `actions`; si añade cifras que no
están en `facts`, se descarta y queda la plantilla.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import utcnow
from .models import (
    ActionPlan,
    Article,
    ArticleVersion,
    Draft,
    Incident,
    IncidentArticle,
    Material,
    MaterialProduct,
    Supplier,
    SupplierAssessment,
)
from .texts import EVENT_LABELS, MONTHS, spanish_date

log = logging.getLogger("srr.actions")

ACTION_LABELS = {
    "monitor": "Vigilar y revisar en el informe semanal",
    "contact_supplier": "Pedir al proveedor impacto, pedidos afectados y fecha de recuperación",
    "shift_to_alternate": "Mover volumen al alternativo aprobado",
    "increase_safety_stock": "Adelantar pedidos y subir el stock de seguridad",
    "start_dual_sourcing": "Iniciar la cualificación de una segunda fuente",
    "reroute_logistics": "Cambiar de transportista o de ruta",
    "escalate_planning": "Avisar a planificación de producción",
}
DEADLINE_LABELS = {"hoy": "Hoy", "esta_semana": "Esta semana", "proximo_informe": "Próximo informe semanal"}
SPANISH_SPEAKING = {"Spain", "Mexico", "Argentina", "Chile", "Colombia", "Peru", "Uruguay", "Ecuador", "Bolivia", "Paraguay",
                    "Venezuela", "Costa Rica", "Panama", "Guatemala", "Honduras", "El Salvador", "Nicaragua", "Cuba",
                    "Dominican Republic", "Puerto Rico", "Puerto Rico (USA)", "Brazil"}  # España y Latinoamérica


def language_for(country: str | None) -> str:
    return "es" if country in SPANISH_SPEAKING else "en"


def _products(db: Session, supplier_id: str) -> list[str]:
    mats = list(db.scalars(select(Material.material_id).where(
        (Material.primary_supplier_id == supplier_id) | (Material.alternate_supplier_id == supplier_id))))
    return sorted(set(db.scalars(select(MaterialProduct.product).where(MaterialProduct.material_id.in_(mats))))) if mats else []


def _latest_assessment(db: Session, inc: Incident) -> SupplierAssessment | None:
    return db.scalar(select(SupplierAssessment).where(SupplierAssessment.incident_id == inc.id)
                     .order_by(SupplierAssessment.priority.desc().nulls_last()).limit(1))


def build_facts(db: Session, inc: Incident, policy: dict) -> dict:
    """Todos los números y nombres del plan salen de aquí (base de datos), nunca del LLM."""
    s = db.get(Supplier, inc.supplier_id)
    alt = db.get(Supplier, s.alternate_id) if s.alternate_id else None
    alt_affected = False
    if alt:
        stmt = select(Incident.id).where(Incident.context_id == inc.context_id, Incident.supplier_id == alt.supplier_id,
                                         Incident.status != "resolved")
        if inc.batch_id:
            stmt = stmt.where(Incident.batch_id == inc.batch_id)
        alt_affected = db.scalar(stmt.limit(1)) is not None
    a = _latest_assessment(db, inc)
    not_applicable = s.category in policy["buffer_not_applicable_categories"]
    cover = None if not_applicable else s.inventory_days
    event_date = inc.opened_at
    stockout = (event_date + timedelta(days=cover)).date().isoformat() if (cover is not None and event_date) else None
    link = db.scalar(select(IncidentArticle).where(IncidentArticle.incident_id == inc.id).order_by(IncidentArticle.published_at.desc()).limit(1))
    headline = None
    if link:
        art = db.get(Article, link.article_id)
        headline = db.get(ArticleVersion, art.current_version_id).headline if art else None
    products = _products(db, s.supplier_id)
    return {
        "incidente": {"id": inc.id, "tipo_evento": inc.event_type, "estado": inc.status, "urgente": inc.urgent == "Y",
                      "prioridad": inc.current_priority, "umbral_urgencia": policy["thresholds"].get("urgent_priority"),
                      "fecha_evento": event_date.date().isoformat() if event_date else None, "titular": headline,
                      "duracion_dias": a.duration_days if a else None,
                      "duracion_es_minima": bool(a and a.duration_is_lower_bound),
                      "decision": a.decision_source if a else None},
        "proveedor": {"id": s.supplier_id, "nombre": s.name, "ciudad": s.city, "pais": s.country, "categoria": s.category,
                      "material": s.material, "fuente_unica": s.single_source == "Y", "criticidad": s.criticality},
        "stock": {"margen_dias": "no aplica" if not_applicable else (cover if cover is not None else "no informado"),
                  "plazo_reposicion_dias": s.lead_days, "fecha_rotura_si_continua": stockout},
        "productos": products or "Productos no mapeados",
        "alternativo": ({"id": alt.supplier_id, "nombre": alt.name, "ciudad": alt.city, "pais": alt.country,
                         "afectado": alt_affected} if alt else None),
    }


def choose_actions(facts: dict, policy: dict) -> list[dict]:
    """Reglas explícitas (policy.action_rules). Devuelve [{code, label, reason, deadline}] en orden estable."""
    rules = policy.get("action_rules", {})
    prolonged = rules.get("prolonged_event_days", 30)
    fraction = rules.get("safety_stock_duration_fraction_of_cover", 0.5)
    week_cover = rules.get("deadline_this_week_cover_days", 30)
    inc, sup, stock, alt = facts["incidente"], facts["proveedor"], facts["stock"], facts["alternativo"]
    urgent = inc["urgente"]
    P = inc["prioridad"]
    threshold = inc["umbral_urgencia"]
    cover = stock["margen_dias"] if isinstance(stock["margen_dias"], (int, float)) else None
    duration = inc["duracion_dias"]
    physical = stock["margen_dias"] != "no aplica"
    prolonged_event = duration is not None and (duration >= prolonged or (cover is not None and duration > cover))
    soon = urgent or (P is not None and threshold is not None and P >= threshold) or (cover is not None and cover <= week_cover)

    def deadline(code: str) -> str:
        if code == "monitor":
            return "proximo_informe"
        if code == "start_dual_sourcing":
            return "esta_semana" if urgent else "proximo_informe"
        if urgent:
            return "hoy"
        return "esta_semana" if soon else "proximo_informe"

    out: list[tuple[str, str]] = []
    if not urgent or (P is not None and threshold is not None and P < threshold):
        out.append(("monitor", "Riesgo no urgente" if not urgent else f"Prioridad {_n(P)} por debajo del umbral {_n(threshold)}"))
    out.append(("contact_supplier", "Riesgo con vínculo confirmado"))
    if alt and not alt["afectado"]:
        out.append(("shift_to_alternate", f"Hay alternativo aprobado ({alt['nombre']}) sin incidente activo"))
    if physical and (urgent or duration is None or (cover is not None and duration > fraction * cover)):
        why = "Urgente" if urgent else ("Duración desconocida" if duration is None else
                                        f"Duración {_n(duration)} días mayor que la mitad de la cobertura ({_n(cover)} días)")
        out.append(("increase_safety_stock", why))
    if sup["fuente_unica"] and sup["criticidad"] == "High" and (urgent or prolonged_event):
        out.append(("start_dual_sourcing", "Fuente única de criticidad alta " + ("y urgente" if urgent else "con evento prolongado")))
    if sup["categoria"] == "Logistics":
        out.append(("reroute_logistics", "Proveedor logístico afectado" + (f"; alternativo {alt['nombre']}" if alt else "")))
    exceeds = duration is not None and cover is not None and duration > cover
    unknown_single = duration is None and sup["fuente_unica"]
    if urgent and (exceeds or unknown_single):
        out.append(("escalate_planning", f"La parada ({_n(duration)} días) supera la cobertura ({_n(cover)} días)" if exceeds
                    else "Duración desconocida con fuente única"))
    return [{"code": c, "label": ACTION_LABELS[c], "reason": r, "deadline": deadline(c)} for c, r in out]


def facts_hash(facts: dict, actions: list[dict]) -> str:
    return hashlib.sha256(json.dumps({"f": facts, "a": actions}, sort_keys=True, default=str).encode()).hexdigest()


def _n(v) -> str:
    """Número en formato español: 40 en lugar de 40.0; 35,9 con coma decimal."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).replace(".", ",") if isinstance(v, float) else str(v)


def template_summary(facts: dict, actions: list[dict]) -> str:
    inc, sup, stock = facts["incidente"], facts["proveedor"], facts["stock"]
    ev = EVENT_LABELS.get(inc["tipo_evento"] or "", "un evento")
    parts = [f"{sup['nombre']} ({sup['ciudad']}, {sup['pais']}) está afectado por {ev}"
             + (f" desde el {spanish_date(inc['fecha_evento'])}" if inc["fecha_evento"] else "") + "."]
    parts.append(f"Prioridad {_n(inc['prioridad'])} de 100" + (" y urgente." if inc["urgente"] else ", no urgente."))
    if isinstance(stock["margen_dias"], (int, float)):
        parts.append(f"Margen de stock: {_n(stock['margen_dias'])} días" + (f"; si la parada continúa, rotura estimada el {spanish_date(stock['fecha_rotura_si_continua'])}." if stock["fecha_rotura_si_continua"] else "."))
    else:
        parts.append(f"Margen de stock: {stock['margen_dias']}.")
    prods = facts["productos"]
    parts.append("Productos en juego: " + (", ".join(prods) if isinstance(prods, list) else prods) + ".")
    parts.append("Acciones: " + "; ".join(f"{a['label'].lower()} ({DEADLINE_LABELS[a['deadline']].lower()})" for a in actions) + ".")
    return " ".join(parts)


_NUM = re.compile(r"(?<![A-Za-z\d])\d+(?:[.,]\d+)?")  # «S014» es un código, no una cifra


def allowed_numbers(facts: dict) -> set[str]:
    nums: set[str] = set()

    def walk(v):
        if isinstance(v, dict):
            for k, x in v.items():
                if k != "id":  # los identificadores (UUID, S001) no son cifras citables
                    walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, bool) or v is None:
            return
        elif isinstance(v, (int, float)):
            for form in (str(v), f"{v:g}", str(int(v)) if float(v).is_integer() else str(v).replace(".", ",")):
                nums.add(form.replace(",", "."))
        elif isinstance(v, str):
            for m in _NUM.findall(v):
                nums.add(m.replace(",", "."))
            try:  # fechas ISO: día y año en texto («2 de septiembre de 2026»)
                d = datetime.fromisoformat(v[:10])
                nums.update({str(d.day), str(d.year), f"{d.day:02d}", str(d.month)})
            except ValueError:
                pass
    walk(facts)
    nums.update({"100", "0"})  # «prioridad X de 100»
    return nums


def numbers_not_in_facts(text: str, facts: dict) -> list[str]:
    allowed = allowed_numbers(facts)
    found = [m.replace(",", ".") for m in _NUM.findall(text)]
    return [n for n in found if n not in allowed and n.rstrip("0").rstrip(".") not in allowed]


# ------------------------------------------------------------------ borradores desde el plan

def _supplier_mail(facts: dict, lang: str) -> tuple[str, str]:
    inc, sup = facts["incidente"], facts["proveedor"]
    if lang == "es":
        subject = f"Consulta sobre continuidad de suministro de {sup['material']}"
        body = "\n".join([f"Hola equipo de {sup['nombre']}:", "",
                          f"Hemos visto información publicada el {spanish_date(inc['fecha_evento'])} sobre «{inc['titular']}». "
                          f"Queremos confirmar si afecta a las entregas de {sup['material']} previstas para Helixa.", "",
                          "¿Podéis indicarnos el impacto en vuestra operación, los pedidos de Helixa potencialmente afectados "
                          "y la fecha estimada de recuperación, si se conoce?", "",
                          "Gracias,", "Equipo de Procurement de Helixa"])
    else:
        subject = f"Supply continuity inquiry: {sup['material']}"
        body = "\n".join([f"Dear {sup['nombre']} team,", "",
                          f"We have seen news published on {inc['fecha_evento']} about \"{inc['titular']}\". "
                          f"We would like to confirm whether it affects planned deliveries of {sup['material']} to Helixa.", "",
                          "Could you share the impact on your operations, which Helixa orders may be affected and the "
                          "estimated recovery date, if known?", "",
                          "Kind regards,", "Helixa Procurement Team"])
    return subject, body


def _alternate_mail(facts: dict, lang: str) -> tuple[str, str]:
    sup, alt = facts["proveedor"], facts["alternativo"]
    if lang == "es":
        subject = f"Consulta de disponibilidad para {sup['material']}"
        body = "\n".join([f"Hola equipo de {alt['nombre']}:", "",
                          f"Estamos revisando la continuidad de suministro de {sup['material']} y os tenemos registrados como "
                          "alternativo aprobado. ¿Podéis confirmar disponibilidad actual, capacidad adicional y plazo de entrega?", "",
                          "Es una consulta informativa: no supone ningún compromiso de compra. Os enviaremos cantidades y "
                          "fechas cuando estén confirmadas.", "", "Gracias,", "Equipo de Procurement de Helixa"])
    else:
        subject = f"Availability inquiry: {sup['material']}"
        body = "\n".join([f"Dear {alt['nombre']} team,", "",
                          f"We are reviewing supply continuity for {sup['material']} and you are registered as an approved "
                          "alternate supplier. Could you confirm current availability, additional capacity and lead time?", "",
                          "This is an information request only and does not commit Helixa to any purchase. We will share "
                          "quantities and dates once confirmed.", "", "Kind regards,", "Helixa Procurement Team"])
    return subject, body


RECIPIENT = "[contacto de compras]"


def _sync_drafts(db: Session, plan: ActionPlan, inc: Incident) -> None:
    codes = {a["code"] for a in plan.actions}
    wanted = {}
    if "contact_supplier" in codes:
        lang = language_for(plan.facts["proveedor"]["pais"])
        wanted["supplier"] = (inc.supplier_id, lang, *_supplier_mail(plan.facts, lang))
    if "shift_to_alternate" in codes and plan.facts["alternativo"]:
        alt = plan.facts["alternativo"]
        lang = language_for(alt["pais"])
        wanted["alternate"] = (alt["id"], lang, *_alternate_mail(plan.facts, lang))
    existing = {d.kind: d for d in db.scalars(select(Draft).where(Draft.plan_id == plan.id))}
    for kind, d in existing.items():
        if kind not in wanted and not d.edited:
            db.delete(d)
    for kind, (target, lang, subject, body) in wanted.items():
        d = existing.get(kind)
        if d is None:
            db.add(Draft(kind=kind, supplier_id=inc.supplier_id, target_supplier_id=target, incident_id=inc.id, plan_id=plan.id,
                         recipient=RECIPIENT, subject=subject, body=body, language=lang, generator="plan",
                         factual_context=plan.facts, factual_context_hash=plan.facts_hash))
        elif not d.edited and d.factual_context_hash != plan.facts_hash:
            d.subject, d.body, d.language, d.target_supplier_id = subject, body, lang, target
            d.factual_context, d.factual_context_hash = plan.facts, plan.facts_hash


def sync_plans(db: Session, context_id: str, policy: dict) -> list[str]:
    """Crea o actualiza el plan de cada incidente activo. Devuelve los IDs de planes cuyos hechos cambiaron."""
    changed = []
    rules_version = policy.get("action_rules", {}).get("version", "1.0.0")
    for inc in db.scalars(select(Incident).where(Incident.context_id == context_id, Incident.status != "resolved")):
        facts = build_facts(db, inc, policy)
        actions = choose_actions(facts, policy)
        h = facts_hash(facts, actions)
        plan = db.scalar(select(ActionPlan).where(ActionPlan.incident_id == inc.id))
        if plan is not None and plan.facts_hash == h:
            continue
        if plan is None:
            plan = ActionPlan(incident_id=inc.id, context_id=context_id, batch_id=inc.batch_id, supplier_id=inc.supplier_id)
            db.add(plan)
        plan.rules_version = rules_version
        plan.facts, plan.actions, plan.facts_hash = facts, actions, h
        plan.summary_template = template_summary(facts, actions)
        plan.summary_llm, plan.summary_source, plan.summary_error, plan.summary_meta = None, "template", None, None
        db.flush()
        _sync_drafts(db, plan, inc)
        changed.append(plan.id)
    db.commit()
    return changed


def _without_ids(v):
    if isinstance(v, dict):
        return {k: _without_ids(x) for k, x in v.items() if k != "id"}
    if isinstance(v, list):
        return [_without_ids(x) for x in v]
    return v


def summarize_with_llm(db: Session, plan_id: str) -> dict:
    """Resumen de 80–120 palabras redactado por el LLM; se descarta si añade cifras que no están en facts."""
    from . import llm
    plan = db.get(ActionPlan, plan_id)
    if plan is None or plan.summary_source == "llm":
        return {"status": "skip"}
    if not llm.is_available():
        return {"status": "unavailable"}
    try:
        text, rec = llm.plan_summary(_without_ids(plan.facts), [{k: a[k] for k in ("label", "reason", "deadline")} for a in plan.actions])
    except llm.LLMError as exc:
        plan.summary_error = f"{exc.code}: se conserva la plantilla"
        db.commit()
        return {"status": "error", "code": exc.code}
    extra = numbers_not_in_facts(text, plan.facts)
    words = len(text.split())
    if extra:
        plan.summary_error = f"El texto del LLM incluía cifras ausentes de los hechos ({', '.join(extra[:5])}); se conserva la plantilla."
    elif not 60 <= words <= 160:
        plan.summary_error = f"El texto del LLM tenía {words} palabras; se conserva la plantilla."
    else:
        plan.summary_llm, plan.summary_source, plan.summary_error = text, "llm", None
    plan.summary_meta = rec.as_dict()
    db.commit()
    return {"status": plan.summary_source, "extra_numbers": extra, "words": words}


__all__ = ["ACTION_LABELS", "DEADLINE_LABELS", "build_facts", "choose_actions", "template_summary", "sync_plans",
           "summarize_with_llm", "numbers_not_in_facts", "language_for", "MONTHS"]
