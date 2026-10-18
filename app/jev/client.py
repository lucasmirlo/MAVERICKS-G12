"""Cliente HTTP de TypeSafe JEV: POST {JEV_BASE_URL}/v1/systemone con Bearer.

Reintentos acotados para 429, 529, 5xx y errores de conexión; 400/401/413/415/422 no se reintentan.
Nunca registra la cabecera Authorization ni la clave.
"""
from __future__ import annotations

import logging
import math
import random
import threading
import time
from dataclasses import dataclass, field

import httpx

from ..config import get_settings

log = logging.getLogger("srr.jev")

RETRYABLE_STATUS = {429, 500, 502, 503, 504, 529}
_semaphore: threading.BoundedSemaphore | None = None
_sem_lock = threading.Lock()


def _sem() -> threading.BoundedSemaphore:
    global _semaphore
    with _sem_lock:
        if _semaphore is None:
            _semaphore = threading.BoundedSemaphore(max(1, get_settings().jev_max_concurrency))
        return _semaphore


class JevError(Exception):
    def __init__(self, code: str, message: str, *, status: int | None = None, retryable: bool = False, attempts: int = 1):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable
        self.attempts = attempts


@dataclass
class JevResult:
    response: dict
    model: str | None
    usage: dict | None
    duration_ms: int
    attempts: int
    status: int = 200
    extra: dict = field(default_factory=dict)


ERROR_MESSAGES = {
    400: ("bad_request", "JEV rechazó la petición (400). Revisa tamaño de contexto o formato de preguntas."),
    401: ("unauthorized", "JEV devolvió 401: clave ausente o no válida en TYPESAFE_API_KEY."),
    403: ("forbidden", "JEV devolvió 403: la cuenta no tiene acceso a este recurso o modelo."),
    404: ("not_found", "JEV devolvió 404: endpoint o modelo no encontrado."),
    413: ("payload_too_large", "JEV devolvió 413: la petición supera 32 MiB."),
    415: ("unsupported_encoding", "JEV devolvió 415: codificación no admitida."),
    422: ("validation_error", "JEV devolvió 422: la petición no superó la validación del proveedor."),
    429: ("rate_limited", "JEV devolvió 429: límite de uso excedido tras los reintentos permitidos."),
    529: ("overloaded", "JEV devolvió 529: servicio temporalmente sobrecargado."),
}


def _retry_after(resp: httpx.Response) -> float | None:
    value = resp.headers.get("retry-after")
    if not value:
        return None
    try:
        seconds = float(value)
        return seconds if math.isfinite(seconds) and seconds >= 0 else None
    except ValueError:
        return None


class JevClient:
    def __init__(self, *, api_key: str | None = None, base_url: str | None = None, timeout: float | None = None,
                 max_retries: int | None = None, transport: httpx.BaseTransport | None = None,
                 sleep=time.sleep):
        s = get_settings()
        self.api_key = api_key if api_key is not None else s.typesafe_api_key
        self.base_url = (base_url or s.jev_base_url).rstrip("/")
        self.timeout = timeout or s.jev_timeout_seconds
        self.max_retries = s.jev_max_retries if max_retries is None else max_retries
        self.transport = transport
        self.sleep = sleep

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/v1/systemone"

    def decide(self, body: dict, *, deadline: float | None = None) -> JevResult:
        if not self.api_key:
            raise JevError("engine_not_configured", "Motor sin configurar: falta TYPESAFE_API_KEY.", retryable=False, attempts=0)
        attempts = 0
        started = time.monotonic()
        last_error: JevError | None = None
        with httpx.Client(timeout=httpx.Timeout(self.timeout, connect=min(10.0, self.timeout)), transport=self.transport,
                          follow_redirects=False) as client:
            while attempts <= self.max_retries:
                attempts += 1
                if deadline is not None and time.monotonic() >= deadline:
                    raise JevError("article_budget_exceeded", "Se agotó el presupuesto de 60 s por artículo.", retryable=True, attempts=attempts - 1)
                wait = None
                try:
                    with _sem():
                        t0 = time.monotonic()
                        resp = client.post(self.endpoint, json=body, headers={
                            "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                            "Accept": "application/json", "User-Agent": "supplier-risk-radar/1.0"})
                        elapsed = int((time.monotonic() - t0) * 1000)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    code = "timeout" if isinstance(exc, httpx.TimeoutException) else "connection_error"
                    last_error = JevError(code, f"No se pudo completar la llamada a JEV ({exc.__class__.__name__}).", retryable=True, attempts=attempts)
                    log.warning("jev call failed code=%s attempt=%s", code, attempts)
                else:
                    log.info("jev call status=%s attempt=%s duration_ms=%s", resp.status_code, attempts, elapsed)
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                        except ValueError as exc:
                            raise JevError("invalid_json", "JEV devolvió un cuerpo que no es JSON.", status=200, attempts=attempts) from exc
                        if not isinstance(data, dict):
                            raise JevError("invalid_json", "La respuesta JEV no es un objeto JSON.", status=200, attempts=attempts)
                        return JevResult(response=data, model=data.get("model"), usage=data.get("usage"),
                                         duration_ms=int((time.monotonic() - started) * 1000), attempts=attempts)
                    code, message = ERROR_MESSAGES.get(resp.status_code, (f"http_{resp.status_code}", f"JEV devolvió HTTP {resp.status_code}."))
                    retryable = resp.status_code in RETRYABLE_STATUS
                    last_error = JevError(code, message, status=resp.status_code, retryable=retryable, attempts=attempts)
                    if not retryable:
                        raise last_error
                    wait = _retry_after(resp)
                if attempts > self.max_retries:
                    break
                delay = wait if wait is not None else min(8.0, 1.0 * (2 ** (attempts - 1))) + random.uniform(0, 0.5)
                if deadline is not None:
                    delay = min(delay, max(0.0, deadline - time.monotonic()))
                self.sleep(min(delay, 20.0))
        assert last_error is not None
        last_error.attempts = attempts
        raise last_error
