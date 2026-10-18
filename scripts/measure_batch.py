"""Mide un lote de extremo a extremo: clic de analizar → exportación final disponible y descargada.

    ADMIN_PASSWORD=... python scripts/measure_batch.py https://<dominio> inputs/supplier_liveday.xlsx

Importa la entrada declarada en el manifiesto (idempotente), encola el análisis, consulta el progreso
cada 2 s y descarga el XLSX en cuanto la exportación deja de estar bloqueada. Incluye fallos y reintentos
en el tiempo total. LiveDay y test son ejecución final: lanzarlo solo cuando corresponda.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main(base: str, manifest_path: str, limit: float = 300.0, force: bool = False) -> int:
    base = base.rstrip("/")
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        print("Define ADMIN_PASSWORD en el entorno.")
        return 2
    with httpx.Client(timeout=30) as c:
        r = c.post(f"{base}/api/session", json={"password": password})
        r.raise_for_status()
        h = {"X-CSRF-Token": r.json()["csrf"]}
        imp = c.post(f"{base}/api/imports/manifest", json={"path": manifest_path}, headers=h)
        imp.raise_for_status()
        batch = next(b for b in imp.json()["batches"] if b["kind"] == "news")
        bid = batch["batch_id"]
        print(f"Lote {bid} ({batch['sheet']}, {batch['rows']} filas, {batch['status']})")
        t0 = time.monotonic()
        a = c.post(f"{base}/api/batches/{bid}/analyze", json={"retry_errors": True, "force": force}, headers=h)
        a.raise_for_status()
        print(f"Encolado: {a.json()['created']} nuevos, {a.json()['requeued']} reintentos")
        while True:
            p = c.get(f"{base}/api/batches/{bid}").json()
            cnt = p["counts"]
            elapsed = time.monotonic() - t0
            llm_pending = p.get("llm", {}).get("pending", 0)
            print(f"  {elapsed:6.1f} s  hechas={cnt['done']} revisión={cnt['review']} error={cnt['error']} pendientes={cnt['pending'] + cnt['running'] + cnt['not_started']} en análisis IA={llm_pending}")
            if p["export"]["ready"]:
                x = c.get(f"{base}/api/batches/{bid}/export.xlsx")
                x.raise_for_status()
                total = time.monotonic() - t0
                out = Path(f"export_{p['split']}_{int(time.time())}.xlsx")
                out.write_bytes(x.content)
                print(f"\nExportación descargada en {total:.1f} s → {out} ({len(x.content)} bytes)")
                print(f"Latencia por artículo p50={p['latency']['p50_ms']} ms p95={p['latency']['p95_ms']} ms (n={p['latency']['n']})")
                if "llm" in p:
                    m = p["llm"]
                    print(f"LLM: {m['doubtful_pairs']} parejas dudosas → {m['decided']} decididas, {m['low_confidence']} baja confianza, "
                          f"{m['no_second_opinion']} sin segunda opinión; latencia media {m['mean_latency_ms']} ms (n={m['n_calls']}); "
                          f"fuentes de decisión {m['sources']}")
                print("DENTRO DEL LÍMITE" if total <= limit else f"SUPERA EL LÍMITE DE {limit:.0f} s")
                return 0 if total <= limit else 1
            if cnt["error"] and not cnt["pending"] and not cnt["running"] and not p["jobs"].get("queued") and not p["jobs"].get("running"):
                print("Hay filas con error sin reintentos pendientes; la exportación sigue bloqueada:")
                for e in p.get("errors", []):
                    print(f"   {e['news_id']}: {e['error_code']} {e['error_message']}")
                return 1
            if elapsed > limit * 2:
                print("Tiempo máximo de espera superado.")
                return 1
            time.sleep(2)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--force"]
    if len(args) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(args[0], args[1], force="--force" in sys.argv))
