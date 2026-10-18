import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Newspaper, Search } from 'lucide-react'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ArticleItem } from '../components/ArticleItem'
import { Button, Card, EmptyState, ErrorState, Loading, Select } from '../components/ui'
import { api, qs } from '../lib/api'
import { POLL_MS, useApp } from '../lib/app-state'
import { SPLIT_LABEL } from '../lib/format'
import type { ArticleBrief, BatchProgress, Paged, Source } from '../lib/types'
import { ContextBanner } from './Overview'

const CHIPS = [
  { id: '', label: 'Todas' },
  { id: 'urgent', label: 'Urgentes' },
  { id: 'risk,urgent', label: 'Riesgo' },
  { id: 'positive', label: 'Positivas' },
  { id: 'recovery', label: 'Recuperación' },
  { id: 'linked,positive,recovery,risk,urgent', label: 'Vinculadas' },
  { id: 'unlinked', label: 'Sin vínculo' },
  { id: 'review', label: 'En revisión' },
  { id: 'pending,deferred', label: 'Pendientes' },
  { id: 'error', label: 'Con error' },
]

export default function News() {
  const { contextId } = useApp()
  const [params, setParams] = useSearchParams()
  const [rel, setRel] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const source = params.get('source') ?? ''
  const batch = params.get('batch') ?? ''
  const sources = useQuery({ queryKey: ['sources'], queryFn: () => api.get<{ items: Source[] }>('/api/sources'), enabled: contextId === 'rss' })
  const batches = useQuery({ queryKey: ['batches', contextId], queryFn: () => api.get<{ items: BatchProgress[] }>(`/api/batches?context_id=${contextId}`), enabled: contextId === 'exercise' })
  const q = useQuery({
    queryKey: ['articles', contextId, rel, search, source, batch, page],
    queryFn: () =>
      api.get<Paged<ArticleBrief> & { counts: Record<string, number> }>(
        `/api/articles${qs({ context_id: contextId, relevance: rel, q: search, source_id: contextId === 'rss' ? source : '', batch_id: contextId === 'exercise' ? batch : '', page, page_size: 25 })}`,
      ),
    refetchInterval: POLL_MS,
    placeholderData: (prev) => prev,
  })
  const pages = q.data ? Math.max(1, Math.ceil(q.data.total / q.data.page_size)) : 1
  const setParam = (k: string, v: string) => {
    const next = new URLSearchParams(params)
    if (v) next.set(k, v)
    else next.delete(k)
    setParams(next, { replace: true })
    setPage(1)
  }
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-bold sm:text-2xl">Noticias</h1>
        <p className="text-sm text-ink-2">{contextId === 'rss' ? 'Artículos RSS reales con su fuente y fecha original.' : 'Noticias del ejercicio en el orden original del archivo.'} Se muestran también las no vinculadas.</p>
      </div>
      <ContextBanner />
      <Card className="flex flex-col gap-3 p-3 sm:p-4">
        <div className="flex flex-wrap items-end gap-2">
          <label htmlFor="news-q" className="flex min-w-0 flex-1 flex-col gap-1 text-xs font-medium text-ink-2">
            Buscar en titular o resumen
            <span className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2" aria-hidden />
              <input id="news-q" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} className="min-h-11 w-full rounded-[10px] border border-line pl-9 pr-3 text-base sm:text-sm" />
            </span>
          </label>
          {contextId === 'rss' ? (
            <div className="w-full sm:w-56">
              <Select id="news-src" label="Fuente" value={source} onChange={(v) => setParam('source', v)} options={[{ value: '', label: 'Todas las fuentes' }, ...(sources.data?.items ?? []).map((s) => ({ value: s.id, label: s.name }))]} />
            </div>
          ) : (
            <div className="w-full sm:w-64">
              <Select id="news-batch" label="Lote" value={batch} onChange={(v) => setParam('batch', v)} options={[{ value: '', label: 'Todos los lotes' }, ...(batches.data?.items ?? []).filter((b) => b.kind === 'news').map((b) => ({ value: b.id, label: `${SPLIT_LABEL[b.split] ?? b.split} · ${b.sheet_name}` }))]} />
            </div>
          )}
        </div>
        <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1" role="group" aria-label="Filtrar por relevancia">
          {CHIPS.map((c) => (
            <button key={c.id} onClick={() => { setRel(c.id); setPage(1) }} aria-pressed={rel === c.id}
              className={clsx('min-h-9 shrink-0 rounded-full border px-3 text-sm font-semibold', rel === c.id ? 'border-accent bg-accent text-white' : 'border-line bg-surface text-ink-2 hover:bg-lavender')}>
              {c.label}
            </button>
          ))}
        </div>
      </Card>
      <Card aria-labelledby="news-list">
        <h2 id="news-list" className="sr-only">Resultados</h2>
        {q.isLoading ? (
          <Loading />
        ) : q.error || !q.data ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : q.data.items.length === 0 ? (
          <EmptyState title="No hay noticias con estos filtros" icon={<Newspaper className="size-8" aria-hidden />}>
            {contextId === 'rss' ? 'Si las fuentes no tienen novedades en 48 h, no aparecen artículos: se muestra la realidad del feed.' : 'Importa y analiza un lote del ejercicio.'}
          </EmptyState>
        ) : (
          <>
            <p className="px-4 pt-3 text-xs text-ink-2" aria-live="polite">{q.data.total} noticias</p>
            <ul>{q.data.items.map((a) => <ArticleItem key={a.id} a={a} />)}</ul>
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
