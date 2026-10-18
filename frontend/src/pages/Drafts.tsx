import { useMutation, useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { FileText } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { DraftDialog } from '../components/DraftDialog'
import { Badge, Card, EmptyState, ErrorState, Loading } from '../components/ui'
import { api } from '../lib/api'
import { fmtDateTime } from '../lib/format'
import type { Draft } from '../lib/types'

interface DraftRow extends Draft {
  supplier_name: string | null
  target_name: string | null
  language: string
  plan_id: string | null
}

const KIND: Record<string, { label: string; tone: 'info' | 'accent' | 'review' }> = {
  supplier: { label: 'Consulta al proveedor', tone: 'info' },
  alternate: { label: 'Consulta al alternativo', tone: 'accent' },
  verification: { label: 'Verificación de vínculo', tone: 'review' },
}

export default function Drafts() {
  const [kind, setKind] = useState('')
  const [open, setOpen] = useState<Draft | null>(null)
  const q = useQuery({ queryKey: ['drafts', kind], queryFn: () => api.get<{ items: DraftRow[]; total: number }>(`/api/drafts${kind ? `?kind=${kind}` : ''}`) })
  const load = useMutation({ mutationFn: (id: string) => api.get<Draft>(`/api/drafts/${id}`), onSuccess: setOpen })
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-bold sm:text-2xl">Borradores</h1>
        <p className="text-sm text-ink-2">Correos generados desde los planes de acción o a mano. Se editan, copian o descargan; la aplicación nunca los envía.</p>
      </div>
      <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1" role="group" aria-label="Filtrar por tipo">
        {[['', 'Todos'], ['supplier', 'Proveedor'], ['alternate', 'Alternativo'], ['verification', 'Verificación']].map(([id, label]) => (
          <button key={id} onClick={() => setKind(id)} aria-pressed={kind === id}
            className={clsx('min-h-9 shrink-0 rounded-full border px-3 text-sm font-semibold', kind === id ? 'border-accent bg-accent text-white' : 'border-line bg-surface text-ink-2 hover:bg-lavender')}>
            {label}
          </button>
        ))}
      </div>
      <Card>
        {q.isLoading ? <Loading /> : q.error || !q.data ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.data.items.length === 0 ? (
          <EmptyState title="Sin borradores" icon={<FileText className="size-8" aria-hidden />}>Se generan al crear los planes de acción de los incidentes activos.</EmptyState>
        ) : (
          <ul className="divide-y divide-line/70">
            {q.data.items.map((d) => (
              <li key={d.id} className="flex flex-wrap items-start justify-between gap-2 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap gap-1">
                    <Badge tone={KIND[d.kind]?.tone ?? 'info'}>{KIND[d.kind]?.label ?? d.kind}</Badge>
                    <Badge>{d.language.toUpperCase()}</Badge>
                    {d.edited && <Badge tone="ok">Editado</Badge>}
                    {d.plan_id && <Badge>Desde plan</Badge>}
                  </div>
                  <button onClick={() => load.mutate(d.id)} className="mt-1 block text-left font-semibold text-ink hover:text-accent-strong hover:underline">{d.subject}</button>
                  <p className="text-xs text-ink-2">
                    Para: {d.recipient ?? 'pendiente'} · {d.target_name ?? d.target_supplier_id}
                    {d.kind === 'alternate' && <> (alternativo de <Link className="underline" to={`/proveedores/${d.supplier_id}`}>{d.supplier_name}</Link>)</>}
                    {' · '}{fmtDateTime(d.updated_at)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <DraftDialog draft={open} onClose={() => setOpen(null)} />
    </div>
  )
}
