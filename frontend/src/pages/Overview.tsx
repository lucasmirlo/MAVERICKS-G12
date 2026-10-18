import { useQuery } from '@tanstack/react-query'
import { AlertOctagon, ArrowRight, Building2, FileSpreadsheet, Newspaper, Rss, ShieldAlert } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArticleItem } from '../components/ArticleItem'
import { AttentionDesk } from '../components/AttentionDesk'
import { BatchPanel } from '../components/BatchPanel'
import { SupplierCards, SupplierTable } from '../components/SupplierRanking'
import { Card, CardHeader, EmptyState, ErrorState, Kpi, Loading, Notice } from '../components/ui'
import { api, qs } from '../lib/api'
import { POLL_MS, useApp } from '../lib/app-state'
import { SPLIT_LABEL, fmtDateTime, fmtDay, fmtRelative } from '../lib/format'
import type { Overview as OverviewT } from '../lib/types'
import { SourceMini } from './Sources'

const BAND_COLORS = { low: '#94a3b8', medium: '#b54708', high: '#d92d20', critical: '#7a271a', pending: '#c4b5fd' }

export function ContextBanner() {
  const { contextId } = useApp()
  if (contextId === 'rss') {
    return (
      <Notice tone="accent" title="Noticias reales · Cartera simulada" icon={<Rss className="size-4" aria-hidden />}>
        Fuentes RSS reales con su fecha original. Los vínculos con proveedores de Helixa (ficticios) son <strong>exposición potencial de cartera simulada</strong>: una
        coincidencia regional no prueba que una instalación concreta se haya detenido.
      </Notice>
    )
  }
  return null
}

export function EngineNotice() {
  const { meta, presenter } = useApp()
  if (!meta) return null
  if (meta.engine.mode === 'unconfigured') {
    return (
      <Notice tone="review" title="Motor sin configurar">
        No se pueden analizar noticias nuevas; nunca se muestran como «sin riesgo».{' '}
        {presenter && meta.engine.missing_variable ? `Define ${meta.engine.missing_variable} en el servidor.` : 'El presentador debe configurar la clave del motor.'}
      </Notice>
    )
  }
  if (meta.worker.alive && meta.worker.compatible === false && meta.worker.revision) {
    return (
      <Notice tone="review" title="Web y worker con versiones distintas">
        La web ejecuta la revisión {meta.worker.web_revision} y el worker la {meta.worker.revision}: un despliegue quedó a medias. Reinicia o redespliega el worker.
      </Notice>
    )
  }
  if (!meta.worker.alive) {
    return (
      <Notice tone="review" title="Worker sin señal">
        El proceso que analiza y sincroniza RSS no ha dado señal en el último minuto ({meta.worker.last_heartbeat ? fmtRelative(meta.worker.last_heartbeat) : 'nunca'}). Los trabajos quedan en cola.
      </Notice>
    )
  }
  return null
}

