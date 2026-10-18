import { ChevronRight, Clock3, Layers } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useApp } from '../lib/app-state'
import { CRIT_LABEL, EVENT_LABEL, FACTOR_LABEL, fmtNum, fmtPub } from '../lib/format'
import type { SupplierRow } from '../lib/types'
import { Badge, PriorityBadge, ReviewBadge, UrgencyBadge } from './ui'

export function DependencyMeter({ row, compact }: { row: SupplierRow; compact?: boolean }) {
  const e = row.dependency_index
  if (e === null || e === undefined) return <span className="text-xs text-ink-2">—</span>
  const parts = (['C', 'U', 'B', 'G'] as const)
    .filter((k) => row.dependency_factors[k] !== undefined)
    .map((k) => `${FACTOR_LABEL[k]} ${fmtNum(row.dependency_factors[k]!, 2)} (peso ${fmtNum(row.dependency_weights[k], 2)})`)
  const omitted = (['C', 'U', 'B', 'G'] as const).filter((k) => row.dependency_factors[k] === undefined).map((k) => FACTOR_LABEL[k])
  const title = `Índice de dependencia E = media ponderada de: ${parts.join('; ')}${omitted.length ? `. Omitidos: ${omitted.join(', ')}` : ''}`
  return (
    <span className="inline-flex items-center gap-2" title={title} aria-label={`Índice de dependencia ${fmtNum(e, 2)} de 1. ${title}`}>
      <span className="h-1.5 w-14 rounded-full bg-line" aria-hidden>
        <span className="block h-1.5 rounded-full bg-accent" style={{ width: `${Math.min(100, e * 100)}%` }} />
      </span>
      <span className="tabular text-xs font-semibold text-ink">{fmtNum(e, 2)}</span>
      {!compact && <span className="hidden text-[11px] text-ink-2 xl:inline">{(['C', 'U', 'B', 'G'] as const).filter((k) => row.dependency_factors[k] !== undefined).map((k) => `${k} ${fmtNum(row.dependency_factors[k]!, 2)}`).join(' · ')}</span>}
    </span>
  )
}

function Reason({ row }: { row: SupplierRow }) {
  if (!row.reason) {
    return <span className="text-ink-2">{row.resolved_incidents ? 'Sin riesgo activo · con historial' : 'Sin incidentes activos'}</span>
  }
  return (
    <span className="line-clamp-1 text-ink">
      <span className="font-medium">{EVENT_LABEL[row.reason.event_type ?? ''] ?? 'Evento'}:</span> {row.reason.headline}
    </span>
  )
}

function Flags({ row }: { row: SupplierRow }) {
  return (
    <span className="flex flex-wrap gap-1">
      <UrgencyBadge urgent={row.urgent} isRisk={row.active_incidents ? 'Y' : 'N'} />
      {row.needs_review && <ReviewBadge />}
      {row.requires_update && (
        <Badge tone="review" icon={<Clock3 className="size-3.5" aria-hidden />}>
          Requiere actualización
        </Badge>
      )}
      {row.active_incidents > 1 && (
        <Badge tone="accent" icon={<Layers className="size-3.5" aria-hidden />}>
          {row.active_incidents} incidentes
        </Badge>
      )}
    </span>
  )
}

export function SupplierCards({ rows }: { rows: SupplierRow[] }) {
  return (
    <ul className="flex flex-col gap-2 md:hidden">
      {rows.map((r) => (
        <li key={r.supplier_id} className="card p-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-semibold text-ink">{r.name}</p>
              <p className="text-xs text-ink-2">
                {r.supplier_id} · {r.city}, {r.country}
              </p>
            </div>
            {r.active_incidents || r.priority_pending ? <PriorityBadge value={r.priority} band={r.priority_band} pending={r.priority_pending} /> : <Badge>Sin activo</Badge>}
          </div>
          <p className="mt-2 text-sm">
            <Reason row={r} />
          </p>
          <p className="mt-1 flex items-center gap-2 text-xs text-ink-2">Índice de dependencia <DependencyMeter row={r} compact /></p>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
            <Flags row={r} />
            <Link
              to={`/proveedores/${r.supplier_id}`}
              className="inline-flex min-h-11 items-center gap-1 rounded-[10px] px-2 text-sm font-semibold text-accent-strong hover:bg-lavender"
              aria-label={`Ver detalle de ${r.name}`}
            >
              Ver detalle <ChevronRight className="size-4" aria-hidden />
            </Link>
          </div>
        </li>
      ))}
    </ul>
  )
}

export function SupplierTable({ rows, caption }: { rows: SupplierRow[]; caption: string }) {
  const { contextId } = useApp()
  return (
    <div className="hidden overflow-x-auto md:block">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="border-b border-line text-xs uppercase tracking-wide text-ink-2">
          <tr>
            <th scope="col" className="px-4 py-2 font-semibold">Proveedor</th>
            <th scope="col" className="px-2 py-2 font-semibold">Material</th>
            <th scope="col" className="px-2 py-2 font-semibold">Prioridad</th>
            <th scope="col" className="px-2 py-2 font-semibold">Estado</th>
            <th scope="col" className="px-2 py-2 font-semibold">Criticidad</th>
            <th scope="col" className="px-2 py-2 font-semibold">Fuente única</th>
            <th scope="col" className="px-2 py-2 font-semibold" title="E de 0 a 1: criticidad, fuente única, presión del buffer y concentración de gasto">Índice de dependencia</th>
            <th scope="col" className="px-2 py-2 font-semibold">Evidencia</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.supplier_id} className="border-b border-line/70 align-top last:border-0 hover:bg-bg">
              <td className="px-4 py-2.5">
                <Link to={`/proveedores/${r.supplier_id}`} className="font-semibold text-ink hover:text-accent-strong hover:underline">
                  {r.name}
                </Link>
                <div className="text-xs text-ink-2">
                  {r.supplier_id} · {r.city}, {r.country}
                </div>
                <div className="mt-1 max-w-[28rem] text-xs">
                  <Reason row={r} />
                </div>
              </td>
              <td className="max-w-[12rem] px-2 py-2.5 text-ink-2">{r.material}</td>
              <td className="px-2 py-2.5">
                {r.active_incidents || r.priority_pending ? <PriorityBadge value={r.priority} band={r.priority_band} pending={r.priority_pending} /> : <span className="text-xs text-ink-2">Sin activo</span>}
              </td>
              <td className="px-2 py-2.5">
                <Flags row={r} />
              </td>
              <td className="px-2 py-2.5">{CRIT_LABEL[r.criticality ?? ''] ?? '—'}</td>
              <td className="px-2 py-2.5">{r.single_source === 'Y' ? <Badge tone="accent">Sí</Badge> : 'No'}</td>
              <td className="px-2 py-2.5"><DependencyMeter row={r} /></td>
              <td className="tabular whitespace-nowrap px-2 py-2.5 text-xs text-ink-2">{r.reason?.published_at ? fmtPub(r.reason.published_at, contextId) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
