import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileUp, FlaskConical, KeyRound, PlugZap, Save, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { BatchPanel } from '../components/BatchPanel'
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, Loading, Notice } from '../components/ui'
import { api, ApiError } from '../lib/api'
import { POLL_MS, useApp } from '../lib/app-state'
import { SPLIT_LABEL, fmtDateTime, fmtDay, fmtNum, fmtPct } from '../lib/format'
import type { BatchProgress, EngineTest } from '../lib/types'

interface ImportResult {
  file_name: string
  sheets: { sheet: string; recognized_as: string | null; rows: number; columns: string[] }[]
  batches: { batch_id: string; kind: string; split?: string; sheet: string; status: string; rows: number; has_labels?: boolean; suppliers?: number; materials?: number; products?: number; label_columns_separated?: string[]; diagnostics: unknown[] }[]
}

interface Metrics {
  n: number
  positives_labelled: number
  confusion: { tp: number; fp: number; fn: number; tn: number }
  precision: number | null
  recall: number | null
  f1: number | null
}
interface EvalRun {
  id: string
  batch_id: string
  split: string
  policy_version: string
  model_id: string | null
  created_at: string
  metrics: {
    articles_total: number
    articles_evaluated: number
    risk: Metrics
    urgent: Metrics
    suppliers: { exact_set_match: number; n: number; exact_set_accuracy: number | null; id_precision: number | null; id_recall: number | null; id_counts: { tp: number; fp: number; fn: number } }
    excluded: { news_id: string; reason: string }[]
    caveat: string
  }
}

function MetricTable({ title, m }: { title: string; m: Metrics }) {
  return (
    <div className="rounded-lg border border-line p-3 text-sm">
      <p className="font-semibold">{title}</p>
      <p className="tabular text-xs text-ink-2">n = {m.n} · positivos etiquetados = {m.positives_labelled}</p>
      <table className="mt-2 text-xs tabular">
        <caption className="sr-only">Matriz de confusión {title}</caption>
        <tbody>
          <tr><th scope="row" className="pr-3 text-left font-medium text-ink-2">VP / FP</th><td>{m.confusion.tp} / {m.confusion.fp}</td></tr>
          <tr><th scope="row" className="pr-3 text-left font-medium text-ink-2">FN / VN</th><td>{m.confusion.fn} / {m.confusion.tn}</td></tr>
          <tr><th scope="row" className="pr-3 text-left font-medium text-ink-2">Precisión</th><td>{m.precision == null ? '—' : fmtPct(m.precision, 1)}</td></tr>
          <tr><th scope="row" className="pr-3 text-left font-medium text-ink-2">Recobrado</th><td>{m.recall == null ? '—' : fmtPct(m.recall, 1)}</td></tr>
          <tr><th scope="row" className="pr-3 text-left font-medium text-ink-2">F1</th><td>{m.f1 == null ? '—' : fmtNum(m.f1, 3)}</td></tr>
        </tbody>
      </table>
    </div>
  )
}

