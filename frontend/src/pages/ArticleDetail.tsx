import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ExternalLink, Sparkles } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { RelevanceBadge } from '../components/ArticleItem'
import { DecisionBadge, LlmReasoning } from '../components/Decision'
import { Badge, Button, Card, CardHeader, ErrorState, Field, Loading, Notice, PriorityBadge, ProbBar, ReviewBadge, UrgencyBadge } from '../components/ui'
import { api, ApiError } from '../lib/api'
import { POLL_MS, useApp } from '../lib/app-state'
import { ERROR_LABEL, EVENT_LABEL, IMPACT_LABEL, fmtDateTime, fmtDays, fmtNum, fmtPub, reviewLabel } from '../lib/format'
import type { ArticleDetail as AD, Assessment, Evidence } from '../lib/types'

function Highlighted({ text, field, evidence }: { text: string; field: 'headline' | 'summary'; evidence: Evidence[] }) {
  const spans = evidence.filter((e) => e.field === field).sort((a, b) => a.start - b.start)
  if (!spans.length) return <>{text}</>
  const out = []
  let i = 0
  for (const s of spans) {
    if (s.start < i) continue
    out.push(<span key={`t${i}`}>{text.slice(i, s.start)}</span>)
    out.push(<mark key={s.id} className="rounded bg-lavender-strong px-0.5 text-ink">{text.slice(s.start, s.end)}</mark>)
    i = s.end
  }
  out.push(<span key="end">{text.slice(i)}</span>)
  return <>{out}</>
}

function AssessmentCard({ a, thresholds, potential }: { a: Assessment; thresholds: Record<string, number>; potential: boolean }) {
  const { presenter, meta } = useApp()
  const [generated, setGenerated] = useState<string | null>(null)
  const gen = useMutation({
    mutationFn: () => api.post<{ text: string; generator: string; error: string | null }>(`/api/assessments/${a.id}/explanation`),
    onSuccess: (r) => setGenerated(r.error ? `${r.error}\n\n${r.text}` : r.text),
  })
  return (
    <li className="rounded-xl border border-line p-3 sm:p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <Link to={`/proveedores/${a.supplier_id}`} className="font-semibold text-ink hover:text-accent-strong hover:underline">{a.supplier_name} ({a.supplier_id})</Link>
          <div className="mt-1 flex flex-wrap gap-1">
            {a.accepted ? <Badge tone="info">{potential ? 'Exposición potencial' : 'Vinculado'}</Badge> : <Badge tone="review">Candidato ambiguo, no aceptado</Badge>}
            {a.accepted && a.link_basis === 'inferred_region' && <Badge tone="review" title="Ni el nombre ni la ciudad aparecen en la noticia; vínculo por región o ruta inferida: sin sonido automático">Vínculo regional inferido</Badge>}
            {a.accepted && a.link_basis === 'location_explicit' && <Badge tone="info">Por ubicación citada</Badge>}
            {a.is_risk === 'Y' ? <Badge tone="review">Riesgo Y</Badge> : <Badge tone="ok">Riesgo N</Badge>}
            <UrgencyBadge urgent={a.urgent} isRisk={a.is_risk} />
            <Badge>{IMPACT_LABEL[a.impact_status]}</Badge>
            {a.needs_review && <ReviewBadge />}
            {a.sound_eligible && <Badge tone="urgent">Elegible para aviso sonoro</Badge>}
            {a.accepted || a.doubtful ? <DecisionBadge source={a.decision_source} llmStatus={a.llm_status} /> : null}
          </div>
        </div>
        {a.is_risk === 'Y' && <PriorityBadge value={a.priority} band={a.priority_band} pending={a.priority === null} />}
      </div>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <ProbBar label="p vínculo (Noul)" value={a.p_link} threshold={thresholds.link} />
        <ProbBar label="p riesgo (Noul)" value={a.p_risk} threshold={thresholds.risk} />
        <ProbBar label="p urgencia (Noul)" value={a.p_urgent} threshold={thresholds.urgent} />
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Field label="Severidad (Score)">{a.severity != null ? `${fmtNum(a.severity)}/10` : '—'}</Field>
        <Field label="Confianza severidad">{a.severity_confidence != null ? fmtNum(a.severity_confidence, 2) : '—'}</Field>
        <Field label="Confianza impacto">{a.impact_confidence != null ? fmtNum(a.impact_confidence, 2) : '—'}</Field>
        <Field label="Duración explícita">{a.duration_days != null ? `${a.duration_is_lower_bound ? '≥ ' : ''}${fmtDays(a.duration_days)}` : 'No indicada'}</Field>
      </dl>
      {a.evidence.length > 0 && <p className="mt-3 rounded-lg bg-lavender p-2 text-sm">«{a.evidence[0].text}»</p>}
      {a.doubtful && (
        <p className="mt-2 text-xs text-ink-2">
          Caso dudoso: regla de prioridad {a.urgent_rule ? 'urgente' : 'no urgente'} · JEV {a.jev_urgent ? 'urgente' : 'no urgente'}
          {a.doubt_reasons.length ? ` · ${a.doubt_reasons.map((r) => ({ urgency_disagreement: 'regla y JEV discrepan', probability_in_review_band: 'probabilidad en zona 0,35–0,65', inferred_region_link: 'vínculo solo por región inferida' } as Record<string, string>)[r] ?? r).join(', ')}` : ''}
        </p>
      )}
      <LlmReasoning decision={a.llm_decision} status={a.llm_status} />
      {a.explanation && <p className="mt-3 text-sm leading-relaxed">{a.explanation}</p>}
      {a.review_reasons.length > 0 && <p className="mt-2 text-xs text-review">Requiere revisión: {a.review_reasons.map(reviewLabel).join('; ')}.</p>}
      {presenter && meta?.generator_available && (
        <div className="mt-2">
          <Button variant="ghost" onClick={() => gen.mutate()} busy={gen.isPending} icon={<Sparkles className="size-4" aria-hidden />}>Redactar explicación con generador</Button>
          {generated && <p className="mt-1 whitespace-pre-line rounded-lg border border-line p-2 text-sm">{generated}</p>}
        </div>
      )}
    </li>
  )
}

