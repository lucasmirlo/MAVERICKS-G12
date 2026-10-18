import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, CircleDashed, ExternalLink, FileSpreadsheet, Loader2, MinusCircle, RefreshCw, Rss, WifiOff } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge, Button, Card, CardHeader, ErrorState, Field, Loading, Notice } from '../components/ui'
import { api, ApiError } from '../lib/api'
import { POLL_MS, useApp } from '../lib/app-state'
import { SPLIT_LABEL, fmtDateTime, fmtDay, fmtRelative } from '../lib/format'
import type { Source } from '../lib/types'

function SourceStatus({ s }: { s: Source }) {
  if (s.syncing) return <Badge tone="info" icon={<Loader2 className="size-3.5 animate-spin" aria-hidden />}>Consultando…</Badge>
  if (s.never_polled) return <Badge icon={<CircleDashed className="size-3.5" aria-hidden />}>Sin consultar aún</Badge>
  if (s.last_outcome === 'error') return <Badge tone="urgent" icon={<WifiOff className="size-3.5" aria-hidden />}>Error de conexión</Badge>
  if (s.last_outcome === 'not_modified' || (s.last_outcome === 'ok' && !s.last_new_count))
    return <Badge tone="ok" icon={<MinusCircle className="size-3.5" aria-hidden />}>Sin novedades</Badge>
  return <Badge tone="ok" icon={<CheckCircle2 className="size-3.5" aria-hidden />}>{s.last_new_count} novedades</Badge>
}

export function SourceMini({ s }: { s: Source }) {
  return (
    <li className="flex items-center justify-between gap-2 px-4 py-2.5 text-sm">
      <div className="min-w-0">
        <p className="truncate font-semibold text-ink">{s.name}</p>
        <p className="text-xs text-ink-2">Última consulta {fmtRelative(s.last_attempt_at)}</p>
      </div>
      <SourceStatus s={s} />
    </li>
  )
}

interface SourcesResponse {
  items: Source[]
  operational: number
  total: number
  analysis_queue: number
  deferred_by_budget: number
  sync_in_progress: number
  budget: { used_today: number; daily: number }
}

