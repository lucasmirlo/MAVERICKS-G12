"""Página «Modelo»: configuración activa, consenso del Test, uso de JEV/LLM e historial de análisis por noticia.

Todo es de lectura y no expone etiquetas de evaluación (las métricas siguen en /api/evaluations, solo presentador).
"""
from __future__ import annotations

import json
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import queries as q
from ..config import ROOT, get_settings
from ..db import get_db, utcnow
from ..jev.questions import QUESTION_VERSION
from ..llm import status as llm_status
from ..llm.prompts import ADJUDICATION_PROMPT_VERSION
from ..models import Analysis, Article, ArticleVersion, JevCall, SupplierAssessment
from ..policy import active_policy
from ..security import ApiError

router = APIRouter()
RUNS_DIR = ROOT / "evaluation" / "runs"


@router.get("/model/config")
def model_config(db: Session = Depends(get_db)):
    s = get_settings()
    policy = active_policy(db)
    sources = dict(db.execute(select(SupplierAssessment.decision_source, func.count()).where(
        SupplierAssessment.accepted.is_(True)).group_by(SupplierAssessment.decision_source)).all())
    roles = {"jev": "JEV decide Urgent con su pregunta de urgencia; la IA solo opina (visible para revisión)",
             "regla_y_jev": "Urgent exige que la regla de prioridad y JEV coincidan; la IA solo opina",
             "llm": "La IA decide los casos dudosos (regla y JEV discrepan o probabilidades intermedias)"}
    return {
        "jev_model": s.jev_model, "question_version": QUESTION_VERSION, "policy_version": policy["version"],
        "urgency_priority_threshold": policy["thresholds"].get("urgent_priority"), "urgency_mode": s.urgency_mode,
        "urgency_mode_description": roles.get(s.urgency_mode, s.urgency_mode),
        "llm": {**llm_status(), "adjudication_prompt_version": ADJUDICATION_PROMPT_VERSION,
                "role": "decide casos dudosos" if s.urgency_mode == "llm" else "explica, redacta planes y opina"},
        "thresholds": policy["thresholds"], "weights": policy["weights"],
        "decision_sources_accepted_pairs": {k or "-": v for k, v in sources.items()},
        "history": [
            {"version": "1.0.0", "note": "Constructor de referencia del kit"},
            {"version": "1.1.0", "note": "Vínculo regional explícito y contexto geográfico inferido (training)"},
            {"version": "1.2.0", "note": "Exposición directa, alcance sectorial y urgencia frente al buffer (training)"},
            {"version": "1.3.0", "note": "Vínculo y riesgo de 1.2.0 con la pregunta de urgencia original del kit (sprint 3)"},
        ],
    }


@router.get("/model/consensus")
def consensus():
    """Consensos guardados por scripts/export_consensus.py (Test: sin etiquetas)."""
    out = []
    for f in sorted(RUNS_DIR.glob("consenso_*_votacion.json"), reverse=True):
        data = json.loads(f.read_text(encoding="utf-8"))
        runs = []
        for r in data.get("runs", []):
            runs.append({k: r.get(k) for k in ("run", "elapsed_s", "jev_s", "llm_pairs", "models")})
        stamp = f.name.split("_")[-3] + "_" + f.name.split("_")[-2] if f.name.count("_") >= 3 else f.name
        mode = None
        first = sorted(RUNS_DIR.glob(f.name.replace("_votacion.json", "_ejecucion1.json")))
        if first:
            run1 = json.loads(first[0].read_text(encoding="utf-8"))
            mode = run1.get("urgency_mode")
            question = run1.get("question_version")
        else:
            question = None
        out.append({"file": f.name, "stamp": stamp, "sheet": data.get("sheet"), "rows": data.get("rows"),
                    "unanimous_rows": data.get("unanimous_rows"), "xlsx": data.get("xlsx"), "runs": runs,
                    "question_version": question, "urgency_mode": mode,
                    "voted": [{"news_id": v["news_id"], "is_risk": v["is_risk"], "urgent": v["urgent"], "affected": v["affected"],
                               "unanimous": v["unanimous"], "votes": v["votes"]} for v in data.get("voted", [])]})
    return {"items": out}


@router.get("/model/usage")
def usage(db: Session = Depends(get_db)):
    since = utcnow() - timedelta(hours=24)
    calls = list(db.scalars(select(JevCall).where(JevCall.created_at >= since)))
    tokens_in = sum((c.usage or {}).get("input_tokens", 0) or 0 for c in calls)
    tokens_out = sum((c.usage or {}).get("output_tokens", 0) or 0 for c in calls)
    llm_rows = [a.llm_decision for a in db.scalars(select(SupplierAssessment).where(SupplierAssessment.llm_decision.is_not(None)))]
    llm_meta = [d.get("meta") or {} for d in llm_rows if isinstance(d, dict)]
    lat = [m.get("latency_ms") for m in llm_meta if m.get("latency_ms")]
    return {
        "window_hours": 24,
        "jev": {"calls": len(calls), "input_tokens": tokens_in, "output_tokens": tokens_out,
                "mean_latency_ms": int(sum(c.duration_ms for c in calls) / len(calls)) if calls else None,
                "cache_entries_total": db.scalar(select(func.count()).select_from(JevCall)) or 0,
                "by_stage": {s: n for s, n in db.execute(select(JevCall.stage, func.count()).where(JevCall.created_at >= since).group_by(JevCall.stage)).all()}},
        "llm": {"opinions_stored": len(llm_rows), "failures": sum(1 for d in llm_rows if isinstance(d, dict) and d.get("error")),
                "mean_latency_ms": int(sum(lat) / len(lat)) if lat else None,
                "input_tokens": sum(m.get("input_tokens") or 0 for m in llm_meta),
                "output_tokens": sum(m.get("output_tokens") or 0 for m in llm_meta)},
        "note": "Coste: consultar la tarifa vigente de la cuenta TypeSafe; el LLM local no tiene coste por token.",
    }


@router.get("/articles/{article_id}/runs")
def article_runs(article_id: str, db: Session = Depends(get_db)):
    art = db.get(Article, article_id)
    if art is None:
        raise ApiError(404, "article_not_found", "Noticia no encontrada.")
    versions = {v.id: v.version for v in db.scalars(select(ArticleVersion).where(ArticleVersion.article_id == article_id))}
    runs = []
    for an in db.scalars(select(Analysis).where(Analysis.article_id == article_id).order_by(Analysis.created_at.desc())):
        runs.append({"id": an.id, "version": versions.get(an.article_version_id), "status": an.status, "engine_mode": an.engine_mode,
                     "model_id": an.model_id, "question_version": an.question_version, "policy_version": an.policy_version,
                     "urgency_mode": an.urgency_mode, "is_risk": an.is_risk, "urgent": an.urgent,
                     "affected_supplier_ids": an.affected_supplier_ids, "cached": an.cached, "duration_ms": an.duration_ms,
                     "finished_at": q.iso(an.finished_at), "current": an.article_version_id == art.current_version_id,
                     "decision_sources": sorted({a.decision_source for a in an.assessments if a.accepted and a.decision_source})})
    return {"items": runs}
