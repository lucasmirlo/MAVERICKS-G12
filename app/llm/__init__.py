"""Cliente LLM configurable por entorno (LLM_PROVIDER, LLM_MODEL, LLM_BASE_URL, LLM_API_KEY, LLM_TIMEOUT_SECONDS,
LLM_MAX_CONCURRENCY). El LLM nunca calcula riesgo, prioridad ni cifras: decide casos dudosos (adjudicate) o redacta
texto a partir de hechos ya calculados (draft)."""
from __future__ import annotations

import json
import logging
import threading
import time

from ..config import get_settings
from .base import Adjudication, CallRecord, Draft, LLMError, LLMProvider
from .prompts import ADJUDICATION_SYSTEM, CHALLENGE_DEFINITIONS, DRAFT_SYSTEM, PLAN_SYSTEM
from .providers import FakeProvider, NoneProvider, OllamaProvider

__all__ = ["Adjudication", "CallRecord", "Draft", "LLMError", "LLMProvider", "FakeProvider", "adjudicate", "draft",
           "plan_summary", "get_provider", "set_provider", "is_available", "status", "CHALLENGE_DEFINITIONS"]
log = logging.getLogger("srr.llm")
_lock = threading.Lock()
_provider: LLMProvider | None = None
_override = False
_availability: tuple[float, bool] = (0.0, False)
AVAILABILITY_TTL = 60.0


def _build() -> LLMProvider:
    cfg = get_settings().llm
    common = {"max_concurrency": cfg["max_concurrency"], "timeout": cfg["timeout"], "max_tokens": cfg["max_tokens"]}
    if cfg["provider"] in ("ollama", "compatible"):
        return OllamaProvider(cfg["model"], cfg["base_url"], cfg["api_key"], **common)
    if cfg["provider"] not in ("none", ""):
        log.warning("LLM_PROVIDER=%s no implementado aún; se usa none", cfg["provider"])
    return NoneProvider(**common)


def get_provider() -> LLMProvider:
    global _provider
    with _lock:
        if _provider is None:
            _provider = _build()
        return _provider


def set_provider(provider: LLMProvider | None) -> None:
    """Solo para pruebas: fija un proveedor (p. ej. FakeProvider) o vuelve al de la configuración con None."""
    global _provider, _override, _availability
    with _lock:
        _provider, _override, _availability = provider, provider is not None, (0.0, False)


def is_available(force: bool = False) -> bool:
    global _availability
    p = get_provider()
    if isinstance(p, NoneProvider):
        return False
    if _override:
        return True
    checked, ok = _availability
    if force or time.monotonic() - checked > AVAILABILITY_TTL:
        ok = p.ping()
        _availability = (time.monotonic(), ok)
    return ok


def status() -> dict:
    p = get_provider()
    return {"provider": p.name, "model": p.model, "available": is_available(), "max_concurrency": get_settings().llm["max_concurrency"]}


def _wrap(tag: str, payload: dict) -> str:
    return f"<<<{tag}>>>\n{json.dumps(payload, ensure_ascii=False, default=str)}\n<<<FIN_{tag}>>>"


def adjudicate(case: dict) -> tuple[Adjudication, CallRecord]:
    """Decide un caso dudoso. Lanza LLMError si no hay respuesta válida: quien llama conserva la regla."""
    payload = {**case, "definiciones": CHALLENGE_DEFINITIONS}
    return get_provider().structured(ADJUDICATION_SYSTEM, _wrap("CASO", payload), Adjudication, purpose="adjudicate")


def plan_summary(facts: dict, actions: list[dict]) -> tuple[str, CallRecord]:
    out, rec = get_provider().structured(PLAN_SYSTEM, _wrap("DATOS", {"hechos": facts, "acciones": actions}), Draft, purpose="plan_summary")
    return out.texto, rec


def draft(context: dict, template: str) -> tuple[str, CallRecord]:
    out, rec = get_provider().structured(DRAFT_SYSTEM, _wrap("CONTEXTO", context) + "\n" + _wrap("PLANTILLA", {"texto": template}),
                                         Draft, purpose="draft")
    return out.texto, rec
