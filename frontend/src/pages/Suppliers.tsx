import * as Dialog from '@radix-ui/react-dialog'
import { useQuery } from '@tanstack/react-query'
import { Building2, Filter, Search, X } from 'lucide-react'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { SupplierCards, SupplierTable } from '../components/SupplierRanking'
import { Button, Card, EmptyState, ErrorState, Loading, Select } from '../components/ui'
import { api, qs } from '../lib/api'
import { POLL_MS, useApp } from '../lib/app-state'
import type { Paged, SupplierRow } from '../lib/types'
import { ContextBanner } from './Overview'

type Filters = { category: string; criticality: string; single_source: string; has_alternate: string; urgent: string; products: string; active_only: string }
const EMPTY: Filters = { category: '', criticality: '', single_source: '', has_alternate: '', urgent: '', products: '', active_only: '' }

function FilterFields({ f, set, categories }: { f: Filters; set: (f: Filters) => void; categories: string[] }) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-7">
      <Select id="f-cat" label="Categoría" value={f.category} onChange={(v) => set({ ...f, category: v })} options={[{ value: '', label: 'Todas' }, ...categories.map((c) => ({ value: c, label: c }))]} />
      <Select id="f-crit" label="Criticidad" value={f.criticality} onChange={(v) => set({ ...f, criticality: v })} options={[{ value: '', label: 'Todas' }, { value: 'High', label: 'Alta' }, { value: 'Medium', label: 'Media' }, { value: 'Low', label: 'Baja' }]} />
      <Select id="f-ss" label="Fuente única" value={f.single_source} onChange={(v) => set({ ...f, single_source: v })} options={[{ value: '', label: 'Indiferente' }, { value: 'Y', label: 'Sí' }, { value: 'N', label: 'No' }]} />
      <Select id="f-alt" label="Alternativo aprobado" value={f.has_alternate} onChange={(v) => set({ ...f, has_alternate: v })} options={[{ value: '', label: 'Indiferente' }, { value: 'true', label: 'Con alternativo' }, { value: 'false', label: 'Sin alternativo' }]} />
      <Select id="f-urg" label="Urgencia" value={f.urgent} onChange={(v) => set({ ...f, urgent: v })} options={[{ value: '', label: 'Todas' }, { value: 'true', label: 'Urgentes' }, { value: 'false', label: 'No urgentes' }]} />
      <Select id="f-prod" label="Productos" value={f.products} onChange={(v) => set({ ...f, products: v })} options={[{ value: '', label: 'Todos' }, { value: 'mapped', label: 'Productos conocidos' }, { value: 'unmapped', label: 'Productos no mapeados' }]} />
      <Select id="f-act" label="Incidentes" value={f.active_only} onChange={(v) => set({ ...f, active_only: v })} options={[{ value: '', label: 'Todos' }, { value: 'true', label: 'Solo con activos' }]} />
    </div>
  )
}

