import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Bot, Cpu, Layers, Scale } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Badge, Card, CardHeader, ErrorState, Field, Loading, Notice } from '../components/ui'
import { api } from '../lib/api'
import { useApp } from '../lib/app-state'
import { fmtNum } from '../lib/format'

interface ModelConfig {
  jev_model: string
  question_version: string
  policy_version: string
  urgency_priority_threshold: number | null
  urgency_mode: string
  urgency_mode_description: string
  llm: { provider: string; model: string; available: boolean; role: string; adjudication_prompt_version: string; max_concurrency: number }
  decision_sources_accepted_pairs: Record<string, number>
  history: { version: string; note: string }[]
}
interface Voted {
  news_id: string
  is_risk: string
  urgent: string
  affected: string[]
  unanimous: boolean
  votes: { is_risk: string[]; urgent: string[]; ids: Record<string, number> }
}
interface Consensus {
  file: string
  stamp: string
  sheet: string
  rows: number
  unanimous_rows: number
  xlsx: string
  question_version: string | null
  urgency_mode: string | null
  runs: { run: number; elapsed_s: number; jev_s: number; llm_pairs: number; models: string[] }[]
  voted: Voted[]
}
interface Usage {
  window_hours: number
  jev: { calls: number; input_tokens: number; output_tokens: number; mean_latency_ms: number | null; cache_entries_total: number; by_stage: Record<string, number> }
  llm: { opinions_stored: number; failures: number; mean_latency_ms: number | null; input_tokens: number; output_tokens: number }
  note: string
}

const SOURCE_LABEL: Record<string, string> = { jev: 'JEV', 'regla+jev': 'Regla + JEV', regla: 'Regla', llm: 'IA', humano: 'Persona', '-': 'Sin fuente' }

function Votes({ values }: { values: string[] }) {
  return (
    <span className="inline-flex gap-0.5" aria-label={`Votos: ${values.join(', ')}`}>
      {values.map((v, i) => (
        <span key={i} className={clsx('tabular inline-flex size-5 items-center justify-center rounded text-[11px] font-bold', v === 'Y' ? 'bg-urgent-bg text-urgent' : 'bg-bg text-ink-2')}>{v}</span>
      ))}
    </span>
  )
}

