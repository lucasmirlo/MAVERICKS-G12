// Tipos de la API (coherentes con contracts/article_analysis.schema.json y app/queries.py).
export type YN = 'Y' | 'N'
export type ContextId = 'exercise' | 'rss'
export type Band = 'low' | 'medium' | 'high' | 'critical'
export type ImpactStatus = 'active' | 'monitoring' | 'resolved' | 'positive' | 'unrelated' | 'unclear'
export type Relevance = 'urgent' | 'risk' | 'positive' | 'recovery' | 'linked' | 'unlinked' | 'pending' | 'deferred' | 'error'

export interface Meta {
  app: string
  timezone: string
  contexts: { id: ContextId; label: string }[]
  engine: { mode: 'jev' | 'fixture' | 'unconfigured'; configured: boolean; model: string | null; missing_variable?: string; last_test?: EngineTest | null }
  fixtures_enabled: boolean
  policy: {
    version: string
    status: string
    thresholds: Record<string, number>
    weights: Record<'C' | 'U' | 'B' | 'G', number>
    bands: { id: Band; label_es: string; min: number }[]
    question_version: string
    criticality: Record<string, number>
    severity_floor: number
    exposure_weight: number
    buffer_not_applicable_categories: string[]
    event_types: string[]
  }
  audio: { cooldown_seconds: number; enabled_by_default: boolean }
  worker: { alive: boolean; last_heartbeat: string | null }
  rss: { poll_seconds: number; daily_budget: number; enabled: boolean }
  generator_available: boolean
  catalog: { suppliers: number }
}

export interface EngineTest {
  ok: boolean
  status: number | null
  model?: string | null
  requested_model?: string
  latency_ms: number
  code?: string
  message?: string
  at: string
}

export interface SessionInfo {
  presenter: boolean
  csrf: string | null
  login_available: boolean
}

export interface SupplierRow {
  supplier_id: string
  name: string
  country: string | null
  city: string | null
  category: string | null
  material: string | null
  criticality: string | null
  single_source: YN | null
  alternate_id: string | null
  alternate_name: string | null
  lead_days: number | null
  inventory_days: number | null
  priority: number | null
  priority_pending: boolean
  priority_band: Band | null
  urgent: YN
  needs_review: boolean
  requires_update: boolean
  active_incidents: number
  resolved_incidents: number
  historical_priority: number | null
  last_evidence_at: string | null
  reason: { event_type: string | null; headline: string; article_id: string; published_at: string | null } | null
  products: string[]
  products_mapped: boolean
  dependency_index: number | null
  dependency_factors: Partial<Record<'C' | 'U' | 'B' | 'G', number>>
  dependency_contributions?: Partial<Record<'C' | 'U' | 'B' | 'G', number>>
  dependency_weights: Record<'C' | 'U' | 'B' | 'G', number>
}

export type DecisionSource = 'jev' | 'regla' | 'regla+jev' | 'llm' | 'humano'
export type LlmStatus = 'no_necesaria' | 'pendiente' | 'hecha' | 'baja_confianza' | 'sin_segunda_opinion'
export interface LlmDecision {
  razonamiento?: string
  vinculado?: boolean
  es_riesgo?: boolean
  urgente?: boolean
  confianza?: 'alta' | 'media' | 'baja'
  error?: string
  message?: string
  meta?: { model?: string; latency_ms?: number; input_tokens?: number; output_tokens?: number }
}

export interface PlanAction {
  code: string
  label: string
  reason: string
  deadline: 'hoy' | 'esta_semana' | 'proximo_informe'
  deadline_label: string
}

export interface ActionPlan {
  id: string
  rules_version: string
  actions: PlanAction[]
  facts: {
    incidente: { tipo_evento: string | null; urgente: boolean; prioridad: number | null; fecha_evento: string | null; duracion_dias: number | null; duracion_es_minima: boolean }
    proveedor: { nombre: string; ciudad: string | null; pais: string | null; material: string | null; fuente_unica: boolean; criticidad: string | null; categoria: string | null }
    stock: { margen_dias: number | string; plazo_reposicion_dias: number | null; fecha_rotura_si_continua: string | null }
    productos: string[] | string
    alternativo: { nombre: string; ciudad: string | null; pais: string | null; afectado: boolean } | null
  }
  summary: string
  summary_source: 'template' | 'llm'
  summary_error: string | null
  drafts: { id: string; kind: 'supplier' | 'alternate'; language: string; subject: string; edited: boolean; target_supplier_id: string }[]
  updated_at: string
}

