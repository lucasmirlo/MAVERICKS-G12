"""Calibra thresholds.urgent_priority SOLO con el lote de entrenamiento, sin llamar a JEV.

    python scripts/calibrate_urgency.py                 # imprime la tabla
    python scripts/calibrate_urgency.py --write         # además guarda el umbral en config/risk_policy.json

Lee de supplier_assessments el último análisis de cada noticia de training, recalcula P con la política
(incluido el ajuste de U por alternativo afectado) y lo cruza con las etiquetas Urgent de training, que se leen
de la tabla separada evaluation_labels. Validación, test y LiveDay no se usan.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app import decision  # noqa: E402
from app.config import file_policy  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.evaluation import binary_metrics  # noqa: E402
from app.models import Article, EvaluationLabel, ImportBatch, Supplier  # noqa: E402
from app.pipeline import pair_input  # noqa: E402
from app.queries import current_analysis  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

THRESHOLDS = [30 + 2.5 * i for i in range(17)]  # 30 … 70


def load_training(db):
    batch = db.scalar(select(ImportBatch).where(ImportBatch.split == "training", ImportBatch.kind == "news")
                      .order_by(ImportBatch.created_at.desc()))
    if batch is None:
        raise SystemExit("No hay lote de training importado.")
    labels = {l.news_id: l for l in db.scalars(select(EvaluationLabel).where(EvaluationLabel.batch_id == batch.id))}
    suppliers = {s.supplier_id: s for s in db.scalars(select(Supplier))}
    rows = []
    for art in db.scalars(select(Article).where(Article.batch_id == batch.id).order_by(Article.row_index)):
        an = current_analysis(db, art)
        if an is None or an.status not in ("done", "review"):
            raise SystemExit(f"{art.external_id}: sin análisis terminado; analiza antes el lote de training.")
        pairs = []
        for a in an.assessments:
            p = pair_input(a)
            p["llm"], p["llm_status"], p["manual"] = None, None, None  # solo regla + JEV
            pairs.append(p)
        rows.append({"news_id": art.external_id, "label": labels[art.external_id].urgent, "pairs": pairs, "event_type": an.event_type})
    return batch, rows, suppliers


def evaluate(policy, rows, suppliers, threshold):
    pol = copy.deepcopy(policy)
    pol["thresholds"]["urgent_priority"] = threshold
    out = []
    for r in rows:
        res = decision.evaluate_article(pol, r["pairs"], suppliers, event_type=r["event_type"])
        risk_active = [x for x in res if x["accepted"] and x["is_risk"] == "Y"]
        rule = any(x["urgent_rule"] for x in risk_active)
        jev = any(x["jev_urgent"] for x in risk_active)
        top = max(risk_active, key=lambda x: x["priority"] or 0, default=None)
        out.append({"news_id": r["news_id"], "label": r["label"], "rule": rule, "or": rule or jev,
                    "and": any(x["urgent_rule"] and x["jev_urgent"] for x in risk_active), "jev": jev,
                    "P": max(((x["priority"] or 0) for x in risk_active), default=0.0),
                    "severity": top["severity"] if top else None, "E": top["exposure"] if top else None,
                    "p_urgent": max((p["p_urgent"] for p in r["pairs"] if p["supplier_id"] in {x["supplier_id"] for x in risk_active}), default=None)})
    return out


def metrics(out, key):
    return binary_metrics([(o["label"], "Y" if o[key] else "N") for o in out])


def margin(out, t):
    ps = [o["P"] for o in out if o["P"] > 0]
    return min((abs(p - t) for p in ps), default=0.0)


def fmt(m):
    c = m["confusion"]
    f = lambda v: "  —  " if v is None else f"{v:5.2f}"  # noqa: E731
    return f"VP {c['tp']:>2} FP {c['fp']:>2} FN {c['fn']:>2} VN {c['tn']:>2}  P {f(m['precision'])} R {f(m['recall'])} F1 {f(m['f1'])}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="guarda el umbral elegido en config/risk_policy.json")
    args = ap.parse_args()
    policy = file_policy()
    with SessionLocal() as db:
        batch, rows, suppliers = load_training(db)
    print(f"Training: {batch.sheet_name} ({len(rows)} noticias, {sum(1 for r in rows if r['label'] == 'Y')} urgentes etiquetadas)\n")
    print(f"{'umbral':>6} | {'solo regla':<52} | F1 regla∨JEV | F1 regla∧JEV | margen")
    table = []
    for t in THRESHOLDS:
        out = evaluate(policy, rows, suppliers, t)
        m_rule, m_or, m_and = metrics(out, "rule"), metrics(out, "or"), metrics(out, "and")
        table.append((t, m_rule, m_or, m_and, margin(out, t), out))
        f = lambda v: "  —  " if v is None else f"{v:5.2f}"  # noqa: E731
        print(f"{t:6.1f} | {fmt(m_rule):<52} | {f(m_or['f1']):>12} | {f(m_and['f1']):>12} | {margin(out, t):6.2f}")
    best_f1 = max((x[1]["f1"] or 0) for x in table)
    tied = [x for x in table if (x[1]["f1"] or 0) == best_f1]
    chosen = max(tied, key=lambda x: x[4])
    t, m_rule, m_or, m_and, mg, out = chosen
    print(f"\nUmbral elegido: {t} (F1 regla {best_f1:.3f}; {len(tied)} umbrales empatados; margen al P más cercano {mg:.2f})")
    print(f"  solo regla : {fmt(m_rule)}")
    print(f"  regla ∨ JEV: {fmt(m_or)}")
    print(f"  regla ∧ JEV: {fmt(m_and)}")
    jev_only = metrics(out, "jev")
    print(f"  solo JEV (p_urgent ≥ 0,5, referencia versión 1): {fmt(jev_only)}")
    print("\nMal clasificadas con la regla en el umbral elegido:")
    for o in out:
        if (o["label"] == "Y") != o["rule"]:
            print(f"  {o['news_id']}: etiqueta {o['label']} · regla {'Y' if o['rule'] else 'N'} · P {o['P']:.1f} · gravedad {o['severity']} · "
                  f"E {o['E'] if o['E'] is None else round(o['E'], 3)} · p_urgent {o['p_urgent'] if o['p_urgent'] is None else round(o['p_urgent'], 2)}")
    report = {"batch": batch.id, "chosen": t, "best_f1": best_f1, "tied": [x[0] for x in tied],
              "table": [{"threshold": x[0], "rule": x[1], "rule_or_jev": x[2], "rule_and_jev": x[3], "margin": x[4]} for x in table]}
    out_dir = ROOT / "evaluation" / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "calibracion_urgencia_training.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.write:
        path = ROOT / "config" / "risk_policy.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["thresholds"]["urgent_priority"] = t
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nGuardado thresholds.urgent_priority = {t} en {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
