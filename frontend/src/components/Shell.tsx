import * as Dialog from '@radix-ui/react-dialog'
import clsx from 'clsx'
import {
  Bell,
  BellRing,
  Building2,
  FileSpreadsheet,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Menu,
  Newspaper,
  Radio,
  Rss,
  Search,
  Settings2,
  Volume2,
  VolumeX,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../lib/api'
import { useAlarm } from '../lib/alarm'
import { useApp } from '../lib/app-state'
import { SPLIT_LABEL, fmtTime } from '../lib/format'
import type { ContextId } from '../lib/types'
import { Button } from './ui'

const NAV = [
  { to: '/', label: 'Resumen', icon: LayoutDashboard, end: true },
  { to: '/proveedores', label: 'Proveedores', icon: Building2 },
  { to: '/noticias', label: 'Noticias', icon: Newspaper },
  { to: '/alertas', label: 'Alertas', icon: Bell },
  { to: '/fuentes', label: 'Fuentes', icon: Rss },
]

function Logo({ compact }: { compact?: boolean }) {
  return (
    <Link to="/" className="flex items-center gap-2 rounded-lg" aria-label="Supplier Risk Radar, ir al resumen">
      <img src="/favicon.svg" alt="" className="size-8" />
      {!compact && (
        <span className="leading-tight">
          <span className="block text-sm font-bold text-ink">Supplier Risk Radar</span>
          <span className="block text-xs text-ink-2">Helixa Pharmaceuticals</span>
        </span>
      )}
    </Link>
  )
}

export function ContextSwitch({ className }: { className?: string }) {
  const { contextId, setContextId } = useApp()
  const { unreadByContext } = useAlarm()
  const opts: { id: ContextId; label: string }[] = [
    { id: 'exercise', label: 'Ejercicio' },
    { id: 'rss', label: 'Noticias reales' },
  ]
  return (
    <div role="radiogroup" aria-label="Contexto de datos" className={clsx('inline-flex rounded-xl border border-line bg-lavender p-1', className)}>
      {opts.map((o) => (
        <button
          key={o.id}
          role="radio"
          aria-checked={contextId === o.id}
          onClick={() => setContextId(o.id)}
          className={clsx(
            'relative min-h-9 rounded-lg px-3 text-sm font-semibold transition-colors',
            contextId === o.id ? 'bg-surface text-ink shadow-sm' : 'text-ink-2 hover:text-ink',
          )}
        >
          {o.label}
          {(unreadByContext[o.id] ?? 0) > 0 && (
            <span className="tabular ml-1.5 rounded-full bg-urgent px-1.5 text-[11px] text-white" aria-label={`${unreadByContext[o.id]} alertas sin leer`}>
              {unreadByContext[o.id]}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}

export function SoundControl({ compact }: { compact?: boolean }) {
  const { state, enable, test, setMuted, lastPlayedAt } = useAlarm()
  const status: Record<string, string> = {
    off: 'Sonido desactivado',
    armed: 'Sonido activado',
    muted: 'Silenciado',
    blocked: 'El navegador bloqueó el audio',
    unsupported: 'Audio no disponible en este navegador',
  }
  return (
    <div className="flex items-center gap-1.5" aria-live="polite">
      {state === 'off' || state === 'blocked' ? (
        <Button variant={state === 'blocked' ? 'danger' : 'primary'} onClick={() => void enable()} icon={<Volume2 className="size-4" aria-hidden />} className={compact ? 'px-3' : ''}>
          {compact ? <span className="sr-only sm:not-sr-only">Activar sonido</span> : 'Activar sonido'}
        </Button>
      ) : state === 'unsupported' ? (
        <span className="text-xs text-ink-2">{status.unsupported}</span>
      ) : (
        <>
          <Button variant="secondary" onClick={test} icon={<BellRing className="size-4" aria-hidden />} className={compact ? 'px-3' : ''} title="Reproduce un tono corto sin crear incidentes">
            <span className={compact ? 'sr-only lg:not-sr-only' : ''}>Probar alarma</span>
          </Button>
          <Button
            variant={state === 'muted' ? 'danger' : 'ghost'}
            onClick={() => setMuted(state !== 'muted')}
            aria-pressed={state === 'muted'}
            icon={state === 'muted' ? <VolumeX className="size-4" aria-hidden /> : <Volume2 className="size-4" aria-hidden />}
            className="px-3"
          >
            <span className={compact ? 'sr-only' : 'sr-only xl:not-sr-only'}>{state === 'muted' ? 'Reactivar' : 'Silenciar'}</span>
          </Button>
        </>
      )}
      <span className="sr-only">
        {status[state]}
        {lastPlayedAt ? `. Último aviso sonoro a las ${fmtTime(new Date(lastPlayedAt).toISOString())}` : ''}
      </span>
    </div>
  )
}

export function LoginDialog() {
  const { loginOpen, closeLogin, refreshSession, session } = useApp()
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.post('/api/session', { password })
      setPassword('')
      await refreshSession()
      closeLogin()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo iniciar sesión.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Dialog.Root open={loginOpen} onOpenChange={(o) => (o ? null : closeLogin())}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/40" />
        <Dialog.Content className="card fixed left-1/2 top-1/2 z-50 w-[min(92vw,420px)] -translate-x-1/2 -translate-y-1/2 p-5 fade-in">
          <Dialog.Title className="text-lg font-semibold">Acceso de presentador</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-ink-2">
            Necesario para cargar archivos, analizar, sincronizar RSS, cambiar la política y generar borradores. La consulta es pública.
          </Dialog.Description>
          {session && !session.login_available ? (
            <p className="mt-4 rounded-lg bg-review-bg p-3 text-sm text-review">El servidor no tiene configurado el acceso de presentador.</p>
          ) : (
            <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
              <label className="flex flex-col gap-1 text-sm font-medium">
                Contraseña compartida
                <input
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="min-h-11 rounded-[10px] border border-line px-3 text-base"
                />
              </label>
              {error && (
                <p role="alert" className="text-sm text-urgent">
                  {error}
                </p>
              )}
              <div className="flex justify-end gap-2">
                <Dialog.Close asChild>
                  <Button type="button" variant="ghost">
                    Cancelar
                  </Button>
                </Dialog.Close>
                <Button type="submit" variant="primary" busy={busy}>
                  Entrar
                </Button>
              </div>
            </form>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function PresenterButton({ compact }: { compact?: boolean }) {
  const { presenter, openLogin, refreshSession } = useApp()
  const qc = useQueryClient()
  if (presenter) {
    return (
      <div className="flex items-center gap-1">
        <Link to="/presentador" className="inline-flex min-h-11 items-center gap-2 rounded-[10px] bg-lavender px-3 text-sm font-semibold text-accent-strong hover:bg-lavender-strong">
          <Settings2 className="size-4" aria-hidden /> <span className={compact ? 'sr-only' : ''}>Presentador</span>
        </Link>
        <Button
          variant="ghost"
          className="px-3"
          aria-label="Cerrar sesión de presentador"
          onClick={async () => {
            await api.del('/api/session')
            await refreshSession()
            qc.invalidateQueries()
          }}
          icon={<LogOut className="size-4" aria-hidden />}
        />
      </div>
    )
  }
  return (
    <Button variant="secondary" onClick={openLogin} icon={<KeyRound className="size-4" aria-hidden />} className={compact ? 'px-3' : ''}>
      <span className={compact ? 'sr-only' : ''}>Acceso de presentador</span>
    </Button>
  )
}

/** Fuente de los datos visibles: Excel del ejercicio (evaluado, con selector de lote) o RSS reales (pitch). */
export function ScopeBar() {
  const { contextId, batchId, setBatchId, batches } = useApp()
  if (contextId === 'rss') {
    return (
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-line bg-lavender/60 px-3 py-1.5 text-xs text-ink-2 sm:px-5">
        <Rss className="size-3.5 text-accent" aria-hidden />
        <span><strong className="text-ink">Fuente: RSS reales</strong> · demostración (pitch), no forma parte de la evaluación · exposición potencial de cartera simulada</span>
      </div>
    )
  }
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line bg-lavender/60 px-3 py-1.5 text-xs text-ink-2 sm:px-5">
      <span className="flex items-center gap-1.5">
        <FileSpreadsheet className="size-3.5 text-accent" aria-hidden />
        <strong className="text-ink">Fuente evaluada: Excel del ejercicio</strong>
      </span>
      <label htmlFor="batch-scope" className="flex items-center gap-1.5">
        Lote
        <select
          id="batch-scope"
          value={batchId}
          onChange={(e) => setBatchId(e.target.value)}
          className="min-h-9 max-w-[16rem] rounded-lg border border-line bg-surface px-2 text-sm font-semibold text-ink"
        >
          <option value="">Todos los lotes</option>
          {batches.map((b) => (
            <option key={b.id} value={b.id}>
              {SPLIT_LABEL[b.split] ?? b.split} · {b.completed}/{b.row_count} analizadas
            </option>
          ))}
        </select>
      </label>
      {!batchId && batches.filter((b) => b.completed > 0).length > 1 && (
        <span className="text-review">Mostrando varios lotes juntos; elige uno para ver sus resultados por separado.</span>
      )}
    </div>
  )
}

function GlobalSearch() {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault()
        navigate(`/proveedores?q=${encodeURIComponent(q)}`)
      }}
      className="relative hidden min-w-0 flex-1 md:block md:max-w-xs"
    >
      <label htmlFor="global-search" className="sr-only">
        Buscar proveedor
      </label>
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-2" aria-hidden />
      <input
        id="global-search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Buscar proveedor, ciudad, material…"
        className="min-h-11 w-full rounded-[10px] border border-line bg-surface pl-9 pr-3 text-sm"
      />
    </form>
  )
}

function AlertToast() {
  const { toast, dismissToast, state } = useAlarm()
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!toast) return
    const t = window.setTimeout(dismissToast, 12000)
    return () => window.clearTimeout(t)
  }, [toast, dismissToast])
  if (!toast) return null
  const urgent = toast.alerts.filter((a) => a.urgent === 'Y').length
  return (
    <div ref={ref} role="status" aria-live="assertive" className="card fixed bottom-20 left-3 right-3 z-30 flex items-start gap-3 border-urgent/30 p-3 fade-in md:bottom-6 md:left-auto md:right-6 md:w-96">
      <BellRing className="mt-0.5 size-5 shrink-0 text-urgent" aria-hidden />
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-semibold">
          {toast.alerts.length === 1 ? 'Nueva alerta' : `${toast.alerts.length} alertas nuevas`}
          {urgent > 0 && ` · ${urgent} urgente${urgent > 1 ? 's' : ''}`}
        </p>
        <p className="truncate text-ink-2">{toast.alerts.map((a) => a.supplier_name).join(', ')}</p>
        <p className="text-xs text-ink-2">
          {toast.sounded ? 'Aviso sonoro emitido.' : state === 'armed' ? 'Sin sonido: no elegible o en cooldown.' : 'Sin sonido: activa el sonido para recibir avisos.'}
        </p>
        <Link to="/alertas" onClick={dismissToast} className="mt-1 inline-block text-sm font-semibold text-accent-strong underline">
          Ver alertas
        </Link>
      </div>
      <button onClick={dismissToast} className="rounded-md p-2 text-ink-2 hover:bg-lavender" aria-label="Cerrar aviso">
        <X className="size-4" aria-hidden />
      </button>
    </div>
  )
}

function MobileMore({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { presenter } = useApp()
  const items = [
    { to: '/proveedores', label: 'Proveedores', icon: Building2 },
    { to: '/fuentes', label: 'Fuentes RSS', icon: Rss },
    ...(presenter ? [{ to: '/presentador', label: 'Panel de presentador', icon: Settings2 }] : []),
  ]
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/40" />
        <Dialog.Content className="fixed inset-x-0 bottom-0 z-50 rounded-t-2xl bg-surface p-4 pb-8 shadow-xl fade-in">
          <div className="mb-3 flex items-center justify-between">
            <Dialog.Title className="text-base font-semibold">Más</Dialog.Title>
            <Dialog.Close className="rounded-md p-2 hover:bg-lavender" aria-label="Cerrar">
              <X className="size-5" aria-hidden />
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">Otras secciones y ajustes</Dialog.Description>
          <nav className="flex flex-col gap-1" aria-label="Más secciones">
            {items.map((i) => (
              <NavLink key={i.to} to={i.to} onClick={() => onOpenChange(false)} className="flex min-h-12 items-center gap-3 rounded-xl px-3 text-base font-medium hover:bg-lavender">
                <i.icon className="size-5 text-accent" aria-hidden /> {i.label}
              </NavLink>
            ))}
          </nav>
          <div className="mt-4 flex flex-col gap-3 border-t border-line pt-4">
            <SoundControl />
            <PresenterButton />
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export function Shell({ children }: { children: ReactNode }) {
  const { unread } = useAlarm()
  const { meta } = useApp()
  const [moreOpen, setMoreOpen] = useState(false)
  const loc = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [loc.pathname])
  return (
    <div className="min-h-dvh">
      <a href="#main" className="skip-link">
        Saltar al contenido
      </a>
      {/* Sidebar escritorio */}
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-60 flex-col border-r border-line bg-surface lg:flex">
        <div className="gradient-bar h-1" aria-hidden />
        <div className="px-4 py-4">
          <Logo />
        </div>
        <nav aria-label="Principal" className="flex flex-col gap-1 px-3">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                clsx('flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm font-semibold', isActive ? 'bg-lavender text-accent-strong' : 'text-ink-2 hover:bg-bg hover:text-ink')
              }
            >
              <n.icon className="size-4" aria-hidden />
              {n.label}
              {n.to === '/alertas' && unread > 0 && <span className="tabular ml-auto rounded-full bg-urgent px-2 text-xs text-white">{unread}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto space-y-2 p-4 text-xs text-ink-2">
          <EngineLine />
          <p>Cartera simulada: proveedores ficticios.</p>
        </div>
      </aside>

      <div className="lg:pl-60">
        <header className="sticky top-0 z-10 border-b border-line bg-surface/95 backdrop-blur">
          <div className="gradient-bar h-1 lg:hidden" aria-hidden />
          <div className="flex items-center gap-2 px-3 py-2 sm:px-5">
            <div className="lg:hidden">
              <Logo compact />
            </div>
            <ContextSwitch className="min-w-0" />
            <GlobalSearch />
            <div className="ml-auto flex items-center gap-1.5">
              <div className="hidden sm:block">
                <SoundControl compact />
              </div>
              <div className="hidden md:block">
                <PresenterButton compact />
              </div>
            </div>
          </div>
          <ScopeBar />
          <MobileSoundStrip />
        </header>
        <main id="main" className="mx-auto w-full max-w-[1400px] px-3 pb-28 pt-4 sm:px-5 lg:pb-10">
          {meta && meta.engine.mode === 'fixture' && (
            <div className="mb-3 rounded-xl border border-review/30 bg-review-bg px-4 py-2 text-sm font-semibold text-review">
              Modo fixture · Demostración de interfaz: los análisis no proceden de JEV y no son exportables.
            </div>
          )}
          {children}
        </main>
      </div>

      {/* Navegación inferior móvil */}
      <nav aria-label="Principal móvil" className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-4 border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden">
        {[
          { to: '/', label: 'Resumen', icon: LayoutDashboard, end: true },
          { to: '/noticias', label: 'Noticias', icon: Newspaper },
          { to: '/alertas', label: 'Alertas', icon: Bell },
        ].map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.end}
            className={({ isActive }) => clsx('relative flex min-h-14 flex-col items-center justify-center gap-0.5 text-xs font-semibold', isActive ? 'text-accent-strong' : 'text-ink-2')}
          >
            <n.icon className="size-5" aria-hidden />
            {n.label}
            {n.to === '/alertas' && unread > 0 && (
              <span className="tabular absolute right-[22%] top-1.5 rounded-full bg-urgent px-1.5 text-[10px] text-white" aria-label={`${unread} sin leer`}>
                {unread}
              </span>
            )}
          </NavLink>
        ))}
        <button onClick={() => setMoreOpen(true)} className="flex min-h-14 flex-col items-center justify-center gap-0.5 text-xs font-semibold text-ink-2" aria-haspopup="dialog">
          <Menu className="size-5" aria-hidden />
          Más
        </button>
      </nav>
      <MobileMore open={moreOpen} onOpenChange={setMoreOpen} />
      <LoginDialog />
      <AlertToast />
    </div>
  )
}

function MobileSoundStrip() {
  const { state } = useAlarm()
  if (state !== 'off' && state !== 'blocked') return null
  return (
    <div className="flex items-center justify-between gap-2 border-t border-line bg-lavender px-3 py-1.5 sm:hidden">
      <span className="flex items-center gap-1.5 text-xs text-ink-2">
        <Radio className="size-3.5" aria-hidden />
        {state === 'blocked' ? 'Audio bloqueado por el navegador' : 'Sonido desactivado'}
      </span>
      <SoundControl />
    </div>
  )
}

function EngineLine() {
  const { meta } = useApp()
  if (!meta) return null
  const label = meta.engine.mode === 'jev' ? `Motor JEV · ${meta.engine.model}` : meta.engine.mode === 'fixture' ? 'Modo fixture (sin JEV)' : 'Motor sin configurar'
  return (
    <p className="flex items-center gap-1.5">
      <span className={clsx('size-2 rounded-full', meta.engine.mode === 'jev' ? 'bg-ok' : 'bg-review')} aria-hidden />
      {label}
      {!meta.worker.alive && <span className="text-review"> · worker sin señal</span>}
    </p>
  )
}
