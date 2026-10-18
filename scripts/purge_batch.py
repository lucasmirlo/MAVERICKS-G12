"""Borra por completo un lote y todo lo que deriva de él (artículos, análisis, incidentes, alertas, borradores).

    python scripts/purge_batch.py --context <batch_id>
    python scripts/purge_batch.py --split liveday           # todos los lotes de ese tipo
    python scripts/purge_batch.py --list

Pide confirmación salvo con --yes. Opera sobre DATABASE_URL (por defecto, la base local).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.maintenance import purge_batch  # noqa: E402
from app.models import ImportBatch  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--context", "--batch", dest="batch", help="ID del lote a borrar")
    p.add_argument("--split", help="training | validation | test | liveday")
    p.add_argument("--list", action="store_true")
    p.add_argument("--yes", action="store_true")
    args = p.parse_args()
    with SessionLocal() as db:
        if args.list or not (args.batch or args.split):
            for b in db.scalars(select(ImportBatch).order_by(ImportBatch.created_at)):
                print(f"{b.id}  {b.kind:<8} {b.split or '-':<10} {b.sheet_name:<16} {b.row_count:>3} filas  {b.created_at:%Y-%m-%d %H:%M}")
            return 0
        targets = [args.batch] if args.batch else list(db.scalars(select(ImportBatch.id).where(ImportBatch.split == args.split)))
        if not targets:
            print("No hay lotes que coincidan.")
            return 1
        if not args.yes and input(f"Se borrarán {len(targets)} lote(s) y todo lo derivado. Escribe 'borrar': ").strip() != "borrar":
            print("Cancelado.")
            return 1
        for bid in targets:
            print(bid, purge_batch(db, bid))
    return 0


if __name__ == "__main__":
    sys.exit(main())
