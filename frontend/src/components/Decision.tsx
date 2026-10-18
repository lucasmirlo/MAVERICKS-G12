import { Bot, Hourglass, Scale, UserCheck, Workflow } from 'lucide-react'
import type { DecisionSource, LlmDecision, LlmStatus } from '../lib/types'
import { Badge } from './ui'

const SOURCE: Record<DecisionSource, { label: string; tone: 'info' | 'accent' | 'ok' | 'neutral'; icon: typeof Scale; title: string }> = {
  jev: { label: 'JEV', tone: 'info', icon: Workflow, title: 'Urgencia según la pregunta de urgencia de JEV (modo jev)' },
  regla: { label: 'Regla', tone: 'neutral', icon: Scale, title: 'Decidió la regla de prioridad (sin segunda opinión concluyente)' },
  'regla+jev': { label: 'Regla + JEV', tone: 'info', icon: Workflow, title: 'La regla de prioridad y JEV coinciden: decisión firme' },
  llm: { label: 'IA', tone: 'accent', icon: Bot, title: 'Caso dudoso decidido por el modelo de lenguaje local' },
  humano: { label: 'Persona', tone: 'ok', icon: UserCheck, title: 'Decisión registrada por el presentador' },
}

export function DecisionBadge({ source, llmStatus }: { source: DecisionSource | null | undefined; llmStatus?: LlmStatus | null }) {
  if (llmStatus === 'pendiente') {
    return (
      <Badge tone="review" icon={<Hourglass className="size-3.5" aria-hidden />} title="Caso dudoso esperando la segunda opinión de la IA">
        En análisis (IA)
      </Badge>
    )
  }
  if (!source) return null
  const s = SOURCE[source]
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <Badge tone={s.tone} icon={<s.icon className="size-3.5" aria-hidden />} title={s.title}>
        Decide: {s.label}
      </Badge>
      {llmStatus === 'sin_segunda_opinion' && <Badge tone="review" title="El LLM no respondió; se conserva la regla">Sin segunda opinión</Badge>}
      {llmStatus === 'baja_confianza' && <Badge tone="review" title="La IA no tuvo confianza suficiente; revisión humana">IA: baja confianza</Badge>}
    </span>
  )
}

export function LlmReasoning({ decision, status }: { decision: LlmDecision | null | undefined; status?: LlmStatus | null }) {
  if (!decision) return null
  if (decision.error) {
    return <p className="mt-2 text-xs text-review">Sin opinión de la IA ({decision.error}); la decisión no depende de ella salvo en modo llm.</p>
  }
  if (!decision.razonamiento) return null
  return (
    <div className="mt-2 rounded-lg border border-accent/25 bg-lavender p-3 text-sm">
      <p className="flex flex-wrap items-center gap-1.5 text-xs font-semibold text-accent-strong">
        <Bot className="size-3.5" aria-hidden /> Opinión de la IA · confianza {decision.confianza}
        {status === 'baja_confianza' && ' · propuesta pendiente de revisión humana'}
      </p>
      <p className="mt-1 leading-relaxed text-ink">{decision.razonamiento}</p>
      <p className="mt-1 text-xs text-ink-2">
        Propone: vinculado {decision.vinculado ? 'sí' : 'no'} · riesgo {decision.es_riesgo ? 'sí' : 'no'} · urgente {decision.urgente ? 'sí' : 'no'}
        {decision.meta?.model ? ` · ${decision.meta.model}` : ''}
        {decision.meta?.latency_ms ? ` · ${(decision.meta.latency_ms / 1000).toFixed(1)} s` : ''}
      </p>
    </div>
  )
}