export interface SupplierFull {
  supplier_id: string
  name: string
  country: string | null
  city: string | null
  category: string | null
  material: string | null
  criticality: string | null
  single_source: YN | null
  alternate_id: string | null
  annual_spend_eur: number | null
  share_category_pct: number | null
  lead_days: number | null
  inventory_days: number | null
  quality_score: number | null
  inventory_applicability: 'physical' | 'not_applicable'
  data_issues: string[]
  cover_below_lead: boolean | null
}

export interface Evidence {
  id: string
  field: 'headline' | 'summary'
  start: number
  end: number
  text: string
}

export interface Assessment {
  id: string
  supplier_id: string
  supplier_name?: string
  accepted: boolean
  p_link: number
  p_risk: number
  p_urgent: number
  is_risk: YN
  urgent: YN
  severity: number | null
  severity_confidence: number | null
  impact_status: ImpactStatus
  impact_confidence: number | null
  priority: number | null
  active_priority: number | null
  priority_band: Band | null
  exposure: number | null
  factor_values: Partial<Record<'C' | 'U' | 'B' | 'G', number>>
  contributions: Partial<Record<'C' | 'U' | 'B' | 'G', number>>
  needs_review: boolean
  review_reasons: string[]
  evidence: Evidence[]
  duration_days: number | null
  duration_is_lower_bound: boolean
  sound_eligible: boolean
  is_recovery: boolean
  link_basis: 'identity' | 'location_explicit' | 'inferred_region'
  decision_source: DecisionSource | null
  urgent_rule: boolean | null
  jev_urgent: boolean | null
  doubtful: boolean
  doubt_reasons: string[]
  llm_status: LlmStatus | null
  llm_decision: LlmDecision | null
  alternate_affected: boolean
  policy_version: string
  incident_id: string | null
  explanation?: string
}

export interface ArticleBrief {
  id: string
  context_id: ContextId
  origin: 'excel' | 'rss'
  news_id: string | null
  batch_id: string | null
  row_index: number | null
  source_id: string | null
  source_name: string | null
  url: string | null
  published_at: string | null
  published_raw: string | null
  first_seen_at: string
  headline: string
  summary: string
  version: number | null
  language: string
  relevance: Relevance
  analysis_status: string
  engine_mode: string | null
  is_risk: YN | null
  urgent: YN | null
  affected_supplier_ids: string[]
  event_type: string | null
  needs_review: boolean
  cached: boolean
  error_code: string | null
  llm_pending?: boolean
  decision_sources?: DecisionSource[]
}

export interface ArticleDetail extends ArticleBrief {
  versions: { version: number; fetched_at: string; content_hash: string }[]
  geo: Record<string, string> | null
  analysis?: {
    id: string
    status: string
    engine_mode: string
    model_id: string | null
    requested_model: string
    question_version: string
    policy_version: string
    cached: boolean
    event_type: string | null
    event_type_confidence: number | null
    event_state: string | null
    review_reasons: string[]
    error_code: string | null
    error_message: string | null
    retryable: boolean | null
    duration_ms: number | null
    finished_at: string | null
    evidence: Evidence[]
    manual_decision: { is_risk: YN; urgent: YN; affected_supplier_ids: string[]; note: string; at: string } | null
    candidates_considered: { supplier_id: string; name: string; p_link: number }[]
    assessments: Assessment[]
  }
}

export interface Incident {
  id: string
  context_id: ContextId
  supplier_id: string
  event_type: string | null
  status: 'active' | 'monitoring' | 'resolved'
  urgent: YN
  current_priority: number | null
  historical_priority: number | null
  priority_band: Band | null
  needs_review: boolean
  review_reasons: string[]
  sound_eligible: boolean
  opened_at: string | null
  last_evidence_at: string | null
  resolved_at: string | null
  resolution: { manual: boolean; note?: string; at: string } | null
  revision: number
  requires_update: boolean
  article_count: number
  plan: ActionPlan | null
  latest_article: { article_id: string; headline: string | null; source_name: string | null; published_at: string | null; url: string | null; news_id: string } | null
  history: { at: string; role: string; status: string; priority?: number | null; urgent?: YN; news_id?: string; article_id?: string; note?: string }[]
}

export interface Draft {
  id: string
  kind: 'supplier' | 'alternate'
  supplier_id: string
  target_supplier_id: string
  incident_id: string | null
  article_id: string | null
  recipient: string | null
  subject: string
  body: string
  generator: string
  factual_context_hash: string
  edited: boolean
  created_at: string
  updated_at: string
  evidence_changed?: boolean
  generator_error?: string | null
}

