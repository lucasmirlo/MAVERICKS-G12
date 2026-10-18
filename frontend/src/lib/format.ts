import type { Band, ImpactStatus, Relevance } from './types'

const TZ = 'Europe/Madrid'
const dtFmt = new Intl.DateTimeFormat('es-ES', { timeZone: TZ, day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
const dFmt = new Intl.DateTimeFormat('es-ES', { timeZone: TZ, day: '2-digit', month: 'short', year: 'numeric' })
const tFmt = new Intl.DateTimeFormat('es-ES', { timeZone: TZ, hour: '2-digit', minute: '2-digit', second: '2-digit' })
const dUtc = new Intl.DateTimeFormat('es-ES', { timeZone: 'UTC', day: '2-digit', month: 'short', year: 'numeric' })

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return dtFmt.format(new Date(iso))
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  return dFmt.format(new Date(iso))
}

/** Fechas del Excel: solo día, sin desplazar por zona horaria. */
export function fmtDay(iso: string | null | undefined): string {
  if (!iso) return '—'
  return dUtc.format(new Date(iso))
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return tFmt.format(new Date(iso))
}

export function fmtRelative(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return 'nunca'
  const s = Math.round((now - new Date(iso).getTime()) / 1000)
  if (s < 0) return 'ahora'
  if (s < 60) return `hace ${s} s`
  if (s < 3600) return `hace ${Math.round(s / 60)} min`
  if (s < 86400) return `hace ${Math.round(s / 3600)} h`
  return `hace ${Math.round(s / 86400)} d`
}

export function fmtNum(v: number | null | undefined, decimals = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return v.toLocaleString('es-ES', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

export function fmtPct(v: number | null | undefined, decimals = 0): string {
  if (v === null || v === undefined) return '—'
  return `${(v * 100).toLocaleString('es-ES', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })} %`
}

export function fmtEur(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return v.toLocaleString('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })
}

export function fmtDays(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${fmtNum(v, Number.isInteger(v) ? 0 : 1)} días`
}

export function fmtSeconds(s: number | null | undefined): string {
  if (s === null || s === undefined) return '—'
  if (s < 60) return `${fmtNum(s, 0)} s`
  return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`
}

export const BAND_LABEL: Record<Band, string> = { low: 'Baja', medium: 'Media', high: 'Alta', critical: 'Crítica' }

export const EVENT_LABEL: Record<string, string> = {
  fire_incident: 'Incendio o incidente en planta',
  natural_disaster: 'Desastre natural',
  labour_strike: 'Huelga o conflicto laboral',
  regulatory_action: 'Acción regulatoria',
  export_restriction: 'Restricción a la exportación',
  financial_distress: 'Deterioro financiero',
  quality_recall: 'Calidad o retirada',
  logistics_disruption: 'Interrupción logística',
  utility_outage: 'Corte de suministros básicos',
  leadership_change: 'Cambio de dirección',
  acquisition: 'Cambio de propiedad',
  recovery: 'Recuperación',
  positive_news: 'Noticia positiva',
  other: 'Otro evento',
  not_relevant: 'Sin evento relevante',
}

export const IMPACT_LABEL: Record<ImpactStatus, string> = {
  active: 'Activo',
  monitoring: 'En seguimiento',
  resolved: 'Recuperado',
  positive: 'Positivo',
  unrelated: 'Sin relación',
  unclear: 'Poco claro',
}

export const RELEVANCE_LABEL: Record<Relevance, string> = {
  urgent: 'Urgente',
  risk: 'Riesgo',
  positive: 'Positiva',
  recovery: 'Recuperación',
  linked: 'Vinculada sin riesgo',
  unlinked: 'Sin vínculo',
  pending: 'Pendiente',
  deferred: 'En espera (cupo)',
  error: 'Error',
}

const REVIEW_LABEL: Record<string, string> = {
  ambiguous_probability: 'probabilidad en zona ambigua (0,35–0,65)',
  contradictory_impact_state: 'estado de impacto contradictorio con el riesgo',
  impact_state_unclear: 'estado de impacto poco claro',
  low_impact_state_confidence: 'confianza baja en el estado de impacto',
  low_severity_confidence: 'confianza baja en la severidad',
  low_event_type_confidence: 'confianza baja en el tipo de evento',
  no_evidence: 'sin frase de evidencia seleccionada',
  inventory_missing: 'inventario físico no informado',
  buffer_horizon_missing: 'sin lead time ni duración para calcular el buffer',
  inventory_applicability_unknown: 'categoría sin aplicabilidad de inventario conocida',
  criticality_missing: 'criticidad no informada',
  single_source_missing: 'fuente única no informada',
  category_share_missing: 'cuota de gasto no informada',
  severity_missing: 'severidad ausente',
  priority_unavailable: 'prioridad no calculable',
  invalid_supplier_data: 'datos del proveedor no válidos',
  supplier_data_issue: 'diagnóstico de datos del proveedor',
  unexpected_model_version: 'versión de modelo devuelta distinta de la solicitada',
  recovery_ambiguous: 'recuperación compatible con varios incidentes',
}

export function reviewLabel(code: string): string {
  const [maybeSupplier, reason] = code.includes(':') ? code.split(':', 2) : [null, code]
  const text = REVIEW_LABEL[reason] ?? reason
  return maybeSupplier ? `${maybeSupplier}: ${text}` : text
}

export const ERROR_LABEL: Record<string, string> = {
  engine_not_configured: 'Motor sin configurar',
  unauthorized: 'Clave JEV rechazada (401)',
  rate_limited: 'Límite de uso JEV (429)',
  overloaded: 'JEV sobrecargado (529)',
  timeout: 'Tiempo de espera agotado',
  connection_error: 'Error de conexión',
  invalid_response: 'Respuesta JEV inválida',
  article_budget_exceeded: 'Presupuesto de 60 s agotado',
  catalog_missing: 'Sin catálogo',
  budget_exceeded: 'Cupo diario RSS alcanzado',
}

export const SPLIT_LABEL: Record<string, string> = {
  training: 'Entrenamiento',
  validation: 'Validación',
  test: 'Test',
  liveday: 'LiveDay',
  other: 'Otro',
}

export const CRIT_LABEL: Record<string, string> = { High: 'Alta', Medium: 'Media', Low: 'Baja' }
export const FACTOR_LABEL: Record<string, string> = { C: 'Criticidad', U: 'Fuente única', B: 'Presión del buffer', G: 'Concentración de gasto' }

/** Excel: fecha de día. RSS: fecha y hora reales en Europe/Madrid. */
export function fmtPub(iso: string | null | undefined, context: string): string {
  return context === 'rss' ? fmtDateTime(iso) : fmtDay(iso)
}
