"""JEV simulado con la forma documentada de respuesta de TypeSafe y catálogo sintético."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx

from app.models import Article, ArticleVersion, ImportBatch, Supplier
from app.textutil import content_hash

SYNTHETIC_SUPPLIERS = [
    dict(supplier_id="EXS01", name="Aster Labs", country="Spain", city="Madrid", category="API", material="Example API",
         criticality="High", single_source="Y", alternate_id=None, lead_days=90, inventory_days=30, share_category_pct=40),
    dict(supplier_id="EXS02", name="Boreal Packaging", country="France", city="Lyon", category="Primary packaging", material="Vials",
         criticality="Medium", single_source="N", alternate_id="EXS03", lead_days=45, inventory_days=20, share_category_pct=25),
    dict(supplier_id="EXS03", name="Cedar Glass", country="France", city="Lyon", category="Primary packaging", material="Vials",
         criticality="Medium", single_source="N", alternate_id="EXS02", lead_days=45, inventory_days=None, share_category_pct=15),
    dict(supplier_id="EXS04", name="Delta Freight", country="Netherlands", city="Rotterdam", category="Logistics", material="Road freight",
         criticality="High", single_source="N", alternate_id=None, lead_days=3, inventory_days=None, share_category_pct=37.3),
]


def add_catalog(db, suppliers=SYNTHETIC_SUPPLIERS):
    for s in suppliers:
        db.merge(Supplier(**s, data_issues=[]))
    db.commit()


def add_article(db, headline, summary, *, published="2026-10-01", news_id="N1", context_id="exercise", batch=None, row=0):
    if batch is None:
        batch = ImportBatch(kind="news", split="training", context_id=context_id, file_name="t.xlsx", sheet_name=f"S{news_id}",
                            file_sha256=news_id.ljust(64, "0"), columns=["News_ID", "Published_Date", "Source", "Headline", "Summary"], row_count=1)
        db.add(batch)
        db.flush()
    art = Article(context_id=context_id, origin="excel", batch_id=batch.id, row_index=row, external_id=news_id,
                  identity_key=f"batch:{batch.id}:{news_id}", source_name="Test", language="en",
                  published_at=datetime.fromisoformat(published).replace(tzinfo=timezone.utc), published_raw=published,
                  source_row={"News_ID": news_id})
    db.add(art)
    db.flush()
    v = ArticleVersion(article_id=art.id, version=1, headline=headline, summary=summary, content_hash=content_hash(headline, summary))
    db.add(v)
    db.flush()
    art.current_version_id = v.id
    db.commit()
    return art, v, batch


class ScriptedJev:
    """Transporte httpx que responde según un guion por proveedor y registra cada petición enviada."""

    def __init__(self, suppliers: dict | None = None, event_type="fire_incident", event_state="active", status_codes=None,
                 confidence=0.9, model="jev-1.13.0"):
        self.suppliers = suppliers or {}
        self.event_type = event_type
        self.event_state = event_state
        self.status_codes = list(status_codes or [])
        self.confidence = confidence
        self.model = model
        self.requests: list[dict] = []
        self.raw: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.raw.append(request)
        body = json.loads(request.content)
        self.requests.append(body)
        if self.status_codes:
            code = self.status_codes.pop(0)
            if code != 200:
                return httpx.Response(code, json={"error": "scripted"}, headers={"retry-after": "0"} if code == 429 else {})
        answers = {}
        for qid, q in body["questions"].items():
            kind, _, sid = qid.partition("_")
            if qid.startswith("impact_state_"):
                kind, sid = "impact", qid[len("impact_state_"):]
            cfg = self.suppliers.get(sid, {})
            if q["type"] == "noul":
                value = {"linked": cfg.get("link", 0.02), "risk": cfg.get("risk", 0.05), "urgent": cfg.get("urgent", 0.05)}[kind]
                answers[qid] = {"type": "noul", "noul": value}
            elif q["type"] == "score":
                answers[qid] = {"type": "score", "score": cfg.get("severity", 8) - 1, "confidence": cfg.get("severity_conf", self.confidence),
                                "legend": {str(i): c for i, c in enumerate(q["criteria"])},
                                "probabilities": {str(i): 0.1 for i in range(10)}}
            else:
                if qid == "event_type":
                    choice = self.event_type
                elif qid == "event_state":
                    choice = self.event_state
                elif kind == "impact":
                    choice = cfg.get("impact", "active")
                elif kind == "evidence":
                    choice = cfg.get("evidence", "e1")
                else:
                    choice = cfg.get("duration", "unknown")
                opts = list(q["criteria"].keys())
                answers[qid] = {"type": "choice", "choice": choice, "confidence": self.confidence,
                                "probabilities": {o: (1.0 if o == choice else 0.0) for o in opts}}
        return httpx.Response(200, json={"model": self.model, "answers": answers, "usage": {"input_tokens": 100, "output_tokens": 5}})

    def client(self):
        from app.jev.client import JevClient
        return JevClient(api_key="test-key", transport=httpx.MockTransport(self), sleep=lambda s: None)
