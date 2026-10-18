"""Transporte de fixture para desarrollo de interfaz SIN clave JEV.

Solo se activa con DEMO_FIXTURES_ENABLED=true. Responde con la forma documentada de TypeSafe usando
heurísticas triviales (coincidencia literal del nombre). Los análisis quedan marcados engine_mode='fixture',
la interfaz muestra «Modo fixture» y la exportación final los rechaza. No es una inferencia real.
"""
from __future__ import annotations

import json
import re

import httpx

FIXTURE_MODEL = "fixture-local-0"
_RISK_WORDS = re.compile(r"fire|explosion|flood|strike|halt|shutdown|recall|ban|insolven|default|outage|closure|earthquake|storm|suspend|warning letter|contamina", re.I)
_URGENT_WORDS = re.compile(r"halt|shutdown|fire|explosion|suspend|closed|ban", re.I)
_RECOVERY_WORDS = re.compile(r"resum|restor|reopen|back to normal|lifted|recover", re.I)


def _answers(body: dict) -> dict:
    article = body["state"]["article"]
    text = f"{article.get('headline', '')} {article.get('summary', '')}"
    suppliers = {s["supplier_id"]: s for s in body["state"]["suppliers"]}
    answers = {}
    for qid, q in body["questions"].items():
        sid = qid.split("_", 1)[1] if "_" in qid else None
        if qid.startswith("impact_state_"):
            sid = qid[len("impact_state_"):]
        s = suppliers.get(sid or "", {})
        named = bool(s) and s.get("name", "").lower() in text.lower()
        if q["type"] == "noul":
            if qid.startswith("linked_"):
                v = 0.95 if named else 0.03
            elif qid.startswith("risk_"):
                v = 0.9 if _RISK_WORDS.search(text) and not _RECOVERY_WORDS.search(text) else 0.08
            else:
                v = 0.85 if _URGENT_WORDS.search(text) and not _RECOVERY_WORDS.search(text) else 0.1
            answers[qid] = {"type": "noul", "noul": v}
        elif q["type"] == "score":
            levels = len(q["criteria"])
            score = 7.0 if _URGENT_WORDS.search(text) else (4.0 if _RISK_WORDS.search(text) else 1.0)
            answers[qid] = {"type": "score", "score": min(score, levels - 1), "confidence": 0.8,
                            "legend": {str(i): c for i, c in enumerate(q["criteria"])},
                            "probabilities": {str(i): (1.0 if i == int(score) else 0.0) for i in range(levels)}}
        else:
            options = list(q["criteria"].keys())
            if qid == "event_type":
                pick = "recovery" if _RECOVERY_WORDS.search(text) else ("fire_incident" if re.search("fire", text, re.I) else ("other" if _RISK_WORDS.search(text) else "not_relevant"))
            elif qid == "event_state" or qid.startswith("impact_state_"):
                pick = "resolved" if _RECOVERY_WORDS.search(text) else ("active" if _RISK_WORDS.search(text) else "unrelated")
            elif qid.startswith("evidence_"):
                pick = next((o for o in options if o.startswith("e")), "none")
            else:
                pick = "unknown"
            pick = pick if pick in options else options[0]
            answers[qid] = {"type": "choice", "choice": pick, "confidence": 0.8,
                            "probabilities": {o: (1.0 if o == pick else 0.0) for o in options}}
    return answers


def handler(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    return httpx.Response(200, json={"model": FIXTURE_MODEL, "answers": _answers(body), "usage": {"input_tokens": 0, "output_tokens": 0}})


def transport() -> httpx.MockTransport:
    return httpx.MockTransport(handler)
