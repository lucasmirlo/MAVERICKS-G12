"""Proveedores LLM disponibles: ollama (API compatible con OpenAI), none y fake (tests)."""
from __future__ import annotations

import time
from collections.abc import Callable

import httpx

from .base import LLMError, LLMProvider


class OllamaProvider(LLMProvider):
    """Ollama por su API compatible con OpenAI (/v1). Desactiva el pensamiento propio de Qwen con
    reasoning_effort="none" (nuestro campo `razonamiento` cumple esa función) y limita la salida."""
    name = "ollama"

    def __init__(self, model: str, base_url: str, api_key: str = "", **kw):
        super().__init__(model, **kw)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def ping(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/v1/models", headers=self._headers(), timeout=3)
            return r.status_code == 200 and any(m.get("id") == self.model for m in r.json().get("data", []))
        except (httpx.HTTPError, ValueError):
            return False

    def _complete(self, system: str, user: str, *, schema: dict | None, max_tokens: int) -> tuple[str, dict]:
        body = {"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": 0, "max_tokens": max_tokens, "reasoning_effort": "none"}
        if schema is not None:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "salida", "schema": schema, "strict": True}}
        try:
            r = httpx.post(f"{self.base_url}/v1/chat/completions", json=body, headers=self._headers(), timeout=self.timeout)
        except httpx.TimeoutException as exc:
            raise LLMError("timeout", f"El LLM no respondió en {self.timeout:.0f} s.") from exc
        except httpx.TransportError as exc:
            raise LLMError("unavailable", f"No se pudo conectar con el LLM ({exc.__class__.__name__}).") from exc
        if r.status_code != 200:
            raise LLMError("http_error", f"El LLM devolvió HTTP {r.status_code}.")
        data = r.json()
        return (data["choices"][0]["message"].get("content") or ""), (data.get("usage") or {})


class NoneProvider(LLMProvider):
    name = "none"

    def __init__(self, **kw):
        super().__init__("none", **kw)

    def ping(self) -> bool:
        return False

    def _complete(self, *a, **kw):
        raise LLMError("disabled", "No hay LLM configurado (LLM_PROVIDER=none).")


class FakeProvider(LLMProvider):
    """Proveedor de pruebas: `responder(system, user)` devuelve el texto o lanza; `delay` simula latencia."""
    name = "fake"

    def __init__(self, responder: Callable[[str, str], str], delay: float = 0.0, timeout: float = 45.0, **kw):
        super().__init__("fake-model", timeout=timeout, **kw)
        self.responder = responder
        self.delay = delay
        self.calls: list[tuple[str, str]] = []

    def _complete(self, system: str, user: str, *, schema: dict | None, max_tokens: int) -> tuple[str, dict]:
        self.calls.append((system, user))
        if self.delay > self.timeout:
            raise LLMError("timeout", f"El LLM no respondió en {self.timeout:.0f} s.")
        if self.delay:
            time.sleep(self.delay)
        return self.responder(system, user), {"prompt_tokens": len(user) // 4, "completion_tokens": 50}
