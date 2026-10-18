import { useQuery } from '@tanstack/react-query'
import { Boxes, Package } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ContextBanner } from './Overview'
import { Badge, Card, CardHeader, EmptyState, ErrorState, Loading, PriorityBadge } from '../components/ui'
import { api, qs } from '../lib/api'
import { POLL_MS, useApp } from '../lib/app-state'
import { fmtNum } from '../lib/format'

interface Side {
  supplier_id: string
  name: string
  city: string | null
  country: string | null
  single_source: string | null
  inventory_days: number | null
  risk: { priority: number | null; urgent: boolean; incidents: number } | null
}
interface MaterialRow {
  material_id: string
  name: string
  category: string | null
  monthly_requirement: number | null
  unit: string | null
  products: string[]
  primary: Side | null
  alternate: Side | null
  status: 'sin_salida' | 'con_alternativo' | 'alternativo_afectado' | 'sin_incidentes'
}

const STATUS: Record<MaterialRow['status'], { label: string; tone: 'urgent' | 'review' | 'info' | 'ok' }> = {
  sin_salida: { label: 'Principal afectado sin alternativo libre', tone: 'urgent' },
  con_alternativo: { label: 'Principal afectado · hay alternativo libre', tone: 'review' },
  alternativo_afectado: { label: 'Solo el alternativo está afectado', tone: 'info' },
  sin_incidentes: { label: 'Sin incidentes activos', tone: 'ok' },
}

function SupplierCell({ s, role }: { s: Side | null; role: string }) {
  if (!s) return <p className="text-sm text-ink-2">Sin {role} aprobado</p>
  return (
    <div className="min-w-0">
      <Link to={`/proveedores/${s.supplier_id}`} className="font-semibold text-ink hover:text-accent-strong hover:underline">{s.name}</Link>
      <p className="text-xs text-ink-2">{s.supplier_id} · {s.city}, {s.country}{s.inventory_days != null ? ` · cobertura ${fmtNum(s.inventory_days, 0)} días` : ''}</p>
      {s.risk ? (
        <div className="mt-1 flex flex-wrap items-center gap-1">
          <PriorityBadge value={s.risk.priority} />
          {s.risk.urgent && <Badge tone="urgent">Urgente</Badge>}
          <Badge>{s.risk.incidents} incidente{s.risk.incidents === 1 ? '' : 's'}</Badge>
        </div>
      ) : <Badge tone="ok" className="mt-1">Sin incidente activo</Badge>}
    </div>
  )
}

export default function Materials() {
  const { scope } = useApp()
  const q = useQuery({
    queryKey: ['materials', scope],
    queryFn: () => api.get<{ items: MaterialRow[]; products: string[]; suppliers_without_material: string[] }>(`/api/materials${qs(scope)}`),
    refetchInterval: POLL_MS,
  })
  if (q.isLoading) return <Loading />
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-bold sm:text-2xl">Materiales</h1>
        <p className="text-sm text-ink-2">Qué material queda sin salida si su proveedor principal está afectado, con el alternativo aprobado y los productos en juego.</p>
      </div>
      <ContextBanner />
      <Card aria-labelledby="mat-h">
        <CardHeader id="mat-h" title={`${d.items.length} materiales · ${d.products.length} productos`} subtitle="Orden: sin salida primero, después por prioridad del principal." />
        {d.items.length === 0 ? <EmptyState title="Sin materiales" icon={<Boxes className="size-8" aria-hidden />}>Importa el catálogo del ejercicio.</EmptyState> : (
          <ul className="divide-y divide-line/70">
            {d.items.map((m) => (
              <li key={m.material_id} className="grid grid-cols-1 gap-3 px-4 py-3 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,1fr)]">
                <div className="min-w-0">
                  <p className="flex items-center gap-1.5 font-bold text-ink"><Boxes className="size-4 text-accent" aria-hidden /> {m.name}</p>
                  <p className="text-xs text-ink-2">{m.material_id} · {m.category}{m.monthly_requirement != null ? ` · ${fmtNum(m.monthly_requirement, 0)} ${m.unit ?? ''}/mes` : ''}</p>
                  <Badge tone={STATUS[m.status].tone} className="mt-1">{STATUS[m.status].label}</Badge>
                  <p className="mt-1 flex items-start gap-1 text-xs text-ink"><Package className="mt-0.5 size-3.5 shrink-0 text-ink-2" aria-hidden /> {m.products.join(', ') || 'Productos no mapeados'}</p>
                </div>
                <div><p className="text-xs font-semibold uppercase tracking-wide text-ink-2">Principal</p><SupplierCell s={m.primary} role="principal" /></div>
                <div><p className="text-xs font-semibold uppercase tracking-wide text-ink-2">Alternativo aprobado</p><SupplierCell s={m.alternate} role="alternativo" /></div>
              </li>
            ))}
          </ul>
        )}
      </Card>
      {d.suppliers_without_material.length > 0 && (
        <Card aria-labelledby="nomat-h">
          <CardHeader id="nomat-h" title="Proveedores sin material en la hoja Materials" subtitle="Siguen en la evaluación de noticias; sus productos figuran como «Productos no mapeados»." />
          <div className="flex flex-wrap gap-1.5 p-4">
            {d.suppliers_without_material.map((s) => <Link key={s} to={`/proveedores/${s}`} className="rounded-full border border-line px-2 py-0.5 text-xs font-semibold hover:bg-lavender">{s}</Link>)}
          </div>
        </Card>
      )}
    </div>
  )
}