export default function Model() {
  const { presenter } = useApp()
  const cfg = useQuery({ queryKey: ['model-config'], queryFn: () => api.get<ModelConfig>('/api/model/config') })
  const cons = useQuery({ queryKey: ['model-consensus'], queryFn: () => api.get<{ items: Consensus[] }>('/api/model/consensus') })
  const usage = useQuery({ queryKey: ['model-usage'], queryFn: () => api.get<Usage>('/api/model/usage'), refetchInterval: 15000 })
  if (cfg.isLoading) return <Loading />
  if (cfg.error || !cfg.data) return <ErrorState error={cfg.error} onRetry={() => cfg.refetch()} />
  const c = cfg.data
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-bold sm:text-2xl">Modelo</h1>
        <p className="text-sm text-ink-2">Qué decide cada pieza, cómo de estable es el resultado entre ejecuciones y cuánto se usa cada motor.</p>
      </div>

      <Card aria-labelledby="cfg-h">
        <CardHeader id="cfg-h" title="Configuración activa" subtitle={c.urgency_mode_description} />
        <dl className="grid grid-cols-2 gap-4 p-4 md:grid-cols-4">
          <Field label="Modelo de decisión"><span className="inline-flex items-center gap-1"><Cpu className="size-4 text-accent" aria-hidden /> {c.jev_model}</span></Field>
          <Field label="Preguntas JEV">{c.question_version}</Field>
          <Field label="Política">{c.policy_version}</Field>
          <Field label="Modo de urgencia (URGENCY_MODE)"><Badge tone="accent">{c.urgency_mode}</Badge></Field>
          <Field label="Umbral de prioridad">{c.urgency_priority_threshold ?? '—'}</Field>
          <Field label="LLM">
            <span className="inline-flex items-center gap-1"><Bot className="size-4 text-accent" aria-hidden /> {c.llm.provider === 'none' ? 'sin LLM' : `${c.llm.model}`}</span>
          </Field>
          <Field label="Papel del LLM">{c.llm.role}</Field>
          <Field label="Estado del LLM">{c.llm.available ? 'Disponible' : 'No disponible'} · prompt v{c.llm.adjudication_prompt_version}</Field>
        </dl>
        <div className="border-t border-line px-4 py-3 text-sm">
          <p className="flex items-center gap-1.5 font-semibold"><Scale className="size-4 text-accent" aria-hidden /> Quién decidió las parejas vinculadas (base local)</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {Object.entries(c.decision_sources_accepted_pairs).map(([k, n]) => <Badge key={k}>{SOURCE_LABEL[k] ?? k}: {n}</Badge>)}
          </div>
          <details className="mt-2 text-xs text-ink-2">
            <summary className="cursor-pointer font-semibold">Historial de versiones de preguntas</summary>
            <ul className="mt-1 list-disc pl-5">{c.history.map((h) => <li key={h.version}><strong>{h.version}</strong>: {h.note}</li>)}</ul>
          </details>
        </div>
      </Card>

      <Card aria-labelledby="cons-h">
        <CardHeader id="cons-h" title="Estabilidad: consenso de varias ejecuciones" subtitle="JEV no es determinista: cada ejecución completa repite las llamadas y se vota por mayoría (scripts/export_consensus.py)." />
        <div className="flex flex-col gap-4 p-3 sm:p-4">
          {cons.isLoading ? <Loading /> : !cons.data?.items.length ? (
            <p className="text-sm text-ink-2">Aún no hay consensos guardados en evaluation/runs.</p>
          ) : cons.data.items.map((r) => (
            <section key={r.file} className="min-w-0 rounded-xl border border-line p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-semibold">{r.sheet} · {r.stamp}</p>
                <div className="flex flex-wrap gap-1">
                  {r.urgency_mode && <Badge tone="accent">modo {r.urgency_mode}</Badge>}
                  {r.question_version && <Badge>preguntas {r.question_version}</Badge>}
                  <Badge tone={r.unanimous_rows === r.rows ? 'ok' : 'review'}>{r.unanimous_rows}/{r.rows} filas unánimes</Badge>
                </div>
              </div>
              <p className="mt-1 text-xs text-ink-2">
                Ejecuciones: {r.runs.map((x) => `${x.run}: ${fmtNum(x.elapsed_s, 1)} s${x.llm_pairs ? ` (${x.llm_pairs} al LLM)` : ''}`).join(' · ')} · archivo <span className="break-all">{r.xlsx}</span>
              </p>
              <div className="mt-2 overflow-x-auto">
                <table className="w-full min-w-[30rem] text-left text-sm">
                  <caption className="sr-only">Votos por fila del consenso {r.stamp}</caption>
                  <thead className="text-xs text-ink-2">
                    <tr><th scope="col" className="py-1">Noticia</th><th scope="col">Riesgo</th><th scope="col">Urgente</th><th scope="col">Proveedores (votos)</th><th scope="col">Resultado</th></tr>
                  </thead>
                  <tbody>
                    {r.voted.filter((v) => !v.unanimous).concat(r.voted.filter((v) => v.unanimous)).map((v) => (
                      <tr key={v.news_id} className={clsx('border-t border-line/70', !v.unanimous && 'bg-review-bg/60')}>
                        <td className="tabular py-1.5 font-semibold">{v.news_id}</td>
                        <td><Votes values={v.votes.is_risk} /></td>
                        <td><Votes values={v.votes.urgent} /></td>
                        <td className="tabular text-xs">{Object.entries(v.votes.ids).map(([id, n]) => `${id}×${n}`).join(', ') || '—'}</td>
                        <td className="tabular text-xs font-semibold">{v.is_risk}/{v.urgent}/{v.affected.join('; ') || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}
        </div>
      </Card>

      <Card aria-labelledby="use-h">
        <CardHeader id="use-h" title="Uso de los motores" subtitle={usage.data ? `Últimas ${usage.data.window_hours} h para JEV; opiniones del LLM acumuladas` : undefined} />
        {usage.data ? (
          <dl className="grid grid-cols-2 gap-4 p-4 md:grid-cols-4">
            <Field label="Llamadas JEV (24 h)">{usage.data.jev.calls}</Field>
            <Field label="Tokens JEV entrada / salida">{usage.data.jev.input_tokens.toLocaleString('es-ES')} / {usage.data.jev.output_tokens.toLocaleString('es-ES')}</Field>
            <Field label="Latencia media JEV">{usage.data.jev.mean_latency_ms != null ? `${fmtNum(usage.data.jev.mean_latency_ms / 1000, 1)} s` : '—'}</Field>
            <Field label="Respuestas JEV en caché">{usage.data.jev.cache_entries_total}</Field>
            <Field label="Opiniones del LLM">{usage.data.llm.opinions_stored} ({usage.data.llm.failures} fallidas)</Field>
            <Field label="Latencia media LLM">{usage.data.llm.mean_latency_ms != null ? `${fmtNum(usage.data.llm.mean_latency_ms / 1000, 1)} s` : '—'}</Field>
            <Field label="Tokens LLM entrada / salida">{usage.data.llm.input_tokens.toLocaleString('es-ES')} / {usage.data.llm.output_tokens.toLocaleString('es-ES')}</Field>
            <Field label="Coste">{usage.data.note}</Field>
          </dl>
        ) : <Loading />}
      </Card>

      <Notice tone="info" title="Métricas contra etiquetas" icon={<Layers className="size-4" aria-hidden />}>
        Las métricas de training y validación usan etiquetas y solo las ve el presentador.{' '}
        {presenter ? <Link to="/presentador" className="font-semibold underline">Ir al panel de presentador</Link> : 'Entra como presentador para verlas.'}
      </Notice>
    </div>
  )
}
