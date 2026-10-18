import { useMutation } from '@tanstack/react-query'
import clsx from 'clsx'
import { Bot, CalendarClock, FileText, Package, Repeat2 } from 'lucide-react'
import { useState } from 'react'
import { api, ApiError } from '../lib/api'
import { fmtDay } from '../lib/format'
import type { ActionPlan, Draft } from '../lib/types'
import { DraftDialog } from './DraftDialog'
import { Badge, Button } from './ui'

const DEADLINE_TONE: Record<string, string> = {
  hoy: 'bg-urgent text-white',
  esta_semana: 'bg-review-bg text-review border border-review/30',
  proximo_informe: 'bg-bg text-ink-2 border border-line',
}

export function ActionPlanCard({ plan }: { plan: ActionPlan }) {
  const [draft, setDraft] = useState<Draft | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const open = useMutation({
    mutationFn: (id: string) => api.get<Draft>(`/api/drafts/${id}`),
    onSuccess: (d) => setDraft(d),
    onError: (e) => setErr(e instanceof ApiError ? e.message : 'No se pudo abrir el borrador.'),
  })
  const f = plan.facts
  const margin = f.stock.margen_dias
  return (
    <section aria-label="Plan de acción" className="mt-3 rounded-xl border border-line bg-surface p-3 sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-bold text-ink">Plan de acción</h3>
        <span className="text-xs text-ink-2">Reglas v{plan.rules_version} · acciones elegidas por reglas; cifras de la base de datos</span>
      </div>
      <ol className="mt-2 flex flex-col gap-1.5">
        {plan.actions.map((a) => (
          <li key={a.code} className="flex flex-col gap-1 text-sm sm:flex-row sm:items-start sm:gap-2">
            <span className={clsx('inline-flex w-fit items-center justify-center gap-1 rounded-md px-2 py-0.5 text-xs font-bold sm:min-w-[7.5rem]', DEADLINE_TONE[a.deadline])}>
              <CalendarClock className="size-3.5" aria-hidden /> {a.deadline_label}
            </span>
            <span className="min-w-0 flex-1">
              <span className="font-semibold text-ink">{a.label}</span>
              <span className="block text-xs text-ink-2">{a.reason}</span>
            </span>
          </li>
        ))}
      </ol>
      <dl className="mt-3 grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs text-ink-2">Margen de stock</dt>
          <dd className="font-semibold">
            {typeof margin === 'number' ? `${margin} días` : margin === 'no aplica' ? 'No aplica (logística o servicios)' : 'No informado'}
          </dd>
          {f.stock.fecha_rotura_si_continua && <dd className="text-xs text-ink-2">Rotura estimada si la parada continúa: {fmtDay(f.stock.fecha_rotura_si_continua)}</dd>}
        </div>
        <div>
          <dt className="flex items-center gap-1 text-xs text-ink-2"><Package className="size-3.5" aria-hidden /> Productos en juego</dt>
          <dd className="font-semibold">{Array.isArray(f.productos) ? f.productos.join(', ') : f.productos}</dd>
        </div>
        <div>
          <dt className="flex items-center gap-1 text-xs text-ink-2"><Repeat2 className="size-3.5" aria-hidden /> Alternativo aprobado</dt>
          <dd className="font-semibold">
            {f.alternativo ? `${f.alternativo.nombre} (${f.alternativo.ciudad})` : 'Sin alternativo aprobado'}
          </dd>
          {f.alternativo && (
            <dd>{f.alternativo.afectado ? <Badge tone="urgent">También afectado</Badge> : <Badge tone="ok">Sin incidente activo · stock sin confirmar</Badge>}</dd>
          )}
        </div>
      </dl>
      <p className="mt-3 text-sm leading-relaxed text-ink">
        {plan.summary_source === 'llm' && <Badge tone="accent" className="mr-1.5" icon={<Bot className="size-3" aria-hidden />}>Redactado por IA</Badge>}
        {plan.summary}
      </p>
      {plan.summary_error && <p className="mt-1 text-xs text-ink-2">{plan.summary_error}</p>}
      {plan.drafts.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {plan.drafts.map((d) => (
            <Button key={d.id} onClick={() => open.mutate(d.id)} busy={open.isPending && open.variables === d.id} icon={<FileText className="size-4" aria-hidden />}>
              {d.kind === 'alternate' ? 'Correo al alternativo' : d.kind === 'verification' ? 'Verificar vínculo' : 'Correo al proveedor'} ({d.language.toUpperCase()})
            </Button>
          ))}
        </div>
      )}
      {err && <p role="alert" className="mt-2 text-sm text-urgent">{err}</p>}
      <DraftDialog draft={draft} onClose={() => setDraft(null)} />
    </section>
  )
}
