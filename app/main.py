"""Aplicación FastAPI: API bajo /api y frontend compilado bajo el mismo origen."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import model, presenter, public
from .config import get_settings
from .db import SessionLocal
from .logging_setup import setup_logging

setup_logging()
log = logging.getLogger("srr.web")

app = FastAPI(title="Supplier Risk Radar", version="1.0.0", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")


@app.exception_handler(StarletteHTTPException)
async def http_error(_request: Request, exc: StarletteHTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": f"http_{exc.status_code}", "message": str(exc.detail), "details": None, "retryable": False}
    return JSONResponse(status_code=exc.status_code, content=detail)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"code": "invalid_request", "message": "Petición no válida.", "details": details, "retryable": False})


@app.exception_handler(Exception)
async def unhandled(_request: Request, exc: Exception):
    log.exception("unhandled error: %s", exc.__class__.__name__)
    return JSONResponse(status_code=500, content={"code": "internal_error", "message": "Error interno. Consulta los logs del servidor.", "details": None, "retryable": True})


CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; script-src 'self'; "
       "connect-src 'self'; media-src 'self' data: blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


@app.middleware("http")
async def headers(request: Request, call_next):
    t0 = time.monotonic()
    response = await call_next(request)
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if get_settings().secure_cookies:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
        if request.method != "GET" or response.status_code >= 400:
            log.info("%s %s -> %s %dms", request.method, request.url.path, response.status_code, int((time.monotonic() - t0) * 1000))
    return response


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(Config(str(get_settings().resolve("alembic.ini")))).get_current_head()
    try:
        with SessionLocal() as db:
            current = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "error", "detail": exc.__class__.__name__})
    if current != head:
        return JSONResponse(status_code=503, content={"status": "migrating", "schema": current, "expected": head})
    return {"status": "ready", "schema": current}


app.include_router(public.router, prefix="/api")
app.include_router(presenter.router, prefix="/api")
app.include_router(model.router, prefix="/api")

static_dir = get_settings().resolve(get_settings().static_dir)
if (static_dir / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"code": "not_found", "message": "Ruta de API desconocida.", "details": None, "retryable": False})
    candidate = (static_dir / full_path).resolve()
    if full_path and candidate.is_file() and Path(static_dir.resolve()) in candidate.parents:
        return FileResponse(candidate)
    index = static_dir / "index.html"
    if index.is_file():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return JSONResponse(status_code=404, content={"code": "frontend_missing", "message": "Frontend no compilado. Ejecuta npm run build en frontend/.", "details": None, "retryable": False})
