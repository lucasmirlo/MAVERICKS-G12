"""Experimento de urgencia sobre ENTRENAMIENTO con los valores JEV ya guardados (no llama a JEV).

Recalcula Urgent por noticia con variantes de la regla de la pareja y lo cruza con las etiquetas
de entrenamiento. Solo lee la base; no cambia política, preguntas ni análisis.

    python scripts/urgency_experiment.py [--question-version 1.3.0] [--out evaluation/runs/experimento_urgencia_training.json]

Variantes:
- base: p_urgent >= 0,50 (la v3 actual)
- umbral: p_urgent >= 0,65
- filtro: p_urgent >= 0,50, vínculo firme (identity / location_explicit) e impacto active
- umbral+filtro: las dos cosas

Además: barrido del umbral (con y sin filtro) y validación cruzada dejando una noticia fuera,
eligiendo el umbral con las otras 29, para estimar cuánto se debe al ajuste sobre la propia muestra.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Analysis, Article, EvaluationLabel, ImportBatch, SupplierAssessment  # noqa: E402

FIRM = {"identity", "location_explicit"}
GRID = [round(0.50 + i * 0.01, 2) for i in range(31)]  # 0,50 … 0,80


def load(db, question_version: str) -> list[dict]:
    batch = db.scalar(select(ImportBatch).where(ImportBatch.split == "training").order_by(ImportBatch.created_at.desc()))
    labels = {lab.news_id: lab for lab in db.scalars(select(EvaluationLabel).where(EvaluationLabel.batch_id == batch.id))}
    rows = []
    for art in db.scalars(select(Article).where(Article.batch_id == batch.id)):
        lab = labels.get(art.external_id)
        if lab is None:
            continue
        an = db.scalar(select(Analysis).where(Analysis.article_id == art.id, Analysis.question_version == question_version,
                                              Analysis.status.in_(("done", "review"))).order_by(Analysis.seq.desc()))
        if an is None:
            raise SystemExit(f"{art.external_id}: sin análisis con preguntas {question_version}")
        pairs = [{"supplier_id": s.supplier_id, "p_urgent": s.p_urgent, "base": s.link_basis, "impact": s.impact_status}
                 for s in db.scalars(select(SupplierAssessment).where(SupplierAssessment.analysis_id == an.id,
                                                                      SupplierAssessment.accepted.is_(True),
                                                                      SupplierAssessment.is_risk == "Y"))]
        rows.append({"news_id": art.external_id, "label": lab.urgent, "is_risk": an.is_risk, "stored": an.urgent,
                     "event_type": an.event_type, "pairs": pairs})
    return sorted(rows, key=lambda r: r["news_id"])


def predict(row: dict, threshold: float, firm: bool) -> str:
    if row["is_risk"] != "Y":
        return "N"
    for p in row["pairs"]:
        if p["p_urgent"] is None or p["p_urgent"] < threshold:
            continue
        if firm and (p["base"] not in FIRM or p["impact"] != "active"):
            continue
        return "Y"
    return "N"


def score(rows: list[dict], preds: list[str]) -> dict:
    tp = sum(r["label"] == "Y" and p == "Y" for r, p in zip(rows, preds))
    fp = sum(r["label"] != "Y" and p == "Y" for r, p in zip(rows, preds))
    fn = sum(r["label"] == "Y" and p != "Y" for r, p in zip(rows, preds))
    tn = len(rows) - tp - fp - fn
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3),
            "fp_ids": [r["news_id"] for r, p in zip(rows, preds) if r["label"] != "Y" and p == "Y"],
            "fn_ids": [r["news_id"] for r, p in zip(rows, preds) if r["label"] == "Y" and p != "Y"]}


def best_threshold(rows: list[dict], firm: bool) -> float:
    """Mejor F1; empate → centro del tramo empatado (más margen a ambos lados)."""
    f1s = {t: score(rows, [predict(r, t, firm) for r in rows])["f1"] for t in GRID}
    top = max(f1s.values())
    tied = [t for t in GRID if f1s[t] == top]
    return tied[len(tied) // 2]


def leave_one_out(rows: list[dict], firm: bool) -> dict:
    preds, chosen = [], []
    for i, row in enumerate(rows):
        t = best_threshold(rows[:i] + rows[i + 1:], firm)
        chosen.append(t)
        preds.append(predict(row, t, firm))
    return {**score(rows, preds), "thresholds_chosen": sorted(set(chosen))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--question-version", default="1.3.0")
    ap.add_argument("--out", default="evaluation/runs/experimento_urgencia_training.json")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    with SessionLocal() as db:
        rows = load(db, args.question_version)

    stored = score(rows, [r["stored"] for r in rows])
    variants = {name: score(rows, [predict(r, t, f) for r in rows])
                for name, t, f in [("base", 0.50, False), ("umbral", 0.65, False), ("filtro", 0.50, True), ("umbral+filtro", 0.65, True)]}
    sweep = {("filtro" if f else "sin_filtro"): {f"{t:.2f}": score(rows, [predict(r, t, f) for r in rows])["f1"] for t in GRID}
             for f in (False, True)}
    loo = {"sin_filtro": leave_one_out(rows, False), "con_filtro": leave_one_out(rows, True)}
    signals = [{"news_id": r["news_id"], "label": r["label"], "stored": r["stored"], "event_type": r["event_type"],
                "max_p_urgent": max((p["p_urgent"] for p in r["pairs"]), default=None),
                "max_p_urgent_firm": max((p["p_urgent"] for p in r["pairs"] if p["base"] in FIRM and p["impact"] == "active"), default=None)}
               for r in rows if r["is_risk"] == "Y"]

    n_pos = sum(r["label"] == "Y" for r in rows)
    print(f"Entrenamiento: n={len(rows)}, urgentes etiquetadas={n_pos}, preguntas {args.question_version}")
    print(f"Guardado en BD (comprobación): {stored['tp']}/{stored['fp']}/{stored['fn']} F1 {stored['f1']}")
    for name, s in variants.items():
        print(f"{name:14s} VP {s['tp']} FP {s['fp']} FN {s['fn']} VN {s['tn']}  P {s['precision']:.2f} R {s['recall']:.2f} F1 {s['f1']:.2f}  FP={s['fp_ids']} FN={s['fn_ids']}")
    for k, v in loo.items():
        print(f"LOO {k:10s} VP {v['tp']} FP {v['fp']} FN {v['fn']} F1 {v['f1']:.2f}  umbrales elegidos {v['thresholds_chosen']}")
    for k, v in sweep.items():
        top = max(v.values())
        print(f"barrido {k}: F1 máx {top} en {[t for t, f in v.items() if f == top]}")
    print("Señales (noticias con riesgo):")
    for s in signals:
        print(f"  {s['news_id']} etiqueta {s['label']} v3 {s['stored']} {s['event_type'] or '':22s} pU máx {s['max_p_urgent']}  pU máx firme {s['max_p_urgent_firm']}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"created_at": datetime.now(timezone.utc).isoformat(), "split": "training",
                               "question_version": args.question_version, "n": len(rows), "urgent_labelled": n_pos,
                               "stored": stored, "variants": variants, "leave_one_out": loo, "sweep": sweep, "signals": signals,
                               "caveat": "Solo entrenamiento, 5 urgentes: un artículo mueve el F1 0,1–0,2."},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print("JSON:", os.path.relpath(out))


if __name__ == "__main__":
    main()
