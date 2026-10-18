"""Interfaz común de proveedores LLM. Añadir OpenAI o Anthropic = un archivo nuevo con un LLMProvider y una variable."""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

log = logging.getLogger("srr.llm")
T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code  # unavailable | timeout | http_error | invalid_output | disabled
        self.message = message


class Adjudication(BaseModel):
    """Salida del LLM para un caso dudoso. `razonamiento` va primero para que razone antes de decidir."""
    model_config = ConfigDict(extra="forbid")
    razonamiento: str = Field(min_length=10, max_length=1200)
    vinculado: bool
    es_riesgo: bool
    urgente: bool
    confianza: Literal["alta", "media", "baja"]

    @model_validator(mode="after")
    def coherent(self):
        if self.urgente and not self.es_riesgo:
            raise ValueError("urgente solo puede ser true si es_riesgo")
        if self.es_riesgo and not self.vinculado:
            raise ValueError("es_riesgo exige vinculado")
        return self


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    texto: str = Field(min_length=20, max_length=2000)


@dataclass
class CallRecord:
    provider: str
    model: str
    purpose: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    attempts: int = 1
    outcome: str = "ok"
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"provider": self.provider, "model": self.model, "purpose": self.purpose, "latency_ms": self.latency_ms,
                "input_tokens": self.input_tokens, "output_tokens": self.output_tokens, "attempts": self.attempts,
                "outcome": self.outcome}


class LLMProvider:
    name = "base"

    def __init__(self, model: str, *, max_concurrency: int = 2, timeout: float = 45.0, max_tokens: int = 800):
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self._sem = threading.BoundedSemaphore(max(1, max_concurrency))

    # Cada proveedor implementa una única llamada que devuelve (texto, usage).
    def _complete(self, system: str, user: str, *, schema: dict | None, max_tokens: int) -> tuple[str, dict]:
        raise NotImplementedError

    def ping(self) -> bool:
        return True

    def structured(self, system: str, user: str, output: type[T], *, purpose: str, retries: int = 2) -> tuple[T, CallRecord]:
        """Salida JSON validada con Pydantic. Hasta `retries` reintentos si no valida; timeout cuenta como fallo."""
        schema = output.model_json_schema()
        attempts = 0
        t0 = time.monotonic()
        usage: dict = {}
        last = "sin respuesta"
        with self._sem:
            while attempts <= retries:
                attempts += 1
                text, usage = self._complete(system, user, schema=schema, max_tokens=self.max_tokens)
                try:
                    obj = output.model_validate(json.loads(_strip_fences(text)))
                except (ValueError, ValidationError) as exc:
                    last = str(exc)[:300]
                    log.warning("llm invalid output provider=%s model=%s purpose=%s attempt=%s", self.name, self.model, purpose, attempts)
                    continue
                rec = CallRecord(self.name, self.model, purpose, int((time.monotonic() - t0) * 1000),
                                 usage.get("prompt_tokens"), usage.get("completion_tokens"), attempts)
                log.info("llm call provider=%s model=%s purpose=%s outcome=ok attempts=%s latency_ms=%s in=%s out=%s",
                         self.name, self.model, purpose, attempts, rec.latency_ms, rec.input_tokens, rec.output_tokens)
                return obj, rec
        log.warning("llm call provider=%s model=%s purpose=%s outcome=invalid_output attempts=%s", self.name, self.model, purpose, attempts)
        raise LLMError("invalid_output", f"La respuesta no validó tras {attempts} intentos: {last}")


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):] if "{" in t else t
    return t
