"""Smoke test de una URL desplegada (solo lectura salvo que se indique lo contrario).

    python scripts/smoke_test.py https://<dominio>.up.railway.app

Comprueba salud, preparación, API pública, ruta profunda, rechazo de mutaciones sin sesión,
estado RSS real y ausencia de secretos en el bundle del frontend.
"""
from __future__ import annotations

import re
import sys
import time

import httpx

SECRET_PATTERNS = [r"TYPESAFE_API_KEY", r"ADMIN_PASSWORD", r"SESSION_SECRET", r"Bearer\s+[A-Za-z0-9._-]{20,}", r"sk-[A-Za-z0-9]{16,}"]


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main(base: str) -> int:
    base = base.rstrip("/")
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        print(f"[{'OK' if ok else 'FALLO'}] {name} {detail}")

    with httpx.Client(timeout=20, follow_redirects=True) as c:
        t0 = time.monotonic()
        r = c.get(f"{base}/healthz")
        check("healthz", r.status_code == 200, f"{r.status_code} {int((time.monotonic() - t0) * 1000)} ms")
        r = c.get(f"{base}/readyz")
        check("readyz", r.status_code == 200 and r.json().get("status") == "ready", r.text[:120])
        if base.startswith("https://"):
            check("https", str(r.url).startswith("https://"), str(r.url))
        meta = c.get(f"{base}/api/meta").json()
        check("api/meta", "engine" in meta, f"motor={meta['engine']['mode']} modelo={meta['engine'].get('model')} worker_vivo={meta['worker']['alive']}")
        check("motor configurado", meta["engine"]["mode"] == "jev", meta["engine"]["mode"])
        check("worker activo", meta["worker"]["alive"], str(meta["worker"].get("last_heartbeat")))
        sup = c.get(f"{base}/api/suppliers?page_size=100").json()
        check("catálogo", sup["total"] == 40, f"{sup['total']} proveedores")
        r = c.get(f"{base}/proveedores/S001")
        check("ruta profunda /proveedores/S001", r.status_code == 200 and "<div id=\"root\">" in r.text, str(r.status_code))
        r = c.post(f"{base}/api/sources/sync")
        check("mutación sin sesión denegada", r.status_code == 401, str(r.status_code))
        r = c.get(f"{base}/api/evaluations")
        check("evaluación protegida", r.status_code == 401, str(r.status_code))
        src = c.get(f"{base}/api/sources").json()
        ok_sources = [s for s in src["items"] if s["healthy"]]
        for s in src["items"]:
            print(f"    RSS {s['name']}: {s['last_outcome']} HTTP {s['last_status']} items {s['last_item_count']} última consulta {s['last_attempt_at']} {s['error_message'] or ''}")
        check("RSS ≥ 4 de 6 operativas", len(ok_sources) >= 4, f"{len(ok_sources)}/{len(src['items'])}")
        html = c.get(f"{base}/").text
        pending = re.findall(r'src="(/assets/[^"]+\.js)"', html)
        bundles: set[str] = set()
        leaked = []
        while pending:  # recorre también los chunks cargados de forma diferida
            b = pending.pop()
            if b in bundles:
                continue
            bundles.add(b)
            js = c.get(f"{base}{b}").text
            leaked += [f"{p} en {b}" for p in SECRET_PATTERNS if re.search(p, js)]
            pending += ["/assets/" + m for m in re.findall(r'([\w.-]+\.js)', js) if ("/assets/" + m) not in bundles and c.head(f"{base}/assets/{m}").status_code == 200]
        check("sin secretos en el bundle", not leaked and bool(bundles), ", ".join(leaked) or f"{len(bundles)} bundles revisados")
    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} comprobaciones correctas")
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