export default function Overview() {
  const { contextId, presenter, meta, scope, batchId, setBatchId } = useApp()
  const q = useQuery({
    queryKey: ['overview', scope],
    queryFn: () => api.get<OverviewT>(`/api/overview${qs(scope)}`),
    refetchInterval: POLL_MS,
  })
  if (q.isLoading) return <Loading />
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  const k = d.kpis
  const noCatalog = meta?.catalog.suppliers === 0
  const dist = (['low', 'medium', 'high', 'critical', 'pending'] as const).map((b) => ({
    band: { low: 'Baja', medium: 'Media', high: 'Alta', critical: 'Crítica', pending: 'Pendiente' }[b],
    key: b,
    n: d.priority_distribution[b] ?? 0,
  }))
  const bySource = Object.entries(d.by_source).map(([name, n]) => ({ name, n }))
  const selected = d.batches.find((b) => b.id === batchId)
  const activeBatches = selected ? [selected] : d.batches.filter((b) => b.analysis_requested_at && !b.analysis_completed_at)
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold text-ink sm:text-2xl">Resumen · {d.context_label}{selected ? ` · ${SPLIT_LABEL[selected.split] ?? selected.split}` : ''}</h1>
          <p className="text-sm text-ink-2">
            {contextId === 'rss' ? 'Hora real' : d.clock_kind === 'presenter' ? 'Reloj elegido por el presentador' : d.clock_kind === 'logical' ? 'Reloj lógico del lote' : 'Sin lote analizado · fecha actual'}: {contextId === 'rss' ? fmtDateTime(d.clock) : fmtDay(d.clock)}
            {d.last_analysis_at && <> · último análisis {fmtRelative(d.last_analysis_at)}</>}
          </p>
        </div>
        {contextId === 'exercise' && <span className="rounded-full bg-lavender px-3 py-1 text-xs font-semibold text-accent-strong">Datos del ejercicio</span>}
      </div>
      <EngineNotice />
      <ContextBanner />
      {noCatalog && (
        <Card>
          <EmptyState title="Sin catálogo de proveedores" icon={<FileSpreadsheet className="size-8" aria-hidden />}
            action={presenter ? <Link className="font-semibold text-accent-strong underline" to="/presentador">Importar Excel</Link> : undefined}>
            {presenter ? 'Importa supplier_training.xlsx (Suppliers y Materials) para empezar.' : 'El presentador debe importar el catálogo del ejercicio.'}
          </EmptyState>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-2 sm:gap-3 xl:grid-cols-4">
        <Kpi label="Proveedores urgentes" tone={k.urgent_suppliers ? 'urgent' : 'default'} icon={<ShieldAlert className="size-4 text-urgent" aria-hidden />}
          value={k.urgent_suppliers} detail={`de ${k.suppliers_total} de la cartera, con incidente activo urgente`} />
        <Kpi label="Incidentes activos" icon={<AlertOctagon className="size-4 text-accent" aria-hidden />} value={k.active_incidents}
          detail={`${k.requires_update} requieren actualización · ${k.incidents_total} totales`} />
        <Kpi label="Noticias procesadas" icon={<Newspaper className="size-4 text-accent" aria-hidden />} value={`${k.processed}/${k.articles_total}`}
          detail={`${k.linked} vinculadas · ${k.risk} riesgo · ${k.error} error · ${k.pending} sin analizar o en cola`} />
        {contextId === 'rss' ? (
          <Kpi label="Fuentes operativas" icon={<Rss className="size-4 text-accent" aria-hidden />} value={`${k.sources_operational}/${k.sources_total}`}
            detail="RSS con consulta correcta reciente" />
        ) : (
          <Kpi label="Lotes Excel analizados" icon={<FileSpreadsheet className="size-4 text-accent" aria-hidden />} value={`${k.batches_analyzed}/${k.batches_total}`}
            detail="Archivos del ejercicio con todas sus filas analizadas" />
        )}
      </div>

      <Card aria-labelledby="desk-h" className="overflow-hidden">
        <div className="gradient-bar h-1" aria-hidden />
        <CardHeader id="desk-h" title="Mesa de atención · de la señal a la siguiente acción"
          subtitle="Incidentes activos por urgencia y prioridad, con la próxima acción de su plan (reglas explícitas y cifras de la base de datos)."
          action={<Link to="/alertas" className="inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-accent-strong">Alertas <ArrowRight className="size-4" aria-hidden /></Link>} />
        <AttentionDesk items={d.attention} />
      </Card>

      {contextId === 'exercise' && activeBatches.length > 0 && (
        <Card aria-labelledby="batch-h">
          <CardHeader id="batch-h" title="Progreso del lote" subtitle="Se actualiza cada 3 s mientras la página está visible." />
          <div className="flex flex-col gap-3 p-3 sm:p-4">
            {activeBatches.map((b) => <BatchPanel key={b.id} batch={b} />)}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Card aria-labelledby="rank-h">
          <CardHeader id="rank-h" title="Ranking de proveedores" subtitle="Prioridad 0–100 = máximo de sus incidentes activos; no es una probabilidad."
            action={<Link to="/proveedores" className="inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-accent-strong">Ver todos <ArrowRight className="size-4" aria-hidden /></Link>} />
          {d.ranking.length === 0 ? (
            <EmptyState title="Sin proveedores" icon={<Building2 className="size-8" aria-hidden />} />
          ) : (
            <div className="p-2 md:p-0">
              <SupplierCards rows={d.ranking.slice(0, 8)} />
              <SupplierTable rows={d.ranking} caption="Ranking de proveedores por prioridad" />
            </div>
          )}
        </Card>
        <div className="flex flex-col gap-4">
          <Card aria-labelledby="news-h">
            <CardHeader id="news-h" title="Novedades" action={<Link to="/noticias" className="inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-accent-strong">Noticias <ArrowRight className="size-4" aria-hidden /></Link>} />
            {d.latest.length === 0 ? (
              <EmptyState title="Sin noticias en este contexto" icon={<Newspaper className="size-8" aria-hidden />}>
                {contextId === 'rss' ? 'Aún no hay artículos RSS recibidos.' : 'Importa un lote de noticias del ejercicio.'}
              </EmptyState>
            ) : (
              <ul>{d.latest.map((a) => <ArticleItem key={a.id} a={a} compact />)}</ul>
            )}
          </Card>
          <Card aria-labelledby="dist-h">
            <CardHeader id="dist-h" title="Distribución de prioridad" subtitle={`Incidentes activos · ${d.context_label}`} />
            <div className="p-3">
              <div className="h-40" aria-hidden>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={dist} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
                    <CartesianGrid vertical={false} stroke="#DCE3EE" />
                    <XAxis dataKey="band" tick={{ fontSize: 12, fill: '#52647A' }} axisLine={false} tickLine={false} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: '#52647A' }} axisLine={false} tickLine={false} />
                    <Tooltip cursor={{ fill: '#F3F0FF' }} />
                    <Bar dataKey="n" name="Incidentes" radius={[6, 6, 0, 0]}>
                      {dist.map((x) => <Cell key={x.key} fill={BAND_COLORS[x.key]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-2 text-xs text-ink-2">
                Alternativa textual: {dist.map((x) => `${x.band} ${x.n}`).join(', ')}. Latencia de análisis p50 {d.latency.p50_ms ? `${(d.latency.p50_ms / 1000).toFixed(1)} s` : '—'}, p95{' '}
                {d.latency.p95_ms ? `${(d.latency.p95_ms / 1000).toFixed(1)} s` : '—'} (n = {d.latency.n}{d.latency.n < 20 ? ', muestra pequeña' : ''}).
              </p>
            </div>
          </Card>
          {contextId === 'rss' && bySource.length > 0 && (
            <Card aria-labelledby="vol-h">
              <CardHeader id="vol-h" title="Volumen por fuente" subtitle="Artículos RSS recibidos (todas las fechas)" />
              <div className="p-3">
                <div className="h-44" aria-hidden>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={bySource} layout="vertical" margin={{ top: 4, right: 12, bottom: 0, left: 8 }}>
                      <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12, fill: '#52647A' }} axisLine={false} tickLine={false} />
                      <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 11, fill: '#0A2540' }} axisLine={false} tickLine={false} />
                      <Tooltip cursor={{ fill: '#F3F0FF' }} />
                      <Bar dataKey="n" name="Artículos" fill="#635BFF" radius={[0, 6, 6, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-2 text-xs text-ink-2">Alternativa textual: {bySource.map((x) => `${x.name} ${x.n}`).join(', ')}.</p>
              </div>
            </Card>
          )}
          {contextId === 'rss' ? (
            <Card aria-labelledby="src-h">
              <CardHeader id="src-h" title="Estado de fuentes RSS" subtitle="Pitch: no forma parte de la evaluación." action={<Link to="/fuentes" className="inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-accent-strong">Fuentes <ArrowRight className="size-4" aria-hidden /></Link>} />
              <ul className="divide-y divide-line/70">{d.sources.map((s) => <SourceMini key={s.id} s={s} />)}</ul>
            </Card>
          ) : (
            <Card aria-labelledby="xls-h">
              <CardHeader id="xls-h" title="Fuentes del ejercicio (Excel)" subtitle="Lo que se evalúa. Pulsa un lote para ver solo sus resultados." />
              {d.batches.length === 0 ? (
                <p className="p-4 text-sm text-ink-2">Sin archivos importados.</p>
              ) : (
                <ul className="divide-y divide-line/70">
                  {d.batches.map((b) => (
                    <li key={b.id}>
                      <button onClick={() => setBatchId(b.id === batchId ? '' : b.id)} aria-pressed={b.id === batchId}
                        className={`flex min-h-12 w-full items-center justify-between gap-2 px-4 py-2 text-left text-sm hover:bg-bg ${b.id === batchId ? 'bg-lavender' : ''}`}>
                        <span className="min-w-0">
                          <span className="block font-semibold text-ink">{SPLIT_LABEL[b.split] ?? b.split} · {b.sheet_name}</span>
                          <span className="block text-xs text-ink-2">{b.file_name} · {b.row_count} filas{b.has_labels ? ' · con etiquetas' : ''}</span>
                        </span>
                        <span className="tabular shrink-0 text-xs font-semibold text-ink-2">
                          {b.completed}/{b.row_count}{b.export?.ready ? ' · exportable' : ''}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
