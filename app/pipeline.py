"""Análisis de un artículo: etapa A (vínculo con los 40 proveedores) → etapa B (parejas candidatas) → política.

El contexto de inferencia se construye exclusivamente con ArticleVersion (titular, resumen) y metadatos de
entrada. Las etiquetas viven en evaluation_labels y este módulo no las importa.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import scoring
from .config import get_settings, location_enrichment
from .db import utcnow
from .jev import fixture
from .jev.client import JevClient, JevError
from .jev.questions import QUESTION_VERSION, request_hash, stage_a, stage_b
from .jev.validate import InvalidJevResponse, validate_answers
from .models import Analysis, Article, ArticleVersion, JevCall, Supplier, SupplierAssessment
from .policy import active_policy
from .textutil import duration_candidates, sentences

log = logging.getLogger("srr.pipeline")


def engine_mode() -> str:
    s = get_settings()
    if s.jev_configured:
        return "jev"
    if s.demo_fixtures_enabled:
        return "fixture"
    return "unconfigured"


def make_client(mode: str | None = None) -> JevClient:
    mode = mode or engine_mode()
    if mode == "fixture":
        return JevClient(api_key="fixture-no-network", base_url="https://fixture.invalid", transport=fixture.transport())
    return JevClient()


def requested_model(mode: str) -> str:
    return fixture.FIXTURE_MODEL if mode == "fixture" else get_settings().jev_model


def _num(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def location_context(s: Supplier) -> tuple[str | None, str | None]:
    """Contexto geográfico inferido (tabla de enriquecimiento con procedencia); nunca sustituye City/Country."""
    enr = location_enrichment()
    city = enr.get("cities", {}).get(f"{s.city}|{s.country}")
    loc = None
    if city:
        loc = city["region"] + ("; " + ", ".join(city["features"]) if city.get("features") else "") + " (inferred, not facility-verified)"
    return loc, enr.get("service_scope", {}).get(s.material or "")


def supplier_state(s: Supplier, names: dict[str, str]) -> dict:
    loc, scope = location_context(s)
    return {
        "location_context_inferred": loc, "service_scope": scope,
        "supplier_id": s.supplier_id, "name": s.name, "country": s.country, "city": s.city, "category": s.category,
        "material": s.material, "criticality": s.criticality, "single_source": s.single_source,
        "alternate_id": s.alternate_id, "alternate_name": names.get(s.alternate_id) if s.alternate_id else None,
        "lead_days": _num(s.lead_days), "inventory_days": _num(s.inventory_days),
        "share_category_pct": _num(s.share_category_pct),
    }


def article_state(article: Article, version: ArticleVersion) -> dict:
    published = article.published_at.astimezone(timezone.utc).date().isoformat() if article.published_at else (article.published_raw or "")
    return {
        "news_id": article.external_id if article.origin == "excel" else article.id,
        "published_date": published,
        "source": article.source_name or "",
        "headline": version.headline,
        "summary": version.summary,
        "language": article.language,
        "context_id": article.context_id,
    }


def _call(db: Session, client: JevClient, body: dict, stage: str, question_version: str, mode: str, deadline: float):
    h = request_hash(body, question_version)
    cached = db.get(JevCall, h)
    if cached is not None and cached.engine_mode == mode:
        return cached.response, h, True, cached
    result = client.decide(body, deadline=deadline)
    validate_answers(body, result.response)  # una respuesta inválida no entra en la caché
    row = JevCall(request_hash=h, stage=stage, requested_model=body["model"], model=result.model, engine_mode=mode,
                  response=result.response, usage=result.usage, duration_ms=result.duration_ms, attempts=result.attempts)
    db.merge(row)
    db.commit()  # una respuesta válida se conserva aunque falle la etapa siguiente
    return result.response, h, False, row


def get_or_create_analysis(db: Session, article: Article, version: ArticleVersion, policy: dict, mode: str) -> Analysis:
    model = requested_model(mode)
    qv = QUESTION_VERSION
    row = db.scalar(select(Analysis).where(
        Analysis.article_version_id == version.id, Analysis.requested_model == model,
        Analysis.question_version == qv, Analysis.policy_version == policy["version"], Analysis.engine_mode == mode))
    if row is None:
        row = Analysis(article_id=article.id, article_version_id=version.id, context_id=article.context_id,
                       engine_mode=mode, requested_model=model, question_version=qv, policy_version=policy["version"])
        db.add(row)
        db.flush()
    return row


def analyze_version(db: Session, version_id: str, *, client: JevClient | None = None, force: bool = False) -> Analysis:
    settings = get_settings()
    mode = engine_mode()
    version = db.get(ArticleVersion, version_id)
    if version is None:
        raise ValueError(f"article version {version_id} not found")
    article = db.get(Article, version.article_id)
    policy = active_policy(db)
    analysis = get_or_create_analysis(db, article, version, policy, mode)
    if analysis.status in ("done", "review") and not force:
        return analysis
    analysis.status = "running"
    analysis.started_at = utcnow()
    analysis.error_code = analysis.error_message = None
    analysis.retryable = None
    db.commit()

    if mode == "unconfigured":
        return _fail(db, analysis, JevError("engine_not_configured", "Motor sin configurar: falta TYPESAFE_API_KEY.", attempts=0))

    client = client or make_client(mode)
    t0 = time.monotonic()
    deadline = t0 + settings.jev_article_budget_seconds
    suppliers = list(db.scalars(select(Supplier).order_by(Supplier.supplier_id)))
    if not suppliers:
        return _fail(db, analysis, JevError("catalog_missing", "No hay catálogo de proveedores importado.", attempts=0))
    names = {s.supplier_id: s.name for s in suppliers}
    by_id = {s.supplier_id: s for s in suppliers}
    art = article_state(article, version)
    spans = sentences(art)
    durations = duration_candidates(art)
    model = requested_model(mode)
    thresholds = policy["thresholds"]
    review_reasons: list[str] = []
    attempts = 0
    usage = {"input_tokens": 0, "output_tokens": 0}
    try:
        body_a = stage_a(policy, art, [supplier_state(s, names) for s in suppliers], model)
        resp_a, hash_a, cached_a, call_a = _call(db, client, body_a, "A", QUESTION_VERSION, mode, deadline)
        answers_a = validate_answers(body_a, resp_a)
        attempts += call_a.attempts if not cached_a else 0
        _add_usage(usage, resp_a.get("usage"))
        returned_models = {resp_a.get("model")}
        link_scores = {sid: answers_a[f"linked_{sid}"]["noul"] for sid in by_id}
        event_type = answers_a["event_type"]["choice"]
        event_type_conf = answers_a["event_type"]["confidence"]
        event_state = answers_a["event_state"]["choice"]
        if event_type_conf is not None and event_type_conf < thresholds["choice_score_confidence"]:
            review_reasons.append("low_event_type_confidence")
        candidates = sorted(sid for sid, p in link_scores.items() if p >= thresholds["review_low"])
        answers_b: dict = {}
        hash_b = None
        cached_b = True
        if candidates:
            body_b = stage_b(policy, art, [supplier_state(by_id[sid], names) for sid in candidates], durations, model)
            resp_b, hash_b, cached_b, call_b = _call(db, client, body_b, "B", QUESTION_VERSION, mode, deadline)
            answers_b = validate_answers(body_b, resp_b)
            attempts += call_b.attempts if not cached_b else 0
            _add_usage(usage, resp_b.get("usage"))
            returned_models.add(resp_b.get("model"))
    except JevError as exc:
        db.rollback()
        return _fail(db, db.get(Analysis, analysis.id), exc)
    except InvalidJevResponse as exc:
        db.rollback()
        err = JevError("invalid_response", exc.message + " " + "; ".join(exc.details[:5]), retryable=False)
        return _fail(db, db.get(Analysis, analysis.id), err)

    returned_models.discard(None)
    model_id = sorted(returned_models)[0] if returned_models else None
    if mode == "jev" and returned_models and returned_models != {model}:
        review_reasons.append("unexpected_model_version")

    analysis.assessments.clear()
    db.flush()
    span_ids = {s["id"] for s in spans}
    dur_by_id = {d["id"]: d for d in durations}
    for sid in candidates:
        assessment = build_assessment(policy, by_id[sid], answers_b, link_scores[sid], event_type, span_ids, dur_by_id,
                                      link_basis=link_basis(by_id[sid], art))
        assessment.article_id = article.id
        assessment.context_id = article.context_id
        analysis.assessments.append(assessment)

    accepted = [a for a in analysis.assessments if a.accepted]
    analysis.affected_supplier_ids = sorted({a.supplier_id for a in accepted})
    analysis.is_risk = "Y" if any(a.is_risk == "Y" for a in accepted) else "N"
    analysis.urgent = "Y" if any(a.is_risk == "Y" and a.urgent == "Y" for a in accepted) else "N"
    for a in analysis.assessments:
        for reason in a.review_reasons:
            tag = f"{a.supplier_id}:{reason}"
            if tag not in review_reasons:
                review_reasons.append(tag)
    analysis.status = "review" if review_reasons else "done"
    analysis.review_reasons = review_reasons
    analysis.event_type = event_type
    analysis.event_type_confidence = event_type_conf
    analysis.event_state = event_state
    analysis.link_scores = link_scores
    analysis.evidence = spans
    analysis.duration_candidates = durations
    analysis.model_id = model_id
    analysis.request_hash_a = hash_a
    analysis.request_hash_b = hash_b
    analysis.cached = bool(cached_a and cached_b)
    analysis.usage = usage
    analysis.jev_attempts = attempts
    analysis.duration_ms = int((time.monotonic() - t0) * 1000)
    analysis.finished_at = utcnow()
    db.commit()
    log.info("analysis done article=%s status=%s risk=%s urgent=%s ids=%s ms=%s cached=%s", article.id, analysis.status,
             analysis.is_risk, analysis.urgent, analysis.affected_supplier_ids, analysis.duration_ms, analysis.cached)
    return analysis


def _add_usage(total: dict, usage) -> None:
    if isinstance(usage, dict):
        for k in ("input_tokens", "output_tokens"):
            if isinstance(usage.get(k), int):
                total[k] += usage[k]


def _fail(db: Session, analysis: Analysis, exc: JevError) -> Analysis:
    analysis.assessments.clear()
    analysis.status = "error"
    analysis.is_risk = None
    analysis.urgent = None
    analysis.affected_supplier_ids = []
    analysis.error_code = exc.code
    analysis.error_message = exc.message
    analysis.retryable = exc.retryable
    analysis.jev_attempts = exc.attempts
    analysis.finished_at = utcnow()
    db.commit()
    log.warning("analysis error article=%s code=%s retryable=%s", analysis.article_id, exc.code, exc.retryable)
    raise AnalysisFailed(analysis, exc)


class AnalysisFailed(Exception):
    def __init__(self, analysis: Analysis, error: JevError):
        super().__init__(error.message)
        self.analysis = analysis
        self.error = error


_LEGAL = re.compile(r"(?<![\w.])(ltd|gmbh|ag|spa|s\.p\.a|co|inc|sl|as|sp\. z o\.o|llc|plc|sa)\.?(?!\w)", re.I)


def link_basis(s: Supplier, art: dict) -> str:
    """identity: el nombre propio aparece; location_explicit: su ciudad aparece; inferred_region: solo región/ruta inferida."""
    text = f"{art.get('headline', '')} {art.get('summary', '')}".lower()
    core = re.sub(r"\s+", " ", _LEGAL.sub(" ", s.name)).strip().lower()
    if core and core in text:
        return "identity"
    if s.city and re.search(r"\b" + re.escape(s.city.lower()) + r"\b", text):
        return "location_explicit"
    return "inferred_region"


def build_assessment(policy: dict, s: Supplier, answers: dict, p_link: float, event_type: str,
                     span_ids: set[str], durations: dict[str, dict], link_basis: str = "identity") -> SupplierAssessment:
    sid = s.supplier_id
    t = policy["thresholds"]
    p_risk = answers[f"risk_{sid}"]["noul"]
    p_urgent = answers[f"urgent_{sid}"]["noul"]
    sev = answers[f"severity_{sid}"]
    impact = answers[f"impact_state_{sid}"]
    evidence = answers[f"evidence_{sid}"]["choice"]
    duration_choice = answers[f"duration_{sid}"]["choice"]
    severity = round(1 + sev["score"], 4)
    impact_status = impact["choice"]
    reasons: list[str] = []
    dec = scoring.decisions(policy, p_link=p_link, p_risk=p_risk, p_urgent=p_urgent, impact_status=impact_status)
    reasons += dec["review_reasons"]
    accepted = dec["linked"]
    is_risk = dec["is_risk"] == "Y"
    if accepted and impact["confidence"] is not None and impact["confidence"] < t["choice_score_confidence"]:
        reasons.append("low_impact_state_confidence")
    if is_risk and sev["confidence"] is not None and sev["confidence"] < t["choice_score_confidence"]:
        reasons.append("low_severity_confidence")
    evidence_ids = [evidence] if evidence in span_ids else []
    if is_risk and not evidence_ids:
        reasons.append("no_evidence")
    duration = durations.get(duration_choice)
    disruption_days = duration["days"] if duration else None
    applicability = scoring.inventory_applicability(policy, s.category)
    result = None
    try:
        result = scoring.priority(policy, is_risk=is_risk, severity=severity if is_risk else None,
                                  criticality=s.criticality, single_source=s.single_source,
                                  share_category_pct=s.share_category_pct, inventory_days=s.inventory_days,
                                  lead_days=s.lead_days, disruption_days=disruption_days,
                                  inventory_applicability=applicability, active=True)
    except ValueError as exc:
        reasons.append("invalid_supplier_data")
        log.warning("invalid supplier data %s: %s", sid, exc)
    if s.data_issues and accepted:
        reasons.append("supplier_data_issue")
    if result and is_risk:
        reasons += [w for w in result["warnings"]]
        if result["priority"] is None:
            reasons.append("priority_unavailable")
    reasons = list(dict.fromkeys(reasons))
    needs_review = bool(reasons)
    hist = result["priority"] if result else None
    active_priority = 0.0 if impact_status == "resolved" else hist
    is_recovery = accepted and (impact_status == "resolved" or event_type == "recovery")
    return SupplierAssessment(
        supplier_id=sid, accepted=accepted, p_link=p_link, p_risk=p_risk, p_urgent=p_urgent,
        is_risk=dec["is_risk"], urgent=dec["urgent"], severity=severity if is_risk else None,
        severity_confidence=sev["confidence"], impact_status=impact_status, impact_confidence=impact["confidence"],
        priority=hist, active_priority=active_priority,
        priority_band=scoring.band(policy, active_priority) if active_priority is not None else None,
        exposure=result["exposure"] if result else None,
        factor_values=result["factors"] if result else {}, contributions=result["contributions"] if result else {},
        needs_review=needs_review, review_reasons=reasons, evidence_ids=evidence_ids,
        duration_days=disruption_days, duration_is_lower_bound=bool(duration and duration.get("is_lower_bound")),
        # Un vínculo solo inferido por región/ruta se muestra como tal y no habilita sonido automático.
        sound_eligible=bool(dec["sound_eligible"] and not needs_review and link_basis != "inferred_region"), is_recovery=is_recovery,
        link_basis=link_basis,
        policy_version=policy["version"],
    )
