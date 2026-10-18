"""Evaluación separada contra etiquetas disponibles. Nunca se usa en inferencia ni en rutas públicas.

Uso CLI (guarda el informe fuera de la app pública):
    python -m app.evaluation --batch <batch_id> [--out evaluation/runs]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal, utcnow
from .export import batch_rows
from .models import EvaluationLabel, EvaluationRun, ImportBatch


def binary_metrics(pairs: list[tuple[str, str]]) -> dict:
    tp = sum(1 for y, p in pairs if y == "Y" and p == "Y")
    fp = sum(1 for y, p in pairs if y == "N" and p == "Y")
    fn = sum(1 for y, p in pairs if y == "Y" and p == "N")
    tn = sum(1 for y, p in pairs if y == "N" and p == "N")
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else (0.0 if precision == 0 or recall == 0 else None)
    return {"n": len(pairs), "positives_labelled": tp + fn, "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
            "precision": precision, "recall": recall, "f1": f1}


def evaluate_batch(db: Session, batch: ImportBatch) -> dict:
    labels = {l.news_id: l for l in db.scalars(select(EvaluationLabel).where(EvaluationLabel.batch_id == batch.id))}
    if not labels:
        raise ValueError("El lote no tiene etiquetas: no se evalúa (test y LiveDay no tienen respuestas).")
    rows = batch_rows(db, batch)
    evaluated = [r for r in rows if r["news_id"] in labels and r["is_risk"] in ("Y", "N")]
    excluded = [{"news_id": r["news_id"], "reason": r["blocker"] or "sin decisión"} for r in rows if r not in evaluated]
    risk_pairs = [(labels[r["news_id"]].is_risk, r["is_risk"]) for r in evaluated if labels[r["news_id"]].is_risk in ("Y", "N")]
    urgent_pairs = [(labels[r["news_id"]].urgent, r["urgent"]) for r in evaluated if labels[r["news_id"]].urgent in ("Y", "N")]
    exact = 0
    tp_ids = fp_ids = fn_ids = 0
    per_article = []
    for r in evaluated:
        gold = set(labels[r["news_id"]].affected_supplier_ids or [])
        pred = set(r["affected"] or [])
        exact += int(gold == pred)
        tp_ids += len(gold & pred)
        fp_ids += len(pred - gold)
        fn_ids += len(gold - pred)
        per_article.append({"news_id": r["news_id"], "is_risk": [labels[r["news_id"]].is_risk, r["is_risk"]],
                            "urgent": [labels[r["news_id"]].urgent, r["urgent"]],
                            "ids_missing": sorted(gold - pred), "ids_extra": sorted(pred - gold),
                            "review": r["review_reasons"]})
    ids_with_suppliers = [r for r in evaluated if labels[r["news_id"]].affected_supplier_ids]
    # Desglose de quién decidió cada pareja (aceptada o dudosa) en los análisis evaluados.
    from .models import Analysis
    sources: dict[str, int] = {}
    llm_stats = {"doubtful_pairs": 0, "decided": 0, "low_confidence": 0, "no_second_opinion": 0}
    for r in evaluated:
        an = db.get(Analysis, r["analysis_id"]) if r["analysis_id"] else None
        for a in (an.assessments if an else []):
            if a.accepted or a.doubtful:
                sources[a.decision_source or "-"] = sources.get(a.decision_source or "-", 0) + 1
            if a.doubtful:
                llm_stats["doubtful_pairs"] += 1
                key = {"hecha": "decided", "baja_confianza": "low_confidence"}.get(a.llm_status, "no_second_opinion")
                llm_stats[key] += 1
    return {
        "batch_id": batch.id, "split": batch.split, "sheet": batch.sheet_name, "created_at": utcnow().isoformat(),
        "articles_total": len(rows), "articles_evaluated": len(evaluated), "excluded": excluded,
        "risk": binary_metrics(risk_pairs), "urgent": binary_metrics(urgent_pairs),
        "suppliers": {
            "exact_set_match": exact, "n": len(evaluated),
            "exact_set_accuracy": exact / len(evaluated) if evaluated else None,
            "articles_with_labelled_suppliers": len(ids_with_suppliers),
            "id_precision": tp_ids / (tp_ids + fp_ids) if tp_ids + fp_ids else None,
            "id_recall": tp_ids / (tp_ids + fn_ids) if tp_ids + fn_ids else None,
            "id_counts": {"tp": tp_ids, "fp": fp_ids, "fn": fn_ids},
        },
        "per_article": per_article,
        "decision_sources_pairs": sources, "llm": llm_stats,
        "caveat": "Muestra pequeña; no indica validez general para una operación real.",
    }


def run(db: Session, batch_id: str) -> EvaluationRun:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise ValueError("lote desconocido")
    metrics = evaluate_batch(db, batch)
    rows = batch_rows(db, batch)
    from .models import Analysis
    analyses = [db.get(Analysis, r["analysis_id"]) for r in rows if r["analysis_id"]]
    run_row = EvaluationRun(batch_id=batch.id, split=batch.split, metrics=metrics,
                            policy_version=",".join(sorted({a.policy_version for a in analyses})) or "-",
                            model_id=",".join(sorted({a.model_id or "-" for a in analyses})) or None)
    db.add(run_row)
    db.commit()
    return run_row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    parser.add_argument("--out", default="evaluation/runs")
    args = parser.parse_args()
    with SessionLocal() as db:
        r = run(db, args.batch)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{r.split}_{r.created_at:%Y%m%dT%H%M%S}.json"
        path.write_text(json.dumps(r.metrics, indent=2, ensure_ascii=False), encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