export default function Presenter() {
  const { presenter, openLogin, meta } = useApp()
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [msg, setMsg] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null)
  const batches = useQuery({ queryKey: ['batches', 'exercise'], queryFn: () => api.get<{ items: (BatchProgress & { kind: string })[] }>('/api/batches?context_id=exercise'), refetchInterval: POLL_MS, enabled: presenter })
  const manifest = useQuery({ queryKey: ['manifest'], queryFn: () => api.get<{ files: { path: string; purpose: string; source_name: string }[] }>('/api/imports/manifest'), enabled: presenter })
  const evals = useQuery({ queryKey: ['evals'], queryFn: () => api.get<{ items: EvalRun[] }>('/api/evaluations'), enabled: presenter })
  const onImported = (r: ImportResult) => {
    setResult(r)
    setMsg({ tone: 'ok', text: `Importado ${r.file_name}: ${r.batches.map((b) => `${b.sheet} (${b.status === 'already_imported' ? 'ya importado' : 'nuevo'})`).join(', ')}.` })
    qc.invalidateQueries()
  }
  const onErr = (e: unknown) => setMsg({ tone: 'err', text: e instanceof ApiError ? e.message : 'Error inesperado.' })
  const upload = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('context_id', 'exercise')
      return api.post<ImportResult>('/api/imports', fd)
    },
    onSuccess: onImported,
    onError: onErr,
  })
  const fromManifest = useMutation({ mutationFn: (path: string) => api.post<ImportResult>('/api/imports/manifest', { path }), onSuccess: onImported, onError: onErr })
  const engineTest = useMutation({ mutationFn: () => api.post<EngineTest>('/api/engine/test'), onSuccess: () => qc.invalidateQueries({ queryKey: ['meta'] }), onError: onErr })
  const evaluate = useMutation({ mutationFn: (id: string) => api.post<EvalRun>(`/api/evaluations/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ['evals'] }), onError: onErr })
  const [clock, setClock] = useState('')
  const setClockM = useMutation({ mutationFn: (date: string | null) => api.put<{ clock: string }>('/api/context/exercise/clock', { date }), onSuccess: (r) => { setMsg({ tone: 'ok', text: `Reloj del ejercicio: ${fmtDay(r.clock)}` }); qc.invalidateQueries() }, onError: onErr })
  const [thresholds, setThresholds] = useState<Record<string, string>>({})
  const [policyNote, setPolicyNote] = useState('')
  const policyM = useMutation({
    mutationFn: () => api.put<{ version: string; note: string }>('/api/policy', { thresholds: Object.fromEntries(Object.entries(thresholds).filter(([, v]) => v !== '').map(([k, v]) => [k, Number(v.replace(',', '.'))])), note: policyNote }),
    onSuccess: (r) => { setMsg({ tone: 'ok', text: `Política ${r.version} activa. ${r.note}` }); setThresholds({}); qc.invalidateQueries() },
    onError: onErr,
  })

  if (!presenter) {
    return (
      <Card>
        <EmptyState title="Acceso de presentador" icon={<KeyRound className="size-8" aria-hidden />} action={<Button variant="primary" onClick={openLogin}>Entrar</Button>}>
          Este panel permite importar Excel, analizar lotes, probar el motor, ajustar la política y evaluar con etiquetas.
        </EmptyState>
      </Card>
    )
  }
  const news = (batches.data?.items ?? []).filter((b) => b.kind === 'news')
  const lastTest = meta?.engine.last_test
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-bold sm:text-2xl">Panel de presentador</h1>
      {msg && <Notice tone={msg.tone === 'ok' ? 'ok' : 'urgent'} title={msg.tone === 'ok' ? 'Hecho' : 'Error'}>{msg.text}</Notice>}

      <Card aria-labelledby="eng-h">
        <CardHeader id="eng-h" title="Motor JEV" subtitle="POST https://api.typesafe.ai/v1/systemone · Bearer desde el servidor" action={
          <Button onClick={() => engineTest.mutate()} busy={engineTest.isPending} disabled={meta?.engine.mode !== 'jev'} icon={<PlugZap className="size-4" aria-hidden />}>Probar conexión</Button>} />
        <div className="flex flex-col gap-2 p-4 text-sm">
          {meta?.engine.mode === 'jev' ? (
            <p>Configurado · modelo solicitado <strong>{meta.engine.model}</strong></p>
          ) : meta?.engine.mode === 'fixture' ? (
            <p className="text-review">Modo fixture explícito (DEMO_FIXTURES_ENABLED). Falta {meta.engine.missing_variable} para el motor real.</p>
          ) : (
            <p className="text-review">Motor sin configurar. Variable necesaria en el servidor: <code className="rounded bg-lavender px-1">{meta?.engine.missing_variable ?? '—'}</code></p>
          )}
          {lastTest && (
            <p className={lastTest.ok ? 'text-ok' : 'text-urgent'}>
              Última prueba {fmtDateTime(lastTest.at)}: {lastTest.ok ? `OK · modelo devuelto ${lastTest.model} · ${lastTest.latency_ms} ms` : `${lastTest.code ?? 'error'} (HTTP ${lastTest.status ?? '—'}) · ${lastTest.message}`}
            </p>
          )}
          <p className="text-xs text-ink-2">Worker: {meta?.worker.alive ? `activo (señal ${fmtDateTime(meta.worker.last_heartbeat)})` : 'sin señal'} · Política {meta?.policy.version} ({meta?.policy.status})</p>
        </div>
      </Card>

      <Card aria-labelledby="imp-h">
        <CardHeader id="imp-h" title="Importar Excel" subtitle="Solo .xlsx, máx. 10 MB y 5.000 filas. Se detecta el esquema de cada hoja; las etiquetas se separan para evaluación." />
        <div className="flex flex-col gap-3 p-4">
          <div className="flex flex-wrap gap-2">
            <input ref={fileRef} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="sr-only" id="xlsx-file"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = '' }} />
            <Button variant="primary" onClick={() => fileRef.current?.click()} busy={upload.isPending} icon={<Upload className="size-4" aria-hidden />}>Seleccionar archivo .xlsx</Button>
          </div>
          {manifest.data && (
            <div>
              <p className="text-xs font-semibold text-ink-2">Entradas declaradas en el manifiesto del kit</p>
              <ul className="mt-1 flex flex-col gap-1">
                {manifest.data.files.map((f) => (
                  <li key={f.path} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line px-3 py-2 text-sm">
                    <span className="min-w-0"><span className="font-semibold">{f.path.split('/').pop()}</span> <span className="text-xs text-ink-2">· {f.purpose}</span></span>
                    <Button onClick={() => fromManifest.mutate(f.path)} busy={fromManifest.isPending && fromManifest.variables === f.path} icon={<FileUp className="size-4" aria-hidden />}>Importar</Button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {result && (
            <div className="rounded-lg bg-lavender p-3 text-xs">
              <p className="font-semibold">Reconocimiento de hojas</p>
              <ul className="mt-1">{result.sheets.map((s) => <li key={s.sheet}>{s.sheet}: {s.recognized_as ?? 'ignorada'} · {s.rows} filas</li>)}</ul>
              <ul className="mt-1">{result.batches.map((b) => <li key={b.batch_id}>{b.kind === 'catalog' ? `Catálogo: ${b.suppliers ?? b.rows} proveedores, ${b.materials ?? '—'} materiales, ${b.products ?? '—'} productos` : `${SPLIT_LABEL[b.split ?? ''] ?? b.split}: ${b.rows} filas${b.has_labels ? ', etiquetas separadas para evaluación' : ', sin etiquetas'}`} · {b.status === 'already_imported' ? 'ya importado (idempotente)' : 'creado'}</li>)}</ul>
            </div>
          )}
        </div>
      </Card>

      <Card aria-labelledby="lot-h">
        <CardHeader id="lot-h" title="Lotes del ejercicio" subtitle="Test y LiveDay son ejecución final: no se usan para ajustar preguntas ni umbrales." />
        <div className="flex flex-col gap-3 p-3 sm:p-4">
          {batches.isLoading ? <Loading /> : batches.error ? <ErrorState error={batches.error} /> : news.length === 0 ? <p className="text-sm text-ink-2">No hay lotes de noticias importados.</p> : news.map((b) => (
            <div key={b.id} className="flex flex-col gap-2">
              <BatchPanel batch={b} />
              {b.has_labels && (
                <Button variant="ghost" className="w-fit" onClick={() => evaluate.mutate(b.id)} busy={evaluate.isPending && evaluate.variables === b.id} icon={<FlaskConical className="size-4" aria-hidden />}>
                  Evaluar contra etiquetas ({SPLIT_LABEL[b.split]})
                </Button>
              )}
            </div>
          ))}
        </div>
      </Card>

      <Card aria-labelledby="ev-h">
        <CardHeader id="ev-h" title="Evaluación separada" subtitle="Solo visible para el presentador. Denominadores explícitos; muestra pequeña." />
        <div className="flex flex-col gap-3 p-4">
          {(evals.data?.items ?? []).length === 0 ? <p className="text-sm text-ink-2">Sin evaluaciones todavía.</p> : evals.data!.items.slice(0, 4).map((r) => (
            <div key={r.id} className="rounded-xl border border-line p-3">
              <p className="text-sm font-semibold">{SPLIT_LABEL[r.split] ?? r.split} · {fmtDateTime(r.created_at)} <Badge className="ml-1">política {r.policy_version}</Badge> <Badge>{r.model_id}</Badge></p>
              <p className="text-xs text-ink-2">{r.metrics.articles_evaluated} de {r.metrics.articles_total} filas evaluadas{r.metrics.excluded.length ? ` · excluidas: ${r.metrics.excluded.map((e) => e.news_id).join(', ')}` : ''}</p>
              <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
                <MetricTable title="Is_Risk" m={r.metrics.risk} />
                <MetricTable title="Urgent" m={r.metrics.urgent} />
                <div className="rounded-lg border border-line p-3 text-sm">
                  <p className="font-semibold">Proveedores</p>
                  <p className="tabular text-xs">Conjunto exacto: {r.metrics.suppliers.exact_set_match}/{r.metrics.suppliers.n}</p>
                  <p className="tabular text-xs">Precisión por ID: {r.metrics.suppliers.id_precision == null ? '—' : fmtPct(r.metrics.suppliers.id_precision, 1)} (VP {r.metrics.suppliers.id_counts.tp}, FP {r.metrics.suppliers.id_counts.fp})</p>
                  <p className="tabular text-xs">Recobrado por ID: {r.metrics.suppliers.id_recall == null ? '—' : fmtPct(r.metrics.suppliers.id_recall, 1)} (FN {r.metrics.suppliers.id_counts.fn})</p>
                </div>
              </div>
              <p className="mt-2 text-xs text-ink-2">{r.metrics.caveat}</p>
            </div>
          ))}
        </div>
      </Card>

      <Card aria-labelledby="clk-h">
        <CardHeader id="clk-h" title="Reloj lógico del ejercicio" subtitle="Por defecto, la fecha máxima de publicación analizada. Se usa para «Requiere actualización» (7 días)." />
        <form className="flex flex-wrap items-end gap-2 p-4" onSubmit={(e) => { e.preventDefault(); setClockM.mutate(clock || null) }}>
          <label className="flex flex-col gap-1 text-xs font-medium text-ink-2">Fecha<input type="date" value={clock} onChange={(e) => setClock(e.target.value)} className="min-h-11 rounded-[10px] border border-line px-3 text-base sm:text-sm" /></label>
          <Button type="submit" busy={setClockM.isPending}>Fijar</Button>
          <Button type="button" variant="ghost" onClick={() => setClockM.mutate(null)}>Usar fecha del lote</Button>
        </form>
      </Card>

      <Card aria-labelledby="pol-h">
        <CardHeader id="pol-h" title="Política de riesgo" subtitle={`Versión activa ${meta?.policy.version} · ${meta?.policy.status}. Parámetros iniciales de ingeniería, no calibración estadística.`} />
        <div className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-2">
          <div className="text-sm">
            <p className="font-semibold">Pesos (E = Σ w·x / Σ w disponibles)</p>
            <p className="tabular text-ink-2">C {meta?.policy.weights.C} · U {meta?.policy.weights.U} · B {meta?.policy.weights.B} · G {meta?.policy.weights.G}</p>
            <p className="mt-2 font-semibold">Bandas</p>
            <p className="text-ink-2">{meta?.policy.bands.map((b) => `${b.label_es} ≥ ${b.min}`).join(' · ')}</p>
            <p className="mt-2 font-semibold">Umbrales</p>
            <ul className="tabular text-ink-2">{Object.entries(meta?.policy.thresholds ?? {}).map(([k, v]) => <li key={k}>{k}: {v}</li>)}</ul>
          </div>
          <form className="flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); policyM.mutate() }}>
            <p className="text-sm font-semibold">Nueva versión de umbrales</p>
            <p className="text-xs text-ink-2">Crea una versión nueva registrada; los análisis existentes conservan la suya. No ajustar con test ni LiveDay.</p>
            <div className="grid grid-cols-2 gap-2">
              {Object.keys(meta?.policy.thresholds ?? {}).map((k) => (
                <label key={k} className="flex flex-col text-xs text-ink-2">{k}
                  <input inputMode="decimal" placeholder={String(meta?.policy.thresholds[k])} value={thresholds[k] ?? ''} onChange={(e) => setThresholds({ ...thresholds, [k]: e.target.value })} className="min-h-11 rounded-lg border border-line px-2 text-base text-ink sm:text-sm" />
                </label>
              ))}
            </div>
            <label className="flex flex-col text-xs text-ink-2">Motivo del cambio<input required minLength={3} value={policyNote} onChange={(e) => setPolicyNote(e.target.value)} className="min-h-11 rounded-lg border border-line px-2 text-base text-ink sm:text-sm" /></label>
            <Button type="submit" busy={policyM.isPending} icon={<Save className="size-4" aria-hidden />} disabled={!Object.values(thresholds).some(Boolean)}>Crear versión</Button>
          </form>
        </div>
      </Card>
    </div>
  )
}
