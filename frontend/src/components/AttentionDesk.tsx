import clsx from 'clsx'
import { ArrowUpRight, CalendarClock, ClipboardList } from 'lucide-react'
import { Link } from 'react-router-dom'
import { CRIT_LABEL, EVENT_LABEL, fmtNum } from '../lib/format'
import type { AttentionItem } from '../lib/types'
import { DecisionBadge } from './Decision'
import { Badge, EmptyState, PriorityBadge, ReviewBadge, UrgencyBadge } from './ui'

const DEADLINE: Record<string, { label: string; cls: string }> = {
  hoy: { label: 'Hoy', cls: 'bg-urgent text-white' },
  esta_semana: { label: 'Esta semana', cls: 'bg-review-bg text-review border border-review/30' },
  proximo_informe: { label: 'Próximo informe', cls: 'bg-bg text-ink-2 border border-line' },
}

export function AttentionDesk({ items }: { items: AttentionItem[] }) {
  if (!items.length) {
    return <EmptyState title="Nada que atender ahora" icon={<ClipboardList className="size-8" aria-hidden />}>No hay incidentes activos en este contexto.</EmptyState>
  }
  return (
    <ol className="grid grid-cols-1 gap-3 p-3 sm:p-4 md:grid-cols-2 xl:grid-cols-3">
      {items.map((it, i) => (
        <li key={it.incident_id} className={clsx('flex flex-col rounded-xl border bg-surface p-3', it.urgent === 'Y' ? 'border-urgent/30' : 'border-line')}>
          <div className="flex items-start justify-between gap-2">
            <span className="tabular text-xs font-bold text-ink-2">{String(i + 1).padStart(2, '0')}</span>
            <PriorityBadge value={it.priority} band={it.priority_band} />
          </div>
          <Link to={`/proveedores/${it.supplier_id}`} className="mt-1 inline-flex items-start gap-1 font-bold text-ink hover:text-accent-strong hover:underline">
            {it.supplier_name} <ArrowUpRight className="mt-0.5 size-4 shrink-0" aria-hidden />
          </Link>
          <p className="text-xs text-ink-2">{it.material} · {it.city}, {it.country}</p>
          <div className="mt-1.5 flex flex-wrap gap-1">
            <UrgencyBadge urgent={it.urgent} />
            {it.needs_review && <ReviewBadge />}
            <DecisionBadge source={it.decision_source} />
            {it.criticality && <Badge tone="accent">Criticidad {CRIT_LABEL[it.criticality] ?? it.criticality}</Badge>}
            {it.single_source === 'Y' && <Badge tone="accent">Fuente única</Badge>}
          </div>
          {it.headline && (
            <Link to={`/noticias/${it.article_id}`} className="mt-2 line-clamp-2 text-sm text-ink hover:underline">
              <span className="font-semibold">{EVENT_LABEL[it.event_type ?? ''] ?? 'Evento'}:</span> {it.headline}
            </Link>
          )}
          <div className="mt-auto pt-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-2">Siguiente acción</p>
            <ul className="mt-1 flex flex-col gap-1">
              {it.next_actions.map((a) => (
                <li key={a.code} className="flex flex-col gap-0.5 text-sm sm:flex-row sm:items-start sm:gap-2">
                  <span className={clsx('inline-flex w-fit items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-bold', DEADLINE[a.deadline]?.cls)}>
                    <CalendarClock className="size-3" aria-hidden /> {DEADLINE[a.deadline]?.label ?? a.deadline}
                  </span>
                  <span className="text-ink">{a.label}</span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-ink-2">
              Margen de stock: {typeof it.stock_margin === 'number' ? `${fmtNum(it.stock_margin, 0)} días` : (it.stock_margin ?? 'sin plan')}
              {' · '}Productos: {Array.isArray(it.products) ? it.products.join(', ') : it.products ?? '—'}
            </p>
            <Link to={`/proveedores/${it.supplier_id}`} className="mt-2 inline-flex min-h-11 items-center text-sm font-semibold text-accent-strong underline">
              Ver plan completo y borradores
            </Link>
          </div>
        </li>
      ))}
    </ol>
  )
}