export interface MaterialLink {
  material_id: string
  name: string
  role: 'primary' | 'alternate'
  category: string | null
  monthly_requirement: number | null
  unit: string | null
  primary_supplier_id: string | null
  alternate_supplier_id: string | null
  products: string[]
}

export interface SupplierDetail {
  supplier: SupplierFull
  alternate: SupplierFull | null
  backup_for: { supplier_id: string; name: string }[]
  materials: MaterialLink[]
  products: string[]
  products_mapped: boolean
  incidents: Incident[]
  priority: number | null
  historical_priority: number | null
  breakdown: {
    priority: number | null
    severity: number | null
    exposure: number | null
    factors: Partial<Record<'C' | 'U' | 'B' | 'G', number>>
    contributions: Partial<Record<'C' | 'U' | 'B' | 'G', number>>
    weights: Record<'C' | 'U' | 'B' | 'G', number>
    severity_floor: number
    exposure_weight: number
    policy_version: string
    duration_days: number | null
    duration_is_lower_bound: boolean
    review_reasons: string[]
  } | null
  news: { article: ArticleBrief; assessment: Assessment; explanation: string }[]
  drafts: Draft[]
  context_id: ContextId
  clock: string
}

export interface Source {
  id: string
  name: string
  url: string
  language: string
  topic: string | null
  enabled: boolean
  poll_seconds: number
  last_attempt_at: string | null
  last_success_at: string | null
  last_status: number | null
  last_outcome: 'ok' | 'not_modified' | 'error' | null
  last_item_count: number | null
  last_new_count: number | null
  last_duration_ms: number | null
  error_count: number
  consecutive_errors: number
  error_message: string | null
  healthy: boolean
  syncing: boolean
  articles_total: number
  articles_24h: number
  never_polled: boolean
}

export interface BatchProgress {
  id: string
  kind: 'news'
  split: 'training' | 'validation' | 'test' | 'liveday' | 'other'
  context_id: ContextId
  file_name: string
  sheet_name: string
  file_sha256: string
  row_count: number
  has_labels: boolean
  logical_date: string | null
  created_at: string
  diagnostics: { level: string; row: number; news_id?: string; issues: string[] }[]
  analysis_requested_at: string | null
  analysis_completed_at: string | null
  elapsed_seconds: number | null
  counts: { done: number; review: number; error: number; running: number; pending: number; not_started: number }
  jobs: Record<string, number>
  completed: number
  latency: { n: number; p50_ms: number | null; p95_ms: number | null }
  export?: { ready: boolean; rows: number; blockers: { news_id: string; reason: string; error_code: string | null }[]; review_pending: number; manual: number }
  errors?: { news_id: string; article_id: string; error_code: string; error_message: string; retryable: boolean; analysis_id: string }[]
}

export interface Overview {
  context_id: ContextId
  batch_id: string | null
  context_label: string
  clock: string
  clock_kind: 'real' | 'logical' | 'presenter'
  last_analysis_at: string | null
  kpis: {
    urgent_suppliers: number
    suppliers_total: number
    active_incidents: number
    requires_update: number
    incidents_total: number
    articles_total: number
    processed: number
    review: number
    error: number
    pending: number
    linked: number
    risk: number
    urgent: number
    positive: number
    linked_suppliers: number
    sources_operational: number
    sources_total: number
    batches_analyzed: number
    batches_total: number
  }
  ranking: SupplierRow[]
  latest: ArticleBrief[]
  sources: Source[]
  priority_distribution: Record<Band | 'pending', number>
  by_source: Record<string, number>
  latency: { n: number; p50_ms: number | null; p95_ms: number | null }
  batches: BatchProgress[]
}

export interface Alert {
  id: string
  seq: number
  incident_id: string
  context_id: ContextId
  batch_id: string | null
  batch_split: string | null
  supplier_id: string
  supplier_name: string
  revision: number
  kind: 'urgent' | 'high_priority' | 'discrepancy'
  priority: number | null
  urgent: YN
  sound_eligible: boolean
  status: 'unread' | 'acknowledged'
  incident_status: 'active' | 'monitoring' | 'resolved' | null
  created_at: string
  acknowledged_at: string | null
  article_id: string | null
  headline: string | null
  source_name: string | null
  published_at: string | null
  event_type: string | null
  needs_review: boolean
  p_link: number | null
  p_risk: number | null
  p_urgent: number | null
  priority_band: Band | null
  decision_source: DecisionSource | null
  llm_decision: LlmDecision | null
  plan: ActionPlan | null
}

export interface AlertsResponse {
  items: Alert[]
  cursor: number
  unread: number
  unread_by_context: Record<string, number>
}

export interface Paged<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
