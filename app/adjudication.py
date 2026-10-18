"""Segunda opinión del LLM para parejas dudosas (sprint 2).

Solo actúa sobre parejas con `doubtful` y `llm_status == "pendiente"`. Con confianza alta o media su decisión
sustituye a la regla (`decision_source = "llm"`); con baja la pareja queda en revisión con la propuesta visible.
Cualquier fallo conserva la regla y marca `sin_segunda_opinion`: nunca se convierte en N ni bloquea el lote.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import llm
from .config import get_settings
from .models import Analysis, Article, ArticleVersion, Material, MaterialProduct, Supplier, SupplierAssessment
from .pipeline import apply_decisions
from .policy import get_policy

log = logging.getLogger("srr.adjudication")
MAX_SUMMARY_CHARS = 700


def _inventory(s: Supplier, policy: dict):
    if s.category in policy["buffer_not_applicable_categories"]:
        return "no aplica"
    return s.inventory_days if s.inventory_days is not None else "no informado"


def _products(db: Session, supplier_id: str) -> list[str] | str:
    mats = list(db.scalars(select(Material.material_id).where(
        (Material.primary_supplier_id == supplier_id) | (Material.alternate_supplier_id == supplier_id))))
    prods = sorted({p for p in db.scalars(select(MaterialProduct.product).where(MaterialProduct.material_id.in_(mats)))}) if mats else []
    return prods or "Productos no mapeados"


def build_case(db: Session, analysis: Analysis, a: SupplierAssessment, policy: dict) -> dict:
    """JSON compacto del caso. Sin texto libre añadido: solo datos de la noticia, la ficha y las respuestas de JEV."""
    art = db.get(Article, analysis.article_id)
    ver = db.get(ArticleVersion, analysis.article_version_id)
    s = db.get(Supplier, a.supplier_id)
    alt = db.get(Supplier, s.alternate_id) if s.alternate_id else None
    evidence = {e["id"]: e["text"] for e in analysis.evidence or []}
    summary = (ver.summary or "")
    if len(summary) > MAX_SUMMARY_CHARS:
        summary = summary[:MAX_SUMMARY_CHARS] + "…"
    return {
        "noticia": {"titular": ver.headline, "resumen": summary,
                    "fecha": art.published_at.date().isoformat() if art.published_at else art.published_raw},
        "evidencia_jev": [evidence[e] for e in a.evidence_ids if e in evidence] or None,
        "proveedor": {
            "id": s.supplier_id, "nombre": s.name, "material": s.material, "ciudad": s.city, "pais": s.country,
            "categoria": s.category, "fuente_unica": s.single_source, "criticidad": s.criticality,
            "cobertura_inventario_dias": _inventory(s, policy), "plazo_reposicion_dias": s.lead_days,
            "productos": _products(db, s.supplier_id),
            "alternativo_aprobado": ({"id": alt.supplier_id, "nombre": alt.name, "afectado_por_esta_noticia": a.alternate_affected}
                                     if alt else None),
        },
        "jev": {"p_vinculo": round(a.p_link, 3), "p_riesgo": round(a.p_risk, 3), "p_urgencia": round(a.p_urgent, 3),
                "tipo_evento": analysis.event_type, "gravedad_1_a_10": a.severity_jev, "estado_impacto": a.impact_status,
                "duracion_dias": a.duration_days, "duracion_es_minima": a.duration_is_lower_bound,
                "base_del_vinculo": a.link_basis},
        "prioridad": {"P": a.priority, "umbral_urgencia": policy["thresholds"].get("urgent_priority"),
                      "indice_dependencia_E": round(a.exposure, 3) if a.exposure is not None else None,
                      "factores": {k: round(v, 3) for k, v in (a.factor_values or {}).items()},
                      "regla_dice_urgente": a.urgent_rule, "jev_dice_urgente": a.jev_urgent},
        "motivos_de_duda": a.doubt_reasons,
    }


def _ask(case: dict) -> dict:
    t0 = time.monotonic()
    try:
        out, rec = llm.adjudicate(case)
        status = "hecha" if out.confianza in ("alta", "media") else "baja_confianza"
        return {"status": status, "decision": {**out.model_dump(), "meta": rec.as_dict()}}
    except llm.LLMError as exc:
        return {"status": "sin_segunda_opinion", "decision": {"error": exc.code, "message": exc.message,
                                                              "meta": {"latency_ms": int((time.monotonic() - t0) * 1000)}}}


def adjudicate_analysis(db: Session, analysis_id: str) -> dict:
    analysis = db.get(Analysis, analysis_id)
    if analysis is None or analysis.status not in ("done", "review"):
        return {"pending": 0}
    pending = [a for a in analysis.assessments if a.doubtful and a.llm_status == "pendiente"]
    if not pending:
        return {"pending": 0}
    policy = get_policy(db, analysis.policy_version)
    if not llm.is_available():
        results = [{"status": "sin_segunda_opinion", "decision": {"error": "unavailable", "message": "LLM no disponible"}}] * len(pending)
    else:
        cases = [build_case(db, analysis, a, policy) for a in pending]
        workers = max(1, get_settings().llm["max_concurrency"])
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_ask, cases))
    for a, r in zip(pending, results):
        a.llm_status = r["status"]
        a.llm_decision = r["decision"]
    by_id = {s.supplier_id: s for s in db.scalars(select(Supplier))}
    apply_decisions(policy, analysis, by_id, analysis.event_type)
    db.commit()
    summary = {"pending": len(pending), "decided": sum(1 for r in results if r["status"] == "hecha"),
               "low_confidence": sum(1 for r in results if r["status"] == "baja_confianza"),
               "failed": sum(1 for r in results if r["status"] == "sin_segunda_opinion"),
               "latency_ms": [r["decision"].get("meta", {}).get("latency_ms") for r in results]}
    log.info("adjudication analysis=%s %s", analysis_id, summary)
    return summary


def needs_adjudication(analysis: Analysis) -> bool:
    return any(a.doubtful and a.llm_status == "pendiente" for a in analysis.assessments)
