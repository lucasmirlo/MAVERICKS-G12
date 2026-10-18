import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Download, Play, RotateCcw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, ApiError, downloadExport } from '../lib/api'
import { useApp } from '../lib/app-state'
import { ERROR_LABEL, SPLIT_LABEL, fmtDateTime, fmtDay, fmtNum, fmtSeconds } from '../lib/format'
import type { BatchProgress } from '../lib/types'
import { Badge, Button } from './ui'

function useTicker(active: boolean) {
  const [, setN] = useState(0)
  useEffect(() => {
    if (!active) return
    const t = window.setInterval(() => setN((n) => n + 1), 1000)
    return () => window.clearInterval(t)
  }, [active])
}

export function BatchPanel({ batch }: { batch: BatchProgress }) {
  const { presenter, openLogin, meta } = useApp()
  const qc = useQueryClient()
  const [msg, setMsg] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null)
  const running = !!batch.analysis_requested_at && !batch.analysis_completed_at
  useTicker(running)
  const elapsed = running && batch.analysis_requested_at ? (Date.now() - new Date(batch.analysis_requested_at).getTime()) / 1000 : batch.elapsed_seconds
  const c = batch.counts
  const total = batch.row_count || 1
  const done = c.done + c.review
  const analyze = useMutation({
    mutationFn: () => api.post<{ created: number; requeued: number }>(`/api/batches/${batch.id}/analyze`, { retry_errors: true }),
    onSuccess: (r) => {
      setMsg({ tone: 'ok', text: r.created || r.requeued ? `Encolado: ${r.created} nuevas, ${r.requeued} reintentos.` : 'Nada que encolar: el lote ya está analizado.' })
      qc.invalidateQueries()
    },
    onError: (e) => setMsg({ tone: 'err', text: e instanceof ApiError ? e.message : 'No se pudo encolar.' }),
  })
  const exportFile = useMutation({
    mutationFn: () => downloadExport(batch.id),
    onSuccess: (name) => setMsg({ tone: 'ok', text: `Descargado ${name}.` }),
    onError: (e) => setMsg({ tone: 'err', text: e instanceof ApiError ? e.message : 'No se pudo exportar.' }),
  })
  const [confirmReset, setConfirmReset] = useState(false)
  const reset = useMutation({
    mutationFn: () => api.post<{ analyses_deleted: number }>(`/api/batches/${batch.id}/reset`),
    onSuccess: (r) => {
      setConfirmReset(false)
      setMsg({ tone: 'ok', text: `Análisis reiniciado (${r.analyses_deleted} resultados borrados, caché incluida). El próximo análisis llamará a JEV en directo.` })
      qc.invalidateQueries()
    },
    onError: (e) => setMsg({ tone: 'err', text: e instanceof ApiError ? e.message : 'No se pudo reiniciar.' }),
  })
  const exportCsv = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/batches/${batch.id}/export.csv`, { credentials: 'same-origin' })
      if (!res.ok) throw new ApiError(res.status, 'export_error', 'No se pudo exportar el CSV.', null, false)
      const url = URL.createObjectURL(await res.blob())
      const a = document.createElement('a')
      a.href = url
      a.download = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') ?? '')?.[1] ?? 'resultados.csv'
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 2000)
      return a.download
    },
    onSuccess: (name) => setMsg({ tone: 'ok', text: `Descargado ${name}.` }),
    onError: (e) => setMsg({ tone: 'err', text: e instanceof ApiError ? e.message : 'No se pudo exportar.' }),
  })
  const finalRun = batch.split === 'test' || batch.split === 'liveday'
  const engineReady = meta?.engine.mode === 'jev' || meta?.engine.mode === 'fixture'
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold text-ink">
            {SPLIT_LABEL[batch.split] ?? batch.split} · {batch.sheet_name}
            {finalRun && <Badge tone="accent" className="ml-2">Ejecución final</Badge>}
          </p>
          <p className="text-xs text-ink-2">
            {batch.file_name} · {batch.row_count} filas · fecha lógica {fmtDay(batch.logical_date)} · sha {batch.file_sha256}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {presenter ? (
            <Button variant="primary" onClick={() => analyze.mutate()} busy={analyze.isPending} disabled={!engineReady} icon={done && !c.error ? <RotateCcw className="size-4" aria-hidden /> : <Play className="size-4" aria-hidden />}>
              {c.error ? 'Reintentar errores' : done ? 'Reanalizar pendientes' : 'Analizar lote'}
            </Button>
          ) : (
            <Button onClick={openLogin} icon={<Play className="size-4" aria-hidden />}>
              Analizar (presentador)
            </Button>
          )}
          <Button onClick={() => exportFile.mutate()} busy={exportFile.isPending} disabled={!batch.export?.ready} icon={<Download className="size-4" aria-hidden />}>
            Exportar XLSX
          </Button>
          <Button onClick={() => exportCsv.mutate()} busy={exportCsv.isPending} disabled={!batch.export?.ready} icon={<Download className="size-4" aria-hidden />}>
            CSV
          </Button>
        </div>
      </div>
      <div className="mt-3" aria-label="Progreso del lote">
        <div className="flex h-2.5 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuemin={0} aria-valuemax={batch.row_count} aria-valuenow={done} aria-valuetext={`${done} de ${batch.row_count} filas completadas`}>
          <div className="bg-accent" style={{ width: `${(c.done / total) * 100}%` }} />
          <div className="bg-[#f79009]" style={{ width: `${(c.review / total) * 100}%` }} />
          <div className="bg-urgent" style={{ width: `${(c.error / total) * 100}%` }} />
          <div className="bg-cyan/60" style={{ width: `${(c.running / total) * 100}%` }} />
        </div>
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4 lg:grid-cols-7">
          <div><dt className="text-ink-2">Completadas</dt><dd className="tabular font-semibold">{done} / {batch.row_count}</dd></div>
          <div><dt className="text-ink-2">En revisión</dt><dd className="tabular font-semibold">{c.review}</dd></div>
          <div><dt className="text-ink-2">Con error</dt><dd className="tabular font-semibold text-urgent">{c.error}</dd></div>
          <div><dt className="text-ink-2">Pendientes</dt><dd className="tabular font-semibold">{c.pending + c.running + c.not_started}</dd></div>
          <div><dt className="text-ink-2">Tiempo</dt><dd className="tabular font-semibold">{fmtSeconds(elapsed)}{running ? ' (en curso)' : ''}</dd></div>
          <div><dt className="text-ink-2">En cola / procesando</dt><dd className="tabular font-semibold">{batch.queue_seconds != null ? `${fmtSeconds(batch.queue_seconds)} / ${fmtSeconds(batch.processing_seconds)}` : '—'}</dd></div>
          <div><dt className="text-ink-2">Latencia p50 / p95</dt><dd className="tabular font-semibold">{batch.latency.n ? `${fmtNum((batch.latency.p50_ms ?? 0) / 1000)} / ${fmtNum((batch.latency.p95_ms ?? 0) / 1000)} s` : '—'}</dd></div>
          <div><dt className="text-ink-2">Muestra</dt><dd className="tabular font-semibold">n = {batch.latency.n}</dd></div>
        </dl>
        {batch.analysis_completed_at && <p className="mt-1 text-xs text-ink-2">Terminado {fmtDateTime(batch.analysis_completed_at)}.</p>}
      </div>
      {batch.export && !batch.export.ready && batch.export.blockers.length > 0 && (
        <p className="mt-2 text-xs text-ink-2">
          Exportación bloqueada: {batch.export.blockers.length} filas {batch.export.blockers.some((b) => b.reason === 'error') ? 'con error o ' : ''}sin decisión final
          {batch.export.blockers.some((b) => b.reason === 'fixture_result') ? ' (resultados de fixture no exportables)' : ''}.
        </p>
      )}
      {batch.export?.ready && batch.export.review_pending > 0 && (
        <p className="mt-2 text-xs text-review">{batch.export.review_pending} filas exportan su mejor decisión binaria con revisión pendiente (registrado en la hoja Informe).</p>
      )}
      {batch.errors && batch.errors.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs text-urgent">
          {batch.errors.slice(0, 5).map((e) => (
            <li key={e.article_id}>
              {e.news_id}: {ERROR_LABEL[e.error_code] ?? e.error_code} {e.retryable ? '(reintentable)' : ''}
            </li>
          ))}
        </ul>
      )}
      {presenter && done + c.error > 0 && !running && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          {confirmReset ? (
            <>
              <span className="text-review">Borra los resultados, alertas derivadas y caché de este lote (no las filas importadas).</span>
              <Button variant="danger" onClick={() => reset.mutate()} busy={reset.isPending}>Confirmar reinicio</Button>
              <Button variant="ghost" onClick={() => setConfirmReset(false)}>Cancelar</Button>
            </>
          ) : (
            <Button variant="ghost" onClick={() => setConfirmReset(true)}>Reiniciar análisis del lote</Button>
          )}
        </div>
      )}
      {!engineReady && presenter &&<p className="mt-2 text-xs text-review">Motor sin configurar: define {meta?.engine.missing_variable ?? 'la clave del motor'} en el servidor.</p>}
      {msg && (
        <p role="status" className={`mt-2 text-sm ${msg.tone === 'ok' ? 'text-ok' : 'text-urgent'}`}>
          {msg.text}
        </p>
      )}
    </div>
  )
}
