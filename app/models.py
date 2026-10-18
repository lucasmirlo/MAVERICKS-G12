"""Modelo persistente. Fechas en UTC; etiquetas de evaluación en tabla separada."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow

CONTEXT_EXERCISE = "exercise"
CONTEXT_RSS = "rss"
CONTEXT_FIXTURE = "fixture_demo"
CONTEXTS = (CONTEXT_EXERCISE, CONTEXT_RSS, CONTEXT_FIXTURE)


def new_id() -> str:
    return str(uuid.uuid4())


def ts(**kw):
    return mapped_column(DateTime(timezone=True), **kw)


class Supplier(Base):
    __tablename__ = "suppliers"
    supplier_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[Optional[str]] = mapped_column(String(80))
    material: Mapped[Optional[str]] = mapped_column(String(200))
    country: Mapped[Optional[str]] = mapped_column(String(80))
    city: Mapped[Optional[str]] = mapped_column(String(120))
    annual_spend_eur: Mapped[Optional[float]] = mapped_column(Float)
    share_category_pct: Mapped[Optional[float]] = mapped_column(Float)
    single_source: Mapped[Optional[str]] = mapped_column(String(1))
    alternate_id: Mapped[Optional[str]] = mapped_column(String(32))
    lead_days: Mapped[Optional[float]] = mapped_column(Float)
    inventory_days: Mapped[Optional[float]] = mapped_column(Float)
    criticality: Mapped[Optional[str]] = mapped_column(String(16))
    quality_score: Mapped[Optional[float]] = mapped_column(Float)
    row_index: Mapped[int] = mapped_column(Integer, default=0)
    data_issues: Mapped[list] = mapped_column(JSONB, default=list)
    catalog_batch_id: Mapped[Optional[str]] = mapped_column(String(36))
    updated_at: Mapped[datetime] = ts(default=utcnow, onupdate=utcnow)


class Material(Base):
    __tablename__ = "materials"
    material_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[Optional[str]] = mapped_column(String(80))
    primary_supplier_id: Mapped[Optional[str]] = mapped_column(String(32))
    alternate_supplier_id: Mapped[Optional[str]] = mapped_column(String(32))
    monthly_requirement: Mapped[Optional[float]] = mapped_column(Float)
    unit: Mapped[Optional[str]] = mapped_column(String(32))
    row_index: Mapped[int] = mapped_column(Integer, default=0)


class MaterialProduct(Base):
    __tablename__ = "material_products"
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.material_id", ondelete="CASCADE"), primary_key=True)
    product: Mapped[str] = mapped_column(String(200), primary_key=True)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8), default="en")
    topic: Mapped[Optional[str]] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    poll_seconds: Mapped[int] = mapped_column(Integer, default=300)
    etag: Mapped[Optional[str]] = mapped_column(Text)
    last_modified: Mapped[Optional[str]] = mapped_column(Text)
    last_attempt_at: Mapped[Optional[datetime]] = ts(nullable=True)
    last_success_at: Mapped[Optional[datetime]] = ts(nullable=True)
    last_status: Mapped[Optional[int]] = mapped_column(Integer)
    last_outcome: Mapped[Optional[str]] = mapped_column(String(32))  # ok | not_modified | error
    last_item_count: Mapped[Optional[int]] = mapped_column(Integer)
    last_new_count: Mapped[Optional[int]] = mapped_column(Integer)
    last_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_errors: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    lease_owner: Mapped[Optional[str]] = mapped_column(String(80))
    lease_until: Mapped[Optional[datetime]] = ts(nullable=True)
    initial_done: Mapped[bool] = mapped_column(Boolean, default=False)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16))  # catalog | news
    split: Mapped[Optional[str]] = mapped_column(String(16))  # training | validation | test | liveday | other
    context_id: Mapped[str] = mapped_column(String(32), default=CONTEXT_EXERCISE)
    file_name: Mapped[str] = mapped_column(String(255))
    sheet_name: Mapped[str] = mapped_column(String(64))
    file_sha256: Mapped[str] = mapped_column(String(64))
    columns: Mapped[list] = mapped_column(JSONB, default=list)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    has_labels: Mapped[bool] = mapped_column(Boolean, default=False)
    logical_date: Mapped[Optional[datetime]] = ts(nullable=True)
    diagnostics: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = ts(default=utcnow)
    analysis_requested_at: Mapped[Optional[datetime]] = ts(nullable=True)
    analysis_completed_at: Mapped[Optional[datetime]] = ts(nullable=True)
    __table_args__ = (UniqueConstraint("file_sha256", "sheet_name", "context_id", name="uq_batch_file_sheet"),)


class Article(Base):
    __tablename__ = "articles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    context_id: Mapped[str] = mapped_column(String(32), index=True)
    origin: Mapped[str] = mapped_column(String(16))  # excel | rss | fixture
    batch_id: Mapped[Optional[str]] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), index=True)
    row_index: Mapped[Optional[int]] = mapped_column(Integer)
    external_id: Mapped[str] = mapped_column(String(512))  # News_ID o GUID
    identity_key: Mapped[str] = mapped_column(String(600))
    source_id: Mapped[Optional[str]] = mapped_column(ForeignKey("sources.id"), index=True)
    source_name: Mapped[Optional[str]] = mapped_column(String(200))
    url: Mapped[Optional[str]] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8), default="en")
    published_at: Mapped[Optional[datetime]] = ts(nullable=True, index=True)
    published_raw: Mapped[Optional[str]] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = ts(default=utcnow)
    geo: Mapped[Optional[dict]] = mapped_column(JSONB)
    source_row: Mapped[Optional[dict]] = mapped_column(JSONB)  # columnas de entrada originales, sin etiquetas
    current_version_id: Mapped[Optional[str]] = mapped_column(String(36))
    versions: Mapped[list["ArticleVersion"]] = relationship(back_populates="article", order_by="ArticleVersion.version")
    __table_args__ = (UniqueConstraint("context_id", "identity_key", name="uq_article_identity"),)


class ArticleVersion(Base):
    __tablename__ = "article_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    headline: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = ts(default=utcnow)
    article: Mapped[Article] = relationship(back_populates="versions")
    __table_args__ = (
        UniqueConstraint("article_id", "content_hash", name="uq_version_hash"),
        UniqueConstraint("article_id", "version", name="uq_version_number"),
    )


class JevCall(Base):
    """Caché de respuestas JEV por hash de la petición (texto, catálogo, modelo, preguntas)."""
    __tablename__ = "jev_calls"
    request_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    stage: Mapped[str] = mapped_column(String(8))
    requested_model: Mapped[str] = mapped_column(String(64))
    model: Mapped[Optional[str]] = mapped_column(String(64))
    engine_mode: Mapped[str] = mapped_column(String(16), default="jev")
    response: Mapped[dict] = mapped_column(JSONB)
    usage: Mapped[Optional[dict]] = mapped_column(JSONB)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = ts(default=utcnow)


class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    article_version_id: Mapped[str] = mapped_column(ForeignKey("article_versions.id", ondelete="CASCADE"), index=True)
    context_id: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | running | done | review | error
    engine_mode: Mapped[str] = mapped_column(String(16), default="jev")  # jev | fixture
    requested_model: Mapped[str] = mapped_column(String(64))
    model_id: Mapped[Optional[str]] = mapped_column(String(64))
    question_version: Mapped[str] = mapped_column(String(16))
    policy_version: Mapped[str] = mapped_column(String(32))
    request_hash_a: Mapped[Optional[str]] = mapped_column(String(64))
    request_hash_b: Mapped[Optional[str]] = mapped_column(String(64))
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    is_risk: Mapped[Optional[str]] = mapped_column(String(1))
    urgent: Mapped[Optional[str]] = mapped_column(String(1))
    affected_supplier_ids: Mapped[list] = mapped_column(JSONB, default=list)
    event_type: Mapped[Optional[str]] = mapped_column(String(32))
    event_type_confidence: Mapped[Optional[float]] = mapped_column(Float)
    event_state: Mapped[Optional[str]] = mapped_column(String(16))
    link_scores: Mapped[dict] = mapped_column(JSONB, default=dict)  # p_link de los 40 proveedores
    evidence: Mapped[list] = mapped_column(JSONB, default=list)
    duration_candidates: Mapped[list] = mapped_column(JSONB, default=list)
    review_reasons: Mapped[list] = mapped_column(JSONB, default=list)
    error_code: Mapped[Optional[str]] = mapped_column(String(64))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    retryable: Mapped[Optional[bool]] = mapped_column(Boolean)
    usage: Mapped[Optional[dict]] = mapped_column(JSONB)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    jev_attempts: Mapped[int] = mapped_column(Integer, default=0)
    manual_decision: Mapped[Optional[dict]] = mapped_column(JSONB)
    started_at: Mapped[Optional[datetime]] = ts(nullable=True)
    finished_at: Mapped[Optional[datetime]] = ts(nullable=True)
    created_at: Mapped[datetime] = ts(default=utcnow)
    assessments: Mapped[list["SupplierAssessment"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", order_by="SupplierAssessment.supplier_id"
    )
    __table_args__ = (
        UniqueConstraint("article_version_id", "requested_model", "question_version", "policy_version", "engine_mode", name="uq_analysis_key"),
    )


class SupplierAssessment(Base):
    __tablename__ = "supplier_assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    article_id: Mapped[str] = mapped_column(String(36), index=True)
    context_id: Mapped[str] = mapped_column(String(32), index=True)
    supplier_id: Mapped[str] = mapped_column(String(32), index=True)
    accepted: Mapped[bool] = mapped_column(Boolean)
    p_link: Mapped[float] = mapped_column(Float)
    p_risk: Mapped[float] = mapped_column(Float)
    p_urgent: Mapped[float] = mapped_column(Float)
    is_risk: Mapped[str] = mapped_column(String(1))
    urgent: Mapped[str] = mapped_column(String(1))
    severity: Mapped[Optional[float]] = mapped_column(Float)
    severity_confidence: Mapped[Optional[float]] = mapped_column(Float)
    impact_status: Mapped[str] = mapped_column(String(16))
    impact_confidence: Mapped[Optional[float]] = mapped_column(Float)
    priority: Mapped[Optional[float]] = mapped_column(Float)  # histórica (evento activo)
    active_priority: Mapped[Optional[float]] = mapped_column(Float)
    priority_band: Mapped[Optional[str]] = mapped_column(String(16))
    exposure: Mapped[Optional[float]] = mapped_column(Float)
    factor_values: Mapped[dict] = mapped_column(JSONB, default=dict)
    contributions: Mapped[dict] = mapped_column(JSONB, default=dict)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reasons: Mapped[list] = mapped_column(JSONB, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONB, default=list)
    duration_days: Mapped[Optional[float]] = mapped_column(Float)
    duration_is_lower_bound: Mapped[bool] = mapped_column(Boolean, default=False)
    sound_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    is_recovery: Mapped[bool] = mapped_column(Boolean, default=False)
    link_basis: Mapped[str] = mapped_column(String(24), default="identity", server_default="identity")
    policy_version: Mapped[str] = mapped_column(String(32))
    incident_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    analysis: Mapped[Analysis] = relationship(back_populates="assessments")
    __table_args__ = (UniqueConstraint("analysis_id", "supplier_id", name="uq_assessment_pair"),)


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    context_id: Mapped[str] = mapped_column(String(32), index=True)
    batch_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)  # lote Excel de origen; None en RSS
    supplier_id: Mapped[str] = mapped_column(String(32), index=True)
    event_type: Mapped[Optional[str]] = mapped_column(String(32))
    location: Mapped[Optional[str]] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | monitoring | resolved
    urgent: Mapped[str] = mapped_column(String(1), default="N")
    current_priority: Mapped[Optional[float]] = mapped_column(Float)
    peak_priority: Mapped[Optional[float]] = mapped_column(Float)
    priority_band: Mapped[Optional[str]] = mapped_column(String(16))
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reasons: Mapped[list] = mapped_column(JSONB, default=list)
    sound_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    opened_at: Mapped[Optional[datetime]] = ts(nullable=True)  # fecha de la primera evidencia
    last_evidence_at: Mapped[Optional[datetime]] = ts(nullable=True)
    resolved_at: Mapped[Optional[datetime]] = ts(nullable=True)  # fecha de la evidencia de recuperación
    resolution: Mapped[Optional[dict]] = mapped_column(JSONB)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    history: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = ts(default=utcnow)
    updated_at: Mapped[datetime] = ts(default=utcnow, onupdate=utcnow)


class IncidentArticle(Base):
    __tablename__ = "incident_articles"
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(String(36))
    role: Mapped[str] = mapped_column(String(16))  # trigger | update | recovery | historical
    published_at: Mapped[Optional[datetime]] = ts(nullable=True)
    attached_at: Mapped[datetime] = ts(default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    context_id: Mapped[str] = mapped_column(String(32), index=True)
    batch_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    supplier_id: Mapped[str] = mapped_column(String(32))
    article_id: Mapped[Optional[str]] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(24))  # urgent | high_priority | discrepancy | review
    priority: Mapped[Optional[float]] = mapped_column(Float)
    urgent: Mapped[str] = mapped_column(String(1))
    sound_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="unread")  # unread | acknowledged
    created_at: Mapped[datetime] = ts(default=utcnow)
    acknowledged_at: Mapped[Optional[datetime]] = ts(nullable=True)
    __table_args__ = (UniqueConstraint("incident_id", "revision", name="uq_alert_revision"),)


class Draft(Base):
    __tablename__ = "drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16))  # supplier | alternate
    supplier_id: Mapped[str] = mapped_column(String(32))
    target_supplier_id: Mapped[str] = mapped_column(String(32))
    incident_id: Mapped[Optional[str]] = mapped_column(String(36))
    article_id: Mapped[Optional[str]] = mapped_column(String(36))
    recipient: Mapped[Optional[str]] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    generator: Mapped[str] = mapped_column(String(32), default="template")
    factual_context: Mapped[dict] = mapped_column(JSONB, default=dict)
    factual_context_hash: Mapped[str] = mapped_column(String(64))
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = ts(default=utcnow)
    updated_at: Mapped[datetime] = ts(default=utcnow, onupdate=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    kind: Mapped[str] = mapped_column(String(32))  # analyze_article | sync_source
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | done | failed
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(300), unique=True)
    batch_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    lease_owner: Mapped[Optional[str]] = mapped_column(String(80))
    lease_until: Mapped[Optional[datetime]] = ts(nullable=True)
    heartbeat_at: Mapped[Optional[datetime]] = ts(nullable=True)
    next_attempt_at: Mapped[datetime] = ts(default=utcnow)
    error_code: Mapped[Optional[str]] = mapped_column(String(64))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = ts(default=utcnow)
    started_at: Mapped[Optional[datetime]] = ts(nullable=True)
    finished_at: Mapped[Optional[datetime]] = ts(nullable=True)
    __table_args__ = (Index("ix_jobs_claim", "status", "priority", "next_attempt_at"),)


class EvaluationLabel(Base):
    """Etiquetas originales. Nunca se leen desde el pipeline de inferencia ni desde rutas públicas."""
    __tablename__ = "evaluation_labels"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), index=True)
    news_id: Mapped[str] = mapped_column(String(64))
    is_risk: Mapped[Optional[str]] = mapped_column(String(1))
    urgent: Mapped[Optional[str]] = mapped_column(String(1))
    affected_supplier_ids: Mapped[list] = mapped_column(JSONB, default=list)
    event_type: Mapped[Optional[str]] = mapped_column(String(80))
    explanation: Mapped[Optional[str]] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("batch_id", "news_id", name="uq_label_row"),)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(String(36), index=True)
    split: Mapped[Optional[str]] = mapped_column(String(16))
    policy_version: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[Optional[str]] = mapped_column(String(64))
    metrics: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = ts(default=utcnow)


class PolicyVersion(Base):
    __tablename__ = "policy_versions"
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = ts(default=utcnow)


class AppState(Base):
    __tablename__ = "app_state"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = ts(default=utcnow, onupdate=utcnow)
