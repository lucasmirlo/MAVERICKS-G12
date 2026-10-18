"""Exportación por consenso del lote de Test: 3 ejecuciones completas (JEV no es determinista) y voto por mayoría.

    python scripts/export_consensus.py --batch <id_del_lote_test> [--runs 3]
    python scripts/export_consensus.py --split test

Cada ejecución borra los análisis y la caché JEV del lote, analiza todas las filas con JEV real, deja que el LLM
decida los casos dudosos y recoge Is_Risk, Urgent y Affected_Supplier_IDs. Se vota por mayoría cada flag y cada ID
de proveedor (Is_Risk = N implica Urgent = N). Guarda las ejecuciones en evaluation/runs/ y el XLSX del reto con
fecha y hora en el nombre. No usa etiquetas ni cambia umbrales: es la ejecución final.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select  # noqa: E402

from app import incidents, llm  # noqa: E402
from app.adjudication import adjudicate_analysis  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.export import batch_rows, build_xlsx, export_status, join_ids  # noqa: E402
from app.jev.questions import QUESTION_VERSION  # noqa: E402
from app.logging_setup import setup_logging  # noqa: E402
from app.models import Analysis, Article, ImportBatch, JevCall, Job  # noqa: E402
from app.pipeline import AnalysisFailed, analyze_version  # noqa: E402
from app.policy import active_policy  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def reset(db, batch_id: str) -> None:
    ids = list(db.scalars(select(Article.id).where(Article.batch_id == batch_id)))
    analyses = list(db.scalars(select(Analysis).where(Analysis.article_id.in_(ids))))
    hashes = {h for an in analyses for h in (an.request_hash_a, an.request_hash_b) if h}
    for an in analyses:
        db.delete(an)
    if hashes:
        db.execute(delete(JevCall).where(JevCall.request_hash.in_(hashes)))
    db.execute(delete(Job).where(Job.batch_id == batch_id))
    db.commit()


def analyze_one(version_id: str) -> str | None:
    with SessionLocal() as db:
        try:
            return analyze_version(db, version_id, force=True).id
        except AnalysisFailed as exc:
            print(f"   error JEV en {version_id}: {exc.error.code}")
            return None


def adjudicate_one(analysis_id: str) -> dict:
    with SessionLocal() as db:
        return adjudicate_analysis(db, analysis_id)


def one_run(batch_id: str, k: int) -> dict:
    t0 = time.monotonic()
    with SessionLocal() as db:
        reset(db, batch_id)
        versions = [a.current_version_id for a in db.scalars(select(Article).where(Article.batch_id == batch_id).order_by(Article.row_index))]
    with ThreadPoolExecutor(max_workers=4) as pool:
        analysis_ids = [x for x in pool.map(analyze_one, versions) if x]
    t_jev = time.monotonic() - t0
    with ThreadPoolExecutor(max_workers=2) as pool:
        adj = list(pool.map(adjudicate_one, analysis_ids))
    with SessionLocal() as db:
        incidents.rebuild_context(db, "exercise")
        batch = db.get(ImportBatch, batch_id)
        rows = batch_rows(db, batch)
        status = export_status(db, batch)
        model_ids = sorted({an.model_id for an in db.scalars(select(Analysis).where(Analysis.id.in_(analysis_ids))) if an.model_id})
        policy = active_policy(db)
    elapsed = time.monotonic() - t0
    llm_pairs = sum(a.get("pending", 0) for a in adj)
    print(f"Ejecución {k}: {elapsed:.1f} s (JEV {t_jev:.1f} s) · {len(analysis_ids)}/{len(versions)} filas · "
          f"{llm_pairs} parejas al LLM · bloqueos de exportación {len(status['blockers'])}")
    return {"run": k, "elapsed_s": round(elapsed, 1), "jev_s": round(t_jev, 1), "llm_pairs": llm_pairs,
            "llm": adj, "models": model_ids, "policy_version": policy["version"], "question_version": QUESTION_VERSION,
            "blockers": status["blockers"],
            "rows": [{"news_id": r["news_id"], "is_risk": r["is_risk"], "urgent": r["urgent"], "affected": sorted(r["affected"] or []),
                      "status": r["status"], "review_reasons": r["review_reasons"]} for r in rows]}


def vote(runs: list[dict]) -> list[dict]:
    n = len(runs)
    need = n // 2 + 1
    out = []
    for i, base in enumerate(runs[0]["rows"]):
        cells = [r["rows"][i] for r in runs]
        assert all(c["news_id"] == base["news_id"] for c in cells), "orden de filas distinto entre ejecuciones"
        risk = "Y" if sum(c["is_risk"] == "Y" for c in cells) >= need else "N"
        urgent = "Y" if risk == "Y" and sum(c["urgent"] == "Y" for c in cells) >= need else "N"
        ids = Counter(i for c in cells for i in c["affected"])
        affected = sorted(i for i, k in ids.items() if k >= need)
        unanimous = len({(c["is_risk"], c["urgent"], tuple(c["affected"])) for c in cells}) == 1
        out.append({"news_id": base["news_id"], "is_risk": risk, "urgent": urgent, "affected": affected, "unanimous": unanimous,
                    "votes": {"is_risk": [c["is_risk"] for c in cells], "urgent": [c["urgent"] for c in cells],
                              "ids": dict(ids)}})
    return out


def main() -> int:
    setup_logging()
    import logging
    logging.getLogger("srr").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch")
    ap.add_argument("--split", default=None)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--from-runs", dest="from_runs", help="sello AAAAMMDD_HHMM: vota con ejecuciones ya guardadas, sin repetirlas")
    args = ap.parse_args()
    with SessionLocal() as db:
        if args.batch:
            batch = db.get(ImportBatch, args.batch)
        else:
            batch = db.scalar(select(ImportBatch).where(ImportBatch.split == (args.split or "test"), ImportBatch.kind == "news")
                              .order_by(ImportBatch.created_at.desc()))
        if batch is None:
            raise SystemExit("Lote no encontrado.")
        batch_id, sheet = batch.id, batch.sheet_name
    print(f"Lote {batch_id} ({sheet}) · {args.runs} ejecuciones · LLM {llm.status()}")
    out_dir = ROOT / "evaluation" / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    runs = []
    if args.from_runs:
        stamp = args.from_runs
        files = sorted(out_dir.glob(f"consenso_{sheet}_{stamp}_ejecucion*.json"))
        if not files:
            raise SystemExit(f"No hay ejecuciones guardadas con el sello {stamp}.")
        runs = [json.loads(f.read_text(encoding="utf-8")) for f in files]
        print(f"Votando con {len(runs)} ejecuciones guardadas ({stamp}).")
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        for k in range(1, args.runs + 1):
            run = one_run(batch_id, k)
            runs.append(run)
            (out_dir / f"consenso_{sheet}_{stamp}_ejecucion{k}.json").write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")
    voted = vote(runs)
    rows = [{"news_id": v["news_id"], "is_risk": v["is_risk"], "urgent": v["urgent"], "affected": v["affected"], "review_reasons": [],
             "manual": False, "cached": False, "status": "consenso", "duration_ms": None, "analysis_id": None, "article_id": None}
            for v in voted]
    with SessionLocal() as db:
        batch = db.get(ImportBatch, batch_id)
        arts = {a.external_id: a.id for a in db.scalars(select(Article).where(Article.batch_id == batch_id))}
        for r in rows:
            r["article_id"] = arts[r["news_id"]]
        info = [("Método", f"Consenso por mayoría de {args.runs} ejecuciones completas (JEV + regla + LLM en dudosos)"),
                ("Unanimidad", f"{sum(v['unanimous'] for v in voted)} de {len(voted)} filas"),
                ("Tiempos (s)", ", ".join(str(r["elapsed_s"]) for r in runs)),
                ("Modelos", ", ".join(sorted({m for r in runs for m in r["models"]} | {llm.status()["model"]}))),
                ("Política / preguntas", f"{runs[0]['policy_version']} / {runs[0]['question_version']}")]
        data = build_xlsx(db, batch, rows=rows, extra_info=info)
    xlsx = out_dir / f"supplier_risk_radar_{sheet}_consenso_{stamp}.xlsx"
    xlsx.write_bytes(data)
    summary = {"batch": batch_id, "sheet": sheet, "runs": [{k: r[k] for k in ("run", "elapsed_s", "jev_s", "llm_pairs", "models")} for r in runs],
               "unanimous_rows": sum(v["unanimous"] for v in voted), "rows": len(voted), "voted": voted, "xlsx": xlsx.name}
    (out_dir / f"consenso_{sheet}_{stamp}_votacion.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFilas unánimes: {summary['unanimous_rows']}/{len(voted)} · XLSX: evaluation/runs/{xlsx.name}")
    for v in voted:
        if not v["unanimous"]:
            print(f"  {v['news_id']}: votos riesgo {v['votes']['is_risk']} urgente {v['votes']['urgent']} IDs {v['votes']['ids']} → "
                  f"{v['is_risk']}/{v['urgent']}/{join_ids(v['affected']) or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
