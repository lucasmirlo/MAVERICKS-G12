"""Revisión del código en ejecución: hash de los .py de app/ (o GIT_COMMIT si se define).

La web y el worker publican la suya; si no coinciden, la interfaz avisa de un despliegue a medias.
"""
from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent


@lru_cache
def code_revision() -> str:
    if os.environ.get("GIT_COMMIT"):
        return os.environ["GIT_COMMIT"][:12]
    h = hashlib.sha256()
    for p in sorted(APP_DIR.rglob("*.py")):
        h.update(p.relative_to(APP_DIR).as_posix().encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:12]