export default function Sources() {
  const { presenter, openLogin, batches, setBatchId, setContextId } = useApp()
  const qc = useQueryClient()
  const [msg, setMsg] = useState<string | null>(null)
  const q = useQuery({ queryKey: ['sources'], queryFn: () => api.get<SourcesResponse>('/api/sources'), refetchInterval: POLL_MS })
  const sync = useMutation({
    mutationFn: () => api.post<{ sources: number }>('/api/sources/sync'),
    onSuccess: (r) => {
      setMsg(`Sincronización encolada para ${r.sources} fuentes. El worker consulta cada fuente de forma independiente.`)
      qc.invalidateQueries({ queryKey: ['sources'] })
    },
    onError: (e) => setMsg(e instanceof ApiError ? e.message : 'No se pudo encolar.'),
  })
  if (q.isLoading) return <Loading />
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-bold sm:text-2xl">Fuentes</h1>
        <p className="text-sm text-ink-2">Dos orígenes separados: los archivos Excel del ejercicio (lo que se evalúa y se exporta) y los RSS reales (demostración del producto).</p>
      </div>
      <section aria-labelledby="xls-src" className="flex flex-col gap-3">
        <h2 id="xls-src" className="flex items-center gap-2 text-lg font-bold"><FileSpreadsheet className="size-5 text-accent" aria-hidden /> Ejercicio · archivos Excel (evaluado)</h2>
        {batches.length === 0 ? (
          <Card><p className="p-4 text-sm text-ink-2">Sin archivos importados. El presentador los importa desde su panel.</p></Card>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            {batches.map((b) => (
              <Card key={b.id} as="article" aria-labelledby={`xls-${b.id}`}>
                <CardHeader id={`xls-${b.id}`} title={SPLIT_LABEL[b.split] ?? b.split} subtitle={`${b.file_name} · hoja ${b.sheet_name}`}
                  action={b.completed === b.row_count && b.row_count ? <Badge tone="ok">Analizado</Badge> : b.completed ? <Badge tone="review">Parcial</Badge> : <Badge>Sin analizar</Badge>} />
                <dl className="grid grid-cols-2 gap-3 p-4">
                  <Field label="Filas">{b.row_count}</Field>
                  <Field label="Analizadas">{b.completed} / {b.row_count}</Field>
                  <Field label="Fecha lógica">{fmtDay(b.logical_date)}</Field>
                  <Field label="Etiquetas">{b.has_labels ? 'Sí (solo evaluación)' : 'No'}</Field>
                  <Field label="Importado">{fmtDateTime(b.created_at)}</Field>
                  <Field label="SHA-256">{b.file_sha256}</Field>
                </dl>
                <div className="border-t border-line px-4 py-3">
                  <button className="text-sm font-semibold text-accent-strong underline" onClick={() => { setContextId('exercise'); setBatchId(b.id) }}>Ver solo este lote</button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>
      <div className="flex flex-wrap items-end justify-between gap-3 border-t border-line pt-4">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><Rss className="size-5 text-accent" aria-hidden /> Noticias reales · RSS (pitch)</h2>
          <p className="text-sm text-ink-2">
            {d.operational} de {d.total} operativas · sondeo automático cada 5 min · {d.analysis_queue} artículos en cola de análisis
            {d.deferred_by_budget ? ` · ${d.deferred_by_budget} en espera por cupo diario` : ''} · cupo {d.budget.used_today}/{d.budget.daily} hoy (UTC)
          </p>
        </div>
        {presenter ? (
          <Button variant="primary" onClick={() => sync.mutate()} busy={sync.isPending || d.sync_in_progress > 0} icon={<RefreshCw className="size-4" aria-hidden />}>
            Actualizar ahora
          </Button>
        ) : (
          <Button onClick={openLogin} icon={<RefreshCw className="size-4" aria-hidden />}>
            Actualizar ahora (presentador)
          </Button>
        )}
      </div>
      {msg && <p role="status" className="text-sm text-ink">{msg}</p>}
      <Notice tone="info" title="Consultas reales, fuera de la evaluación">
        Cada estado procede de la última petición HTTP real del worker. Un fallo de una fuente no detiene a las demás y los artículos previos conservan su fecha. Estos artículos nunca entran en la exportación del reto.
      </Notice>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {d.items.map((s) => (
          <Card key={s.id} as="article" aria-labelledby={`src-${s.id}`}>
            <CardHeader id={`src-${s.id}`} title={s.name} subtitle={`${s.topic ?? ''} · ${s.language.toUpperCase()}`} action={<SourceStatus s={s} />} />
            <dl className="grid grid-cols-2 gap-3 p-4">
              <Field label="Última consulta">{fmtDateTime(s.last_attempt_at)}</Field>
              <Field label="Último éxito">{fmtDateTime(s.last_success_at)}</Field>
              <Field label="HTTP">{s.last_status ?? '—'}{s.last_duration_ms != null ? ` · ${s.last_duration_ms} ms` : ''}</Field>
              <Field label="Elementos en el feed">{s.last_item_count ?? '—'}</Field>
              <Field label="Novedades última consulta">{s.last_new_count ?? '—'}</Field>
              <Field label="Artículos (24 h / total)">{s.articles_24h} / {s.articles_total}</Field>
              <Field label="Errores acumulados">{s.error_count}{s.consecutive_errors ? ` (${s.consecutive_errors} seguidos)` : ''}</Field>
            </dl>
            {s.error_message && <p className="mx-4 mb-3 rounded-lg bg-urgent-bg p-2 text-xs text-urgent">{s.error_message}</p>}
            <div className="flex flex-wrap gap-3 border-t border-line px-4 py-3 text-sm">
              <Link to={`/noticias?source=${s.id}`} className="font-semibold text-accent-strong underline">Ver artículos</Link>
              <a href={s.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-ink-2 underline">
                Feed original <ExternalLink className="size-3.5" aria-hidden />
              </a>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
