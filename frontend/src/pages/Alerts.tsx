import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { BellOff, Check, CheckCheck, ShieldCheck, Volume2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { SoundControl } from '../components/Shell'
import { Badge, Button, Card, EmptyState, ErrorState, Loading, Notice, PriorityBadge, ReviewBadge } from '../components/ui'
import { api, ApiError } from '../lib/api'
import { useAlarm } from '../lib/alarm'
import { POLL_MS, useApp } from '../lib/app-state'
import { EVENT_LABEL, fmtDateTime, fmtNum, fmtPub } from '../lib/format'
import type { Alert, AlertsResponse } from '../lib/types'

type Tab = 'new' | 'ack' | 'resolved'

function ResolveDialog({ alert, onClose }: { alert: Alert | null; onClose: () => void }) {
  const qc = useQueryClient()
  const [note, setNote] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const m = useMutation({
    mutationFn: () => api.post(`/api/incidents/${alert!.incident_id}/resolve`, { note }),
    onSuccess: () => {
      qc.invalidateQueries()
      setNote('')
      onClose()
    },
    onError: (e) => setErr(e instanceof ApiError ? e.message : 'No se pudo resolver.'),
  })
  return (
    <Dialog.Root open={!!alert} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/40" />
        <Dialog.Content className="card fixed left-1/2 top-1/2 z-50 w-[min(92vw,460px)] -translate-x-1/2 -translate-y-1/2 p-5 fade-in">
          <Dialog.Title className="text-lg font-semibold">Resolver incidente</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-ink-2">
            {alert?.supplier_name}: la resolución manual se registra con su motivo y conserva el historial. Reconocer una alerta no resuelve el incidente.
          </Dialog.Description>
          <form className="mt-3 flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); m.mutate() }}>
            <label className="flex flex-col gap-1 text-sm font-medium">
              Motivo
              <textarea required minLength={5} value={note} onChange={(e) => setNote(e.target.value)} rows={3} className="rounded-[10px] border border-line p-2 text-base sm:text-sm" />
            </label>
            {err && <p role="alert" className="text-sm text-urgent">{err}</p>}
            <div className="flex justify-end gap-2">
              <Dialog.Close asChild><Button type="button" variant="ghost">Cancelar</Button></Dialog.Close>
              <Button type="submit" variant="primary" busy={m.isPending}>Resolver</Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export default function Alerts() {
  const { presenter, openLogin, contextId } = useApp()
  const { state } = useAlarm()
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('new')
  const [resolving, setResolving] = useState<Alert | null>(null)
  const q = useQuery({ queryKey: ['alerts', contextId], queryFn: () => api.get<AlertsResponse>(`/api/alerts?context_id=${contextId}&limit=200`), refetchInterval: POLL_MS })
  const ack = useMutation({ mutationFn: (id: string) => api.post(`/api/alerts/${id}/ack`), onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }) })
  const ackAll = useMutation({ mutationFn: () => api.post(`/api/alerts/ack-all?context_id=${contextId}`), onSuccess: () => qc.invalidateQueries() })
  if (q.isLoading) return <Loading />
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const items = q.data.items.filter((a) =>
    tab === 'resolved' ? a.incident_status === 'resolved' : a.incident_status !== 'resolved' && (tab === 'new' ? a.status === 'unread' : a.status === 'acknowledged'),
  )
  const counts = {
    new: q.data.items.filter((a) => a.incident_status !== 'resolved' && a.status === 'unread').length,
    ack: q.data.items.filter((a) => a.incident_status !== 'resolved' && a.status === 'acknowledged').length,
    resolved: q.data.items.filter((a) => a.incident_status === 'resolved').length,
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold sm:text-2xl">Alertas</h1>
          <p className="text-sm text-ink-2">Una alerta por revisión de incidente. Se consultan cada 3 s con la pestaña visible.</p>
        </div>
        <SoundControl />
      </div>
      {state !== 'armed' && (
        <Notice tone={state === 'blocked' ? 'urgent' : 'info'} title={state === 'blocked' ? 'El navegador bloqueó el audio' : state === 'muted' ? 'Silenciado' : 'Sonido desactivado'} icon={state === 'muted' ? <BellOff className="size-4" aria-hidden /> : <Volume2 className="size-4" aria-hidden />}>
          Las alertas siguen visibles aquí. El aviso sonoro requiere pulsar «Activar sonido» en esta pestaña; no funciona con la pestaña cerrada, el móvil bloqueado o el dispositivo en silencio.
        </Notice>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div role="tablist" aria-label="Estado de alertas" className="inline-flex rounded-xl border border-line bg-lavender p-1">
          {([['new', 'Nuevas'], ['ack', 'Reconocidas'], ['resolved', 'Resueltas']] as const).map(([id, label]) => (
            <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
              className={clsx('min-h-10 rounded-lg px-3 text-sm font-semibold', tab === id ? 'bg-surface text-ink shadow-sm' : 'text-ink-2')}>
              {label} <span className="tabular">({counts[id]})</span>
            </button>
          ))}
        </div>
        {tab === 'new' && counts.new > 0 && (presenter ? <Button onClick={() => ackAll.mutate()} busy={ackAll.isPending} icon={<CheckCheck className="size-4" aria-hidden />}>Reconocer todas</Button> : null)}
      </div>
      <Card>
        {items.length === 0 ? (
          <EmptyState title={tab === 'new' ? 'No hay alertas nuevas' : tab === 'ack' ? 'No hay alertas reconocidas' : 'No hay incidentes resueltos con alerta'} icon={<ShieldCheck className="size-8" aria-hidden />} />
        ) : (
          <ul className="divide-y divide-line/70">
            {items.map((a) => (
              <li key={a.id} className={clsx('px-4 py-3', a.status === 'unread' && a.incident_status !== 'resolved' && 'border-l-4 border-l-urgent')}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {a.urgent === 'Y' ? <Badge tone="urgent">Urgente</Badge> : a.kind === 'discrepancy' ? <Badge tone="review">Prioridad crítica sin urgencia: revisar</Badge> : <Badge tone="info">Prioridad alta</Badge>}
                      {a.needs_review && <ReviewBadge />}
                      {a.incident_status === 'resolved' && <Badge tone="ok">Incidente resuelto</Badge>}
                      {a.revision > 1 && <Badge tone="accent">Revisión {a.revision}</Badge>}
                      {a.sound_eligible ? <Badge tone="urgent" icon={<Volume2 className="size-3" aria-hidden />}>Sonora</Badge> : <Badge>Solo visual</Badge>}
                      <Badge>{a.context_id === 'rss' ? 'Noticias reales · exposición potencial' : 'Ejercicio'}</Badge>
                    </div>
                    <Link to={`/proveedores/${a.supplier_id}`} className="mt-1 block font-semibold hover:text-accent-strong hover:underline">{a.supplier_name} ({a.supplier_id})</Link>
                    {a.headline && <Link to={`/noticias/${a.article_id}`} className="block text-sm text-ink-2 hover:underline">{EVENT_LABEL[a.event_type ?? ''] ?? 'Evento'}: {a.headline}</Link>}
                    <p className="mt-1 text-xs text-ink-2">
                      {a.source_name} · {fmtPub(a.published_at, a.context_id)} · alerta {fmtDateTime(a.created_at)} · p vínculo {fmtNum(a.p_link, 2)} · p riesgo {fmtNum(a.p_risk, 2)} · p urgencia {fmtNum(a.p_urgent, 2)}
                    </p>
                  </div>
                  <PriorityBadge value={a.priority} band={a.priority_band} />
                </div>
                {a.incident_status !== 'resolved' && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {a.status === 'unread' && (presenter ? (
                      <Button onClick={() => ack.mutate(a.id)} busy={ack.isPending && ack.variables === a.id} icon={<Check className="size-4" aria-hidden />}>Reconocer</Button>
                    ) : (
                      <Button variant="ghost" onClick={openLogin}>Reconocer (presentador)</Button>
                    ))}
                    {presenter && <Button variant="ghost" onClick={() => setResolving(a)} icon={<ShieldCheck className="size-4" aria-hidden />}>Resolver incidente</Button>}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <ResolveDialog alert={resolving} onClose={() => setResolving(null)} />
    </div>
  )
}
