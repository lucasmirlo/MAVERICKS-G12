"""Acceso de presentador: contraseña compartida → cookie firmada HttpOnly; CSRF por cabecera; límite de intentos."""
from __future__ import annotations

import hmac
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import get_settings

COOKIE = "srr_session"
CSRF_HEADER = "x-csrf-token"
MAX_AGE = 12 * 3600
_attempts: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()
LOGIN_WINDOW = 300
LOGIN_MAX = 5


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str, details=None, retryable: bool = False):
        super().__init__(status_code=status, detail={"code": code, "message": message, "details": details, "retryable": retryable})


def _serializer() -> URLSafeTimedSerializer:
    secret = get_settings().session_secret
    if not secret:
        raise ApiError(503, "session_not_configured", "Falta SESSION_SECRET en el servidor; el acceso de presentador está deshabilitado.")
    return URLSafeTimedSerializer(secret, salt="srr-presenter")


def presenter_configured() -> bool:
    s = get_settings()
    return bool(s.admin_password and s.session_secret)


def check_rate(ip: str) -> None:
    now = time.monotonic()
    with _lock:
        q = _attempts[ip]
        while q and now - q[0] > LOGIN_WINDOW:
            q.popleft()
        if len(q) >= LOGIN_MAX:
            raise ApiError(429, "too_many_attempts", "Demasiados intentos. Espera unos minutos.", retryable=True)
        q.append(now)


def verify_password(password: str) -> bool:
    expected = get_settings().admin_password
    return bool(expected) and hmac.compare_digest(password.encode(), expected.encode())


def issue_session() -> tuple[str, str]:
    csrf = secrets.token_urlsafe(24)
    return _serializer().dumps({"role": "presenter", "csrf": csrf}), csrf


def read_session(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE)
    if not token or not presenter_configured():
        return None
    try:
        data = _serializer().loads(token, max_age=MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return data if data.get("role") == "presenter" else None


def require_presenter(request: Request) -> dict:
    session = read_session(request)
    if session is None:
        raise ApiError(401, "presenter_required", "Acceso de presentador necesario para esta acción.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        header = request.headers.get(CSRF_HEADER, "")
        if not header or not hmac.compare_digest(header, session.get("csrf", "")):
            raise ApiError(403, "csrf_failed", "Token CSRF ausente o no válido. Recarga la página.")
    return session


Presenter = Depends(require_presenter)
