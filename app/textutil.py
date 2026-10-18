"""Utilidades de texto: normalización, hash, saneado HTML, frases y duraciones explícitas."""
from __future__ import annotations

import hashlib
import html
import re

import bleach

_WS = re.compile(r"\s+")


def normalize_space(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


def content_hash(headline: str, summary: str) -> str:
    return hashlib.sha256(f"{normalize_space(headline)}\n{normalize_space(summary)}".encode("utf-8")).hexdigest()


def html_to_text(value: str | None, limit: int = 4000) -> str:
    """Elimina todas las etiquetas y entidades; el frontend nunca recibe HTML de terceros."""
    if not value:
        return ""
    cleaned = bleach.clean(value, tags=[], attributes={}, strip=True, strip_comments=True)
    text = normalize_space(html.unescape(cleaned))
    return text[:limit]


def sentences(article: dict) -> list[dict]:
    """Fragmentos literales indexados por campo (idéntico a reference/jev_requests.py)."""
    out = []
    for field in ["headline", "summary"]:
        text = article.get(field, "") or ""
        start = 0
        for match in re.finditer(r"(?<=[.!?])\s+", text):
            end = match.start()
            if text[start:end].strip():
                out.append({"id": f"e{len(out) + 1}", "field": field, "start": start, "end": end, "text": text[start:end]})
            start = match.end()
        if text[start:].strip():
            out.append({"id": f"e{len(out) + 1}", "field": field, "start": start, "end": len(text), "text": text[start:]})
    return out


_NUMBER_WORDS = {
    "one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fourteen": 14, "fifteen": 15, "twenty": 20, "thirty": 30,
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
    "nueve": 9, "diez": 10, "quince": 15, "veinte": 20, "treinta": 30, "several": None, "few": None,
}
_UNITS = {
    "day": 1, "days": 1, "día": 1, "días": 1, "dia": 1, "dias": 1,
    "week": 7, "weeks": 7, "semana": 7, "semanas": 7,
    "month": 30, "months": 30, "mes": 30, "meses": 30,
    "year": 365, "years": 365, "año": 365, "años": 365,
    "hour": 1 / 24, "hours": 1 / 24, "hora": 1 / 24, "horas": 1 / 24,
}
_LOWER_BOUND = re.compile(r"(at least|minimum of|a minimum|more than|over|no less than|al menos|como mínimo|más de|mínimo)\s*$", re.I)
_DURATION = re.compile(
    r"\b(?P<num>\d+(?:[.,]\d+)?|" + "|".join(k for k in _NUMBER_WORDS if _NUMBER_WORDS[k]) + r")"
    r"(?:\s*(?:-|to|a|–)\s*(?P<num2>\d+(?:[.,]\d+)?))?"
    r"[\s-]*(?P<unit>" + "|".join(sorted(_UNITS, key=len, reverse=True)) + r")\b",
    re.I,
)


def duration_candidates(article: dict) -> list[dict]:
    """Candidatos de duración encontrados literalmente en el texto. JEV elige uno o 'unknown'."""
    out = []
    seen = set()
    for field in ("headline", "summary"):
        text = article.get(field) or ""
        for m in _DURATION.finditer(text):
            raw = m.group("num").lower().replace(",", ".")
            value = float(raw) if raw[0].isdigit() else _NUMBER_WORDS.get(raw)
            if value is None:
                continue
            if m.group("num2"):
                value = float(m.group("num2").replace(",", "."))  # rango: se toma el extremo superior declarado
            days = round(value * _UNITS[m.group("unit").lower()], 3)
            if days <= 0:
                continue
            prefix = text[max(0, m.start() - 24): m.start()]
            lower = bool(_LOWER_BOUND.search(prefix))
            key = (field, m.start())
            if key in seen:
                continue
            seen.add(key)
            out.append({"id": f"d{len(out) + 1}", "text": text[m.start(): m.end()], "days": days,
                        "is_lower_bound": lower, "field": field, "start": m.start(), "end": m.end()})
    return out