function ManualDecisionForm({ analysisId }: { analysisId: string }) {
  const qc = useQueryClient()
  const [isRisk, setIsRisk] = useState<'Y' | 'N'>('N')
  const [urgent, setUrgent] = useState<'Y' | 'N'>('N')
  const [ids, setIds] = useState('')
  const [note, setNote] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const m = useMutation({
    mutationFn: () => api.post(`/api/analyses/${analysisId}/manual`, { is_risk: isRisk, urgent, affected_supplier_ids: ids.split(/[;,\s]+/).filter(Boolean), note }),
    onSuccess: () => {
      setMsg('Decisión manual registrada; la fila queda marcada como manual en la exportación.')
      qc.invalidateQueries()
    },
    onError: (e) => setMsg(e instanceof ApiError ? e.message : 'No se pudo registrar.'),
  })
  return (
    <form className="mt-3 flex flex-col gap-2 rounded-xl border border-line p-3" onSubmit={(e: FormEvent) => { e.preventDefault(); m.mutate() }}>
      <p className="text-sm font-semibold">Resolución manual explícita</p>
      <p className="text-xs text-ink-2">Solo si no es posible reintentar. Queda registrada con nota; no se convierte un error en N de forma silenciosa.</p>
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col text-xs">Is_Risk<select className="min-h-11 rounded-lg border border-line px-2" value={isRisk} onChange={(e) => setIsRisk(e.target.value as 'Y' | 'N')}><option>N</option><option>Y</option></select></label>
        <label className="flex flex-col text-xs">Urgent<select className="min-h-11 rounded-lg border border-line px-2" value={urgent} onChange={(e) => setUrgent(e.target.value as 'Y' | 'N')}><option>N</option><option>Y</option></select></label>
      </div>
      <label className="flex flex-col text-xs">Affected_Supplier_IDs (separados por ;)<input className="min-h-11 rounded-lg border border-line px-2 text-base sm:text-sm" value={ids} onChange={(e) => setIds(e.target.value)} /></label>
      <label className="flex flex-col text-xs">Motivo (obligatorio)<input required minLength={3} className="min-h-11 rounded-lg border border-line px-2 text-base sm:text-sm" value={note} onChange={(e) => setNote(e.target.value)} /></label>
      <Button type="submit" busy={m.isPending}>Registrar decisión manual</Button>
      {msg && <p role="status" className="text-sm">{msg}</p>}
    </form>
  )
}