export default function Suppliers() {
  const { scope } = useApp()
  const [params, setParams] = useSearchParams()
  const [filters, setFilters] = useState<Filters>(EMPTY)
  const [draft, setDraft] = useState<Filters>(EMPTY)
  const [panel, setPanel] = useState(false)
  const [page, setPage] = useState(1)
  const search = params.get('q') ?? ''
  const q = useQuery({
    queryKey: ['suppliers', scope, search, filters, page],
    queryFn: () => api.get<Paged<SupplierRow> & { categories: string[] }>(`/api/suppliers${qs({ ...scope, q: search, page, page_size: 20, ...filters })}`),
    refetchInterval: POLL_MS,
    placeholderData: (prev) => prev,
  })
  const active = Object.values(filters).filter(Boolean).length
  const pages = q.data ? Math.max(1, Math.ceil(q.data.total / q.data.page_size)) : 1
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-bold sm:text-2xl">Proveedores</h1>
        <p className="text-sm text-ink-2">Con incidentes activos, orden por prioridad (máximo de sus incidentes); sin ellos, por índice de dependencia E (0–1: criticidad, fuente única, presión del buffer y concentración de gasto).</p>
      </div>
      <ContextBanner />
      <Card className="p-3 sm:p-4">
        <div className="flex flex-wrap items-end gap-2">
          <label htmlFor="sup-q" className="flex min-w-0 flex-1 flex-col gap-1 text-xs font-medium text-ink-2">
            Buscar
            <span className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2" aria-hidden />
              <input
                id="sup-q"
                value={search}
                onChange={(e) => {
                  setPage(1)
                  setParams(e.target.value ? { q: e.target.value } : {}, { replace: true })
                }}
                placeholder="Nombre, ID, ciudad, país, material"
                className="min-h-11 w-full rounded-[10px] border border-line bg-surface pl-9 pr-3 text-base text-ink sm:text-sm"
              />
            </span>
          </label>
          <Button className="lg:hidden" onClick={() => { setDraft(filters); setPanel(true) }} icon={<Filter className="size-4" aria-hidden />} aria-haspopup="dialog">
            Filtros{active ? ` (${active})` : ''}
          </Button>
        </div>
        <div className="mt-3 hidden lg:block">
          <FilterFields f={filters} set={(f) => { setPage(1); setFilters(f) }} categories={q.data?.categories ?? []} />
          {active > 0 && (
            <button className="mt-2 text-sm font-semibold text-accent-strong underline" onClick={() => setFilters(EMPTY)}>
              Limpiar filtros
            </button>
          )}
        </div>
      </Card>

      <Dialog.Root open={panel} onOpenChange={setPanel}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/40" />
          <Dialog.Content className="fixed inset-x-0 bottom-0 z-50 max-h-[90dvh] overflow-y-auto rounded-t-2xl bg-surface p-4 pb-8 fade-in">
            <div className="mb-3 flex items-center justify-between">
              <Dialog.Title className="text-base font-semibold">Filtros</Dialog.Title>
              <Dialog.Close className="rounded-md p-2 hover:bg-lavender" aria-label="Cerrar filtros">
                <X className="size-5" aria-hidden />
              </Dialog.Close>
            </div>
            <Dialog.Description className="sr-only">Filtra el listado de proveedores</Dialog.Description>
            <FilterFields f={draft} set={setDraft} categories={q.data?.categories ?? []} />
            <div className="mt-4 grid grid-cols-2 gap-2">
              <Button onClick={() => { setDraft(EMPTY); setFilters(EMPTY); setPanel(false) }}>Limpiar</Button>
              <Button variant="primary" onClick={() => { setPage(1); setFilters(draft); setPanel(false) }}>Aplicar</Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <Card aria-labelledby="sup-list">
        <h2 id="sup-list" className="sr-only">Listado</h2>
        {q.isLoading ? (
          <Loading />
        ) : q.error || !q.data ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : q.data.items.length === 0 ? (
          <EmptyState title="Ningún proveedor coincide" icon={<Building2 className="size-8" aria-hidden />}>
            {q.data.total === 0 && !search && !active ? 'No hay catálogo importado.' : 'Prueba a cambiar la búsqueda o los filtros.'}
          </EmptyState>
        ) : (
          <>
            <p className="px-4 pt-3 text-xs text-ink-2" aria-live="polite">{q.data.total} proveedores</p>
            <div className="p-2 md:p-0">
              <SupplierCards rows={q.data.items} />
              <SupplierTable rows={q.data.items} caption="Proveedores filtrados" />
            </div>
            {pages > 1 && (
              <nav className="flex items-center justify-between border-t border-line p-3" aria-label="Paginación">
                <Button disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</Button>
                <span className="tabular text-sm text-ink-2">Página {page} de {pages}</span>
                <Button disabled={page >= pages} onClick={() => setPage(page + 1)}>Siguiente</Button>
              </nav>
            )}
          </>
        )}
      </Card>
    </div>
  )
}
