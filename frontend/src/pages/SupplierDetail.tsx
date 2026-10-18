import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft, Boxes, ExternalLink, FileText, History, Mail, PackageSearch, Quote, ShieldCheck, Timer } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ActionPlanCard } from '../components/ActionPlanCard'
import { DraftDialog } from '../components/DraftDialog'
import { ScoreBreakdown } from '../components/ScoreBreakdown'
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, Field, Loading, PriorityBadge, ReviewBadge, UrgencyBadge } from '../components/ui'
import { api, ApiError, qs } from '../lib/api'
import { POLL_MS, useApp } from '../lib/app-state'
import { CRIT_LABEL, EVENT_LABEL, IMPACT_LABEL, fmtDays, fmtEur, fmtNum, fmtPub, reviewLabel } from '../lib/format'
import type { Draft, Incident, SupplierDetail as SD } from '../lib/types'
import { ContextBanner } from './Overview'

function IncidentCard({ inc, context }: { inc: Incident; context: string }) {
  const resolved = inc.status === 'resolved'
  return (
    <li className="rounded-xl border border-line p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold">{EVENT_LABEL[inc.event_type ?? ''] ?? 'Evento'}</p>
        <div className="flex flex-wrap gap-1">
          {resolved ? <Badge tone="ok" icon={<ShieldCheck className="size-3.5" aria-hidden />}>Recuperado</Badge> : inc.status === 'monitoring' ? <Badge tone="info">En seguimiento</Badge> : <Badge tone="urgent">Activo</Badge>}
          {!resolved && <UrgencyBadge urgent={inc.urgent} />}
          {inc.needs_review && <ReviewBadge title={inc.review_reasons.map(reviewLabel).join('; ')} />}
          {inc.requires_update && <Badge tone="review" icon={<Timer className="size-3.5" aria-hidden />}>Requiere actualización</Badge>}
        </div>
      </div>
      <p className="mt-1 text-sm text-ink-2">
        {resolved ? <>Prioridad activa 0 · histórica <strong className="tabular text-ink">{fmtNum(inc.historical_priority)}</strong></> : <>Prioridad <strong className="tabular text-ink">{fmtNum(inc.current_priority)}</strong> · máxima {fmtNum(inc.historical_priority)}</>}
        {' '}· {inc.article_count} noticia{inc.article_count === 1 ? '' : 's'} · desde {fmtPub(inc.opened_at, context)}
        {inc.resolved_at && <> · resuelto {fmtPub(inc.resolved_at, context)}{inc.resolution?.manual ? ' (manual)' : ''}</>}
      </p>
      {inc.latest_article && (
        <Link to={`/noticias/${inc.latest_article.article_id}`} className="mt-1 block text-sm font-medium text-accent-strong underline">
          {inc.latest_article.headline}
        </Link>
      )}
      {!resolved && inc.plan && <ActionPlanCard plan={inc.plan} />}
      <details className="mt-2 text-xs">
        <summary className="cursor-pointer font-semibold text-ink-2">Historial ({inc.history.length})</summary>
        <ol className="mt-1 space-y-1 border-l-2 border-lavender-strong pl-3">
          {inc.history.map((h, i) => (
            <li key={i}>
              <span className="tabular">{fmtPub(h.at, context)}</span> · {{ trigger: 'Inicio', update: 'Actualización', recovery: 'Recuperación', historical: 'Evidencia anterior recibida tarde', recovery_candidate: 'Recuperación ambigua', manual_resolution: 'Resolución manual' }[h.role] ?? h.role}
              {h.news_id ? ` · ${h.news_id}` : ''}
              {h.priority != null ? ` · prioridad ${fmtNum(h.priority)}` : ''}
              {h.note ? ` · «${h.note}»` : ''}
            </li>
          ))}
        </ol>
      </details>
    </li>
  )
}