interface Run {
  id: string
  version: number | null
  status: string
  model_id: string | null
  question_version: string
  policy_version: string
  urgency_mode: string | null
  is_risk: string | null
  urgent: string | null
  affected_supplier_ids: string[]
  cached: boolean
  finished_at: string | null
  current: boolean
  decision_sources: string[]
}

function RunHistory({ articleId }: { articleId: string }) {
  const q = useQuery({ queryKey: ['runs', articleId], queryFn: () => api.get<{ items: Run[] }>(`/api/articles/${articleId}/runs`) })
  if (!q.data || q.data.items.length < 2) return null
  return (
    <Card aria-labelledby="runs-h">
      <CardHeader id="runs-h" title="Historial de análisis" subtitle="Cada fila es un análisis guardado: versión de preguntas, política y modo con que se decidió." />
      <div className="overflow-x-auto p-3">
        <table className="w-full min-w-[34rem] text-left text-sm">
          <caption className="sr-only">Análisis de esta noticia</caption>
          <thead className="text-xs text-ink-2">
            <tr><th scope="col">Fecha</th><th scope="col">Preguntas</th><th scope="col">Política</th><th scope="col">Modo</th><th scope="col">Resultado</th><th scope="col">Estado</th></tr>
          </thead>
          <tbody>
            {q.data.items.map((r) => (
              <tr key={r.id} className="border-t border-line/70">
                <td className="py-1.5 text-xs">{fmtDateTime(r.finished_at)}{r.cached ? ' · caché' : ''}</td>
                <td className="tabular">{r.question_version}</td>
                <td className="tabular">{r.policy_version}</td>
                <td>{r.urgency_mode ?? '—'}</td>
                <td className="tabular text-xs font-semibold">{r.is_risk ?? '—'}/{r.urgent ?? '—'}/{r.affected_supplier_ids.join('; ') || '—'}</td>
                <td className="text-xs">{r.status}{r.current ? '' : ' · versión anterior'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

export default function ArticleDetail() {
  const { id = '' } = useParams()
  const { meta, presenter } = useApp()
  const q = useQuery({ queryKey: ['article', id], queryFn: () => api.get<AD>(`/api/articles/${id}`), refetchInterval: POLL_MS })
  if (q.isLoading) return <Loading />
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const a = q.data
  const an = a.analysis
  const evidence = an?.evidence ?? []
  const used = new Set(an?.assessments.flatMap((x) => x.evidence.map((e) => e.id)) ?? [])
  const usedEvidence = evidence.filter((e) => used.has(e.id))
  const potential = a.context_id === 'rss'
  return (
    <div className="flex flex-col gap-4">
      <Link to="/noticias" className="inline-flex min-h-11 w-fit items-center gap-1 text-sm font-semibold text-accent-strong"><ArrowLeft className="size-4" aria-hidden /> Noticias</Link>
      {potential && (
        <Notice tone="accent" title="Noticia real · Cartera simulada">Cualquier vínculo mostrado es exposición potencial de la cartera simulada de Helixa (proveedores ficticios).</Notice>
      )}
      <Card>
        <div className="p-4 sm:p-5">
          <div className="flex flex-wrap items-center gap-2 text-xs text-ink-2">
            <span className="font-semibold text-ink">{a.source_name}</span>
            <span>· publicada {fmtPub(a.published_at, a.context_id)}</span>
            {a.origin === 'rss' && <span>· recibida {fmtDateTime(a.first_seen_at)}</span>}
            {a.news_id && <span className="tabular">· {a.news_id}</span>}
            {a.version && a.version > 1 && <Badge tone="info">Versión {a.version}</Badge>}
          </div>
          <h1 className="mt-1 text-xl font-bold leading-snug sm:text-2xl"><Highlighted text={a.headline} field="headline" evidence={usedEvidence} /></h1>
          {a.summary && <p className="mt-2 leading-relaxed text-ink"><Highlighted text={a.summary} field="summary" evidence={usedEvidence} /></p>}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <RelevanceBadge relevance={a.relevance} />
            {an?.event_type && <Badge tone="accent">{EVENT_LABEL[an.event_type] ?? an.event_type}</Badge>}
            {an?.cached && <Badge>Resultado en caché</Badge>}
            {a.url && (
              <a href={a.url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-accent-strong underline">
                Fuente original <ExternalLink className="size-3.5" aria-hidden />
              </a>
            )}
          </div>
          {a.origin === 'rss' && <p className="mt-2 text-xs text-ink-2">Resumen tal como lo suministra el feed (sin texto completo). Texto saneado sin HTML.</p>}
        </div>
      </Card>

      {!an ? (
        <Notice tone="info" title={a.analysis_status === 'deferred' ? 'En espera por cupo diario RSS' : 'Análisis pendiente'}>
          {meta?.engine.mode === 'unconfigured' ? 'Motor sin configurar: no se ha analizado. Nunca se presenta como «sin riesgo».' : 'El worker procesará esta noticia; la página se actualiza sola.'}
        </Notice>
      ) : an.status === 'error' ? (
        <Card>
          <div className="p-4">
            <Notice tone="urgent" title={`Error de análisis: ${ERROR_LABEL[an.error_code ?? ''] ?? an.error_code}`}>
              {an.error_message} {an.retryable ? 'Se reintentará automáticamente de forma acotada.' : 'Requiere reintento desde el lote o resolución manual.'} Sin decisión Y/N: bloquea la exportación final.
            </Notice>
            {an.manual_decision && <p className="mt-2 text-sm">Decisión manual: Is_Risk {an.manual_decision.is_risk}, Urgent {an.manual_decision.urgent}, IDs {an.manual_decision.affected_supplier_ids.join('; ') || '—'} · «{an.manual_decision.note}»</p>}
            {presenter && !an.manual_decision && <ManualDecisionForm analysisId={an.id} />}
          </div>
        </Card>
      ) : (
        <>
        <Card aria-labelledby="eval-h">
          <CardHeader id="eval-h" title="Evaluación por proveedor"
            subtitle={`Estado del evento: ${an.event_state ? IMPACT_LABEL[an.event_state as keyof typeof IMPACT_LABEL] ?? an.event_state : '—'} · confianza tipo ${an.event_type_confidence != null ? fmtNum(an.event_type_confidence, 2) : '—'}`} />
          <div className="p-3 sm:p-4">
            {an.review_reasons.length > 0 && <div className="mb-3"><Notice tone="review" title="Requiere revisión">{an.review_reasons.map(reviewLabel).join('; ')}.</Notice></div>}
            {an.assessments.length ? (
              <ul className="flex flex-col gap-3">{an.assessments.map((x) => <AssessmentCard key={x.id} a={x} thresholds={meta?.policy.thresholds ?? {}} potential={potential} />)}</ul>
            ) : (
              <p className="text-sm text-ink-2">Ningún proveedor de la cartera superó el umbral de candidato (p ≥ 0,35) en la etapa A. Se evaluaron las {meta?.catalog.suppliers ?? 40} identidades.</p>
            )}
            {an.candidates_considered.length > 0 && (
              <details className="mt-3 text-xs text-ink-2">
                <summary className="cursor-pointer font-semibold">Candidatos de la etapa A con p ≥ 0,20</summary>
                <ul className="mt-1">{an.candidates_considered.map((c) => <li key={c.supplier_id} className="tabular">{c.supplier_id} {c.name}: {fmtNum(c.p_link, 2)}</li>)}</ul>
              </details>
            )}
            <p className="mt-3 text-xs text-ink-2">
              Modelo {an.model_id ?? an.requested_model} · preguntas v{an.question_version} · política {an.policy_version} · {an.duration_ms != null ? `${fmtNum(an.duration_ms / 1000)} s` : '—'} · {fmtDateTime(an.finished_at)}
              {an.engine_mode === 'fixture' && ' · MODO FIXTURE (no JEV)'}
            </p>
          </div>
        </Card>
        <RunHistory articleId={a.id} />
        </>
      )}
    </div>
  )
}
