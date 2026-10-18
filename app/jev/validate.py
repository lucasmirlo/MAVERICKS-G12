"""Validación estricta de respuestas de TypeSafe antes de aplicar la política.

Una clave ausente, un tipo inesperado o un valor fuera de rango es un error de análisis; nunca se sustituye por 0.
"""
from __future__ import annotations

import math


class InvalidJevResponse(Exception):
    def __init__(self, message: str, details: list[str]):
        super().__init__(message)
        self.message = message
        self.details = details


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def validate_answers(body: dict, response: dict) -> dict:
    """Devuelve answers normalizados {qid: {...}}; lanza InvalidJevResponse si algo no cuadra."""
    problems: list[str] = []
    answers = response.get("answers")
    if not isinstance(answers, dict):
        raise InvalidJevResponse("La respuesta JEV no contiene 'answers'.", ["answers ausente"])
    out = {}
    for qid, question in body["questions"].items():
        a = answers.get(qid)
        qtype = question["type"]
        if not isinstance(a, dict):
            problems.append(f"{qid}: respuesta ausente")
            continue
        if a.get("type") not in (None, qtype):
            problems.append(f"{qid}: tipo {a.get('type')} distinto de {qtype}")
            continue
        if qtype == "noul":
            v = a.get("noul")
            if not _finite(v) or not 0 <= v <= 1:
                problems.append(f"{qid}: noul no es un número finito en [0,1]")
                continue
            out[qid] = {"noul": float(v)}
        elif qtype == "choice":
            choice = a.get("choice")
            criteria = question["criteria"]
            if choice not in criteria:
                problems.append(f"{qid}: opción '{choice}' fuera de los criterios")
                continue
            conf = a.get("confidence")
            if conf is not None and (not _finite(conf) or not 0 <= conf <= 1):
                problems.append(f"{qid}: confidence fuera de rango")
                continue
            probs = a.get("probabilities")
            if probs is not None:
                if not isinstance(probs, dict) or any(not _finite(p) or p < 0 for p in probs.values()):
                    problems.append(f"{qid}: distribución inválida")
                    continue
                if probs and abs(sum(probs.values()) - 1) > 0.02:
                    problems.append(f"{qid}: la distribución no suma 1")
                    continue
            out[qid] = {"choice": choice, "confidence": float(conf) if conf is not None else None, "probabilities": probs}
        elif qtype == "score":
            score = a.get("score")
            levels = len(question["criteria"])
            if not _finite(score) or not 0 <= score <= levels - 1:
                problems.append(f"{qid}: score fuera de 0–{levels - 1}")
                continue
            conf = a.get("confidence")
            if conf is not None and (not _finite(conf) or not 0 <= conf <= 1):
                problems.append(f"{qid}: confidence fuera de rango")
                continue
            probs = a.get("probabilities")
            if probs is not None and (not isinstance(probs, dict) or any(not _finite(p) or p < 0 for p in probs.values())):
                problems.append(f"{qid}: distribución inválida")
                continue
            out[qid] = {"score": float(score), "confidence": float(conf) if conf is not None else None, "probabilities": probs}
    if problems:
        raise InvalidJevResponse("Respuesta JEV incompleta o inválida.", problems)
    return out