export default function SupplierDetail() {
  const { id = '' } = useParams()
  const { contextId, presenter, openLogin, scope } = useApp()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const q = useQuery({ queryKey: ['supplier', id, scope], queryFn: () => api.get<SD>(`/api/suppliers/${id}${qs(scope)}`), refetchInterval: POLL_MS })
  const create = useMutation({
    mutationFn: (kind: 'supplier' | 'alternate') => {
      const top = q.data?.incidents.find((i) => i.status !== 'resolved') ?? q.data?.incidents[0]
      return api.post<Draft>('/api/drafts', { kind, supplier_id: id, incident_id: top?.id ?? null, article_id: top?.latest_article?.article_id ?? null })
    },
    onSuccess: (d) => {
      setErr(null)
      setDraft(d)
    },
    onError: (e) => setErr(e instanceof ApiError ? e.message : 'No se pudo crear el borrador.'),
  })
  if (q.isLoading) return <Loading />
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  const s = d.supplier
  const active = d.incidents.filter((i) => i.status !== 'resolved')
  const top = active[0]
  const topNews = top ? d.news.find((n) => n.article.id === top.latest_article?.article_id) : undefined
  const inventory =
    s.inventory_applicability === 'not_applicable'
      ? 'Inventario no aplicable'
      : s.inventory_days === null
        ? 'Inventario no informado'
        : fmtDays(s.inventory_days)
  return (
    <div className="flex flex-col gap-4">
      <Link to="/proveedores" className="inline-flex min-h-11 w-fit items-center gap-1 text-sm font-semibold text-accent-strong">
        <ArrowLeft className="size-4" aria-hidden /> Proveedores
      </Link>
      <ContextBanner />
      <Card className="overflow-hidden">
        <div className="gradient-bar h-1" aria-hidden />
        <div className="flex flex-wrap items-start justify-between gap-3 p-4 sm:p-5">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-2">{s.supplier_id} · {s.category}</p>
            <h1 className="text-xl font-bold sm:text-2xl">{s.name}</h1>
            <p className="text-sm text-ink-2">{s.city}, {s.country} · {s.material}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Badge tone="accent">Criticidad {CRIT_LABEL[s.criticality ?? ''] ?? '—'}</Badge>
              {s.single_source === 'Y' && <Badge tone="accent">Fuente única</Badge>}
              {active.some((i) => i.urgent === 'Y') && <UrgencyBadge urgent="Y" />}
              {active.some((i) => i.needs_review) && <ReviewBadge />}
              {d.historical_priority ? <Badge>Riesgo histórico: máx. {fmtNum(d.historical_priority)}</Badge> : null}
            </div>
          </div>
          <div className="text-right">
            <p className="text-xs text-ink-2">Prioridad activa</p>
            {active.length ? <PriorityBadge value={d.priority} band={top?.priority_band} pending={d.priority === null} size="lg" /> : <p className="text-sm font-semibold text-ink-2">Sin riesgo activo</p>}
            <p className="mt-1 text-xs text-ink-2">{active.length} incidente{active.length === 1 ? '' : 's'} activo{active.length === 1 ? '' : 's'}</p>
            <a href="#next-h" className="mt-2 inline-flex min-h-11 items-center gap-1 rounded-[10px] bg-lavender px-3 text-sm font-semibold text-accent-strong xl:hidden">
              <Mail className="size-4" aria-hidden /> Siguiente paso
            </a>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="flex flex-col gap-4">
          <Card aria-labelledby="what-h">
            <CardHeader id="what-h" title="Qué ocurrió y por qué lo vinculamos" />
            <div className="p-4">
              {top && topNews ? (
                <div className="flex flex-col gap-3">
                  <Link to={`/noticias/${topNews.article.id}`} className="font-semibold text-ink underline decoration-accent/40 hover:text-accent-strong">
                    {topNews.article.headline}
                  </Link>
                  <p className="text-xs text-ink-2">{topNews.article.source_name} · {fmtPub(topNews.article.published_at, contextId)}</p>
                  {topNews.assessment.evidence.map((e) => (
                    <blockquote key={e.id} className="flex gap-2 rounded-lg border-l-4 border-accent bg-lavender p-3 text-sm">
                      <Quote className="size-4 shrink-0 text-accent" aria-hidden />
                      <span>{e.text}</span>
                    </blockquote>
                  ))}
                  <p className="text-sm leading-relaxed">{topNews.explanation}</p>
                  <p className="text-xs text-ink-2">
                    Vínculo p={fmtNum(topNews.assessment.p_link, 2)} · riesgo p={fmtNum(topNews.assessment.p_risk, 2)} · urgencia p={fmtNum(topNews.assessment.p_urgent, 2)} · impacto{' '}
                    {IMPACT_LABEL[topNews.assessment.impact_status]}. Probabilidades Noul de JEV; no son confianza ni probabilidad de quiebra.
                  </p>
                </div>
              ) : (
                <EmptyState title="Sin incidentes activos" icon={<ShieldCheck className="size-8" aria-hidden />}>
                  {d.incidents.length ? 'Tiene historial de incidentes resueltos (ver abajo).' : 'No hay noticias de riesgo vinculadas en este contexto.'}
                </EmptyState>
              )}
            </div>
          </Card>

          {d.breakdown && (
            <Card aria-labelledby="score-h">
              <CardHeader id="score-h" title="Desglose de la prioridad" subtitle="Orden de atención 0–100; no es una probabilidad de desabastecimiento." />
              <div className="p-4"><ScoreBreakdown b={d.breakdown} /></div>
            </Card>
          )}

          <Card aria-labelledby="inc-h">
            <CardHeader id="inc-h" title="Incidentes" subtitle="Actualizaciones del mismo evento se agrupan sin sumar puntuaciones." />
            <div className="p-4">
              {d.incidents.length ? <ul className="flex flex-col gap-2">{d.incidents.map((i) => <IncidentCard key={i.id} inc={i} context={contextId} />)}</ul> : <p className="text-sm text-ink-2">Sin incidentes en este contexto.</p>}
            </div>
          </Card>

          <Card aria-labelledby="news-h">
            <CardHeader id="news-h" title="Noticias vinculadas" subtitle="Incluye noticias positivas y sin riesgo." />
            {d.news.length ? (
              <ul className="divide-y divide-line/70">
                {d.news.map((n) => (
                  <li key={n.article.id} className="px-4 py-3">
                    <Link to={`/noticias/${n.article.id}`} className="font-semibold hover:text-accent-strong hover:underline">{n.article.headline}</Link>
                    <p className="text-xs text-ink-2">{n.article.source_name} · {fmtPub(n.article.published_at, contextId)} {n.article.news_id ? `· ${n.article.news_id}` : ''}</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {n.assessment.is_risk === 'Y' ? <Badge tone="review">Riesgo</Badge> : <Badge tone="ok">Sin riesgo</Badge>}
                      <UrgencyBadge urgent={n.assessment.urgent} isRisk={n.assessment.is_risk} />
                      {!n.assessment.accepted && <Badge tone="review">Candidato ambiguo (no aceptado)</Badge>}
                      {n.assessment.needs_review && <ReviewBadge title={n.assessment.review_reasons.map(reviewLabel).join('; ')} />}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="p-4 text-sm text-ink-2">Sin noticias vinculadas.</p>
            )}
          </Card>
        </div>

        <div className="flex flex-col gap-4">
          <Card aria-labelledby="next-h">
            <CardHeader id="next-h" title="Siguiente paso" />
            <div className="flex flex-col gap-2 p-4">
              {presenter ? (
                <>
                  <Button variant="primary" onClick={() => create.mutate('supplier')} busy={create.isPending && create.variables === 'supplier'} icon={<Mail className="size-4" aria-hidden />}>
                    Borrador de consulta al proveedor
                  </Button>
                  <Button onClick={() => create.mutate('alternate')} disabled={!d.alternate} busy={create.isPending && create.variables === 'alternate'} icon={<PackageSearch className="size-4" aria-hidden />}>
                    {d.alternate ? `Consultar alternativo (${d.alternate.name})` : 'Sin alternativo aprobado'}
                  </Button>
                </>
              ) : (
                <Button onClick={openLogin} icon={<Mail className="size-4" aria-hidden />}>Acceso de presentador para crear borradores</Button>
              )}
              {err && <p role="alert" className="text-sm text-urgent">{err}</p>}
              {d.drafts.length > 0 && (
                <div className="mt-2">
                  <p className="text-xs font-semibold text-ink-2">Borradores guardados</p>
                  <ul className="mt-1 flex flex-col gap-1">
                    {d.drafts.map((dr) => (
                      <li key={dr.id}>
                        <button className="flex min-h-11 w-full items-center gap-2 rounded-lg px-2 text-left text-sm hover:bg-lavender" onClick={() => setDraft(dr)}>
                          <FileText className="size-4 text-accent" aria-hidden />
                          <span className="min-w-0 flex-1 truncate">{dr.subject}</span>
                          {dr.edited && <Badge>Editado</Badge>}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </Card>

          <Card aria-labelledby="buffer-h">
            <CardHeader id="buffer-h" title="Buffer y dependencia" />
            <dl className="grid grid-cols-2 gap-3 p-4">
              <Field label="Cobertura de inventario">{inventory}</Field>
              <Field label="Lead time">{s.lead_days === null ? 'No informado' : fmtDays(s.lead_days)}</Field>
              <Field label="Cuota de gasto en categoría">{s.share_category_pct === null ? '—' : `${fmtNum(s.share_category_pct)} %`}</Field>
              <Field label="Gasto anual">{fmtEur(s.annual_spend_eur)}</Field>
              <Field label="Calidad">{s.quality_score ?? '—'}</Field>
              <Field label="Cobertura vs. lead">{s.cover_below_lead === null ? '—' : s.cover_below_lead ? 'Inferior al lead time' : 'Cubre el lead time'}</Field>
            </dl>
            <p className="px-4 pb-4 text-xs text-ink-2">Indicador de cobertura, no proyección: no hay pedidos en tránsito ni capacidad del alternativo en los datos.</p>
            {s.data_issues.length > 0 && <p className="mx-4 mb-4 rounded-lg bg-review-bg p-2 text-xs text-review">Diagnóstico de datos: {s.data_issues.join('; ')}</p>}
          </Card>

          <Card aria-labelledby="alt-h">
            <CardHeader id="alt-h" title="Alternativa" />
            <div className="p-4 text-sm">
              {d.alternate ? (
                <>
                  <Link to={`/proveedores/${d.alternate.supplier_id}`} className="font-semibold text-accent-strong underline">{d.alternate.name}</Link>
                  <p className="text-ink-2">{d.alternate.city}, {d.alternate.country}</p>
                  <Badge tone="review" className="mt-2">Alternativo aprobado, stock sin confirmar</Badge>
                </>
              ) : (
                <p className="text-ink-2">Sin alternativo aprobado en los datos.</p>
              )}
              {d.backup_for.length > 0 && <p className="mt-2 text-xs text-ink-2">Es alternativo de: {d.backup_for.map((b) => b.name).join(', ')}.</p>}
            </div>
          </Card>

          <Card aria-labelledby="prod-h">
            <CardHeader id="prod-h" title="Materiales y productos" />
            <div className="p-4 text-sm">
              {d.materials.length ? (
                <ul className="flex flex-col gap-2">
                  {d.materials.map((m) => (
                    <li key={`${m.material_id}-${m.role}`} className="rounded-lg border border-line p-2">
                      <p className="flex items-center gap-1.5 font-semibold"><Boxes className="size-4 text-accent" aria-hidden />{m.name} <span className="text-xs font-normal text-ink-2">({m.material_id} · {m.role === 'primary' ? 'principal' : 'alternativo'})</span></p>
                      <p className="text-xs text-ink-2">Necesidad mensual: {m.monthly_requirement != null ? `${fmtNum(m.monthly_requirement, 0)} ${m.unit ?? ''}` : '—'}</p>
                      <p className="text-xs">Productos: {m.products.join(', ') || 'Productos no mapeados'}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="font-semibold text-review">Productos no mapeados</p>
              )}
              {!d.materials.length && <p className="mt-1 text-xs text-ink-2">La hoja Materials no relaciona este proveedor con productos; no significa que no afecte a ninguno.</p>}
            </div>
          </Card>
          {topNews?.article.url && (
            <a href={topNews.article.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-ink-2 underline">
              Fuente original <ExternalLink className="size-3.5" aria-hidden />
            </a>
          )}
          <p className="flex items-center gap-1 text-xs text-ink-2"><History className="size-3.5" aria-hidden /> Reloj del contexto: {fmtPub(d.clock, contextId)}</p>
        </div>
      </div>
      <DraftDialog draft={draft} onClose={() => setDraft(null)} />
    </div>
  )
}
