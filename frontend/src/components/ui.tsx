import clsx from 'clsx'
import { AlertCircle, AlertTriangle, CheckCircle2, CircleDashed, Info, Loader2, RefreshCw, ShieldAlert } from 'lucide-react'
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { ApiError } from '../lib/api'
import { BAND_LABEL, fmtNum } from '../lib/format'
import type { Band, YN } from '../lib/types'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; busy?: boolean; icon?: ReactNode }>(
  function Button({ variant = 'secondary', busy, icon, className, children, disabled, onClick, ...rest }, ref) {
    // Mientras está ocupado no se deshabilita el elemento: así conserva el foco y los diálogos lo devuelven al cerrar.
    return (
      <button
        ref={ref}
        className={clsx(
          'inline-flex min-h-11 items-center justify-center gap-2 rounded-[10px] px-4 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-55',
          variant === 'primary' && 'bg-accent text-white shadow-sm hover:bg-accent-strong',
          variant === 'secondary' && 'border border-line bg-surface text-ink hover:bg-lavender',
          variant === 'ghost' && 'text-ink-2 hover:bg-lavender hover:text-ink',
          variant === 'danger' && 'border border-urgent/30 bg-urgent-bg text-urgent hover:bg-urgent/10',
          className,
        )}
        disabled={disabled}
        aria-disabled={busy || undefined}
        aria-busy={busy || undefined}
        onClick={busy ? (e) => e.preventDefault() : onClick}
        {...rest}
      >
        {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
        {children}
      </button>
    )
  },
)

export function Card({ className, children, as: As = 'section', ...rest }: { className?: string; children: ReactNode; as?: 'section' | 'div' | 'article'; 'aria-labelledby'?: string }) {
  return (
    <As className={clsx('card', className)} {...rest}>
      {children}
    </As>
  )
}

export function CardHeader({ title, id, action, subtitle }: { title: ReactNode; id?: string; action?: ReactNode; subtitle?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-2 border-b border-line px-4 py-3 sm:px-5">
      <div className="min-w-0">
        <h2 id={id} className="text-base font-semibold text-ink">
          {title}
        </h2>
        {subtitle && <p className="text-sm text-ink-2">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

type Tone = 'urgent' | 'review' | 'info' | 'ok' | 'neutral' | 'accent'
const toneClass: Record<Tone, string> = {
  urgent: 'bg-urgent-bg text-urgent border-urgent/25',
  review: 'bg-review-bg text-review border-review/25',
  info: 'bg-info-bg text-info border-info/25',
  ok: 'bg-ok-bg text-ok border-ok/25',
  neutral: 'bg-bg text-ink-2 border-line',
  accent: 'bg-lavender text-accent-strong border-accent/25',
}

export function Badge({ tone = 'neutral', icon, children, className, title }: { tone?: Tone; icon?: ReactNode; children: ReactNode; className?: string; title?: string }) {
  return (
    <span title={title} className={clsx('inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-semibold', toneClass[tone], className)}>
      {icon}
      {children}
    </span>
  )
}

export function UrgencyBadge({ urgent, isRisk = 'Y' }: { urgent: YN | null | undefined; isRisk?: YN | null }) {
  if (urgent === 'Y') return <Badge tone="urgent" icon={<ShieldAlert className="size-3.5" aria-hidden />}>Urgente</Badge>
  if (isRisk === 'Y') return <Badge tone="info" icon={<Info className="size-3.5" aria-hidden />}>No urgente</Badge>
  return null
}

const bandTone: Record<Band, string> = {
  critical: 'bg-urgent text-white',
  high: 'bg-[#d92d20]/12 text-urgent',
  medium: 'bg-review-bg text-review',
  low: 'bg-bg text-ink-2',
}

export function PriorityBadge({ value, band, pending, size = 'md' }: { value: number | null | undefined; band?: Band | null; pending?: boolean; size?: 'md' | 'lg' }) {
  if (pending || value === null || value === undefined) {
    return (
      <span className={clsx('inline-flex items-center gap-1 rounded-lg border border-review/30 bg-review-bg px-2 py-1 font-semibold text-review', size === 'lg' ? 'text-base' : 'text-xs')}>
        <CircleDashed className="size-3.5" aria-hidden /> Pendiente
      </span>
    )
  }
  const b: Band = band ?? (value >= 80 ? 'critical' : value >= 65 ? 'high' : value >= 35 ? 'medium' : 'low')
  return (
    <span
      className={clsx('tabular inline-flex items-baseline gap-1 rounded-lg px-2 py-1 font-bold', bandTone[b], size === 'lg' ? 'text-2xl' : 'text-sm')}
      aria-label={`Prioridad ${fmtNum(value)} de 100, banda ${BAND_LABEL[b]}`}
    >
      {fmtNum(value)}
      <span className={clsx('font-medium opacity-80', size === 'lg' ? 'text-sm' : 'text-[11px]')}>/100 · {BAND_LABEL[b]}</span>
    </span>
  )
}

export function ReviewBadge({ title }: { title?: string }) {
  return (
    <Badge tone="review" title={title} icon={<AlertTriangle className="size-3.5" aria-hidden />}>
      Requiere revisión
    </Badge>
  )
}

export function Loading({ label = 'Cargando…' }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 p-6 text-sm text-ink-2">
      <Loader2 className="size-4 animate-spin" aria-hidden /> {label}
    </div>
  )
}

export function EmptyState({ title, children, icon, action }: { title: string; children?: ReactNode; icon?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-10 text-center">
      <div className="text-accent">{icon ?? <CheckCircle2 className="size-8" aria-hidden />}</div>
      <p className="font-semibold text-ink">{title}</p>
      {children && <div className="max-w-md text-sm text-ink-2">{children}</div>}
      {action}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof ApiError ? error.message : 'No se pudo cargar la información.'
  return (
    <div role="alert" className="flex flex-col items-center gap-3 px-6 py-8 text-center">
      <AlertCircle className="size-7 text-urgent" aria-hidden />
      <p className="text-sm text-ink">{msg}</p>
      {onRetry && (
        <Button onClick={onRetry} icon={<RefreshCw className="size-4" aria-hidden />}>
          Reintentar
        </Button>
      )}
    </div>
  )
}

export function Notice({ tone = 'info', title, children, icon }: { tone?: Tone; title: ReactNode; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className={clsx('flex gap-3 rounded-xl border px-4 py-3 text-sm', toneClass[tone])} role={tone === 'urgent' ? 'alert' : 'status'}>
      <span className="mt-0.5 shrink-0">{icon ?? <Info className="size-4" aria-hidden />}</span>
      <div className="min-w-0">
        <p className="font-semibold">{title}</p>
        {children && <div className="mt-0.5 text-ink">{children}</div>}
      </div>
    </div>
  )
}

export function Kpi({ label, value, detail, tone, icon }: { label: string; value: ReactNode; detail: ReactNode; tone?: 'urgent' | 'default'; icon?: ReactNode }) {
  return (
    <div className="card flex flex-col gap-1 p-3 sm:p-4">
      <div className="flex items-center justify-between gap-2 text-xs font-semibold uppercase tracking-wide text-ink-2">
        <span>{label}</span>
        {icon}
      </div>
      <div className={clsx('tabular text-2xl font-bold sm:text-3xl', tone === 'urgent' ? 'text-urgent' : 'text-ink')}>{value}</div>
      <div className="text-xs text-ink-2">{detail}</div>
    </div>
  )
}

export function ProbBar({ label, value, threshold }: { label: string; value: number | null | undefined; threshold?: number }) {
  const v = value ?? 0
  return (
    <div className="text-xs">
      <div className="flex justify-between text-ink-2">
        <span>{label}</span>
        <span className="tabular font-semibold text-ink">{value === null || value === undefined ? '—' : fmtNum(v * 100, 0) + ' %'}</span>
      </div>
      <div className="relative mt-1 h-1.5 rounded-full bg-line" aria-hidden>
        <div className="h-1.5 rounded-full bg-accent" style={{ width: `${Math.min(100, v * 100)}%` }} />
        {threshold !== undefined && <div className="absolute -top-0.5 h-2.5 w-0.5 bg-ink" style={{ left: `${threshold * 100}%` }} />}
      </div>
    </div>
  )
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-ink-2">{label}</dt>
      <dd className="text-sm font-semibold text-ink">{children}</dd>
      {hint && <dd className="text-xs text-ink-2">{hint}</dd>}
    </div>
  )
}

export function Select({ label, value, onChange, options, id }: { label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; id: string }) {
  return (
    <label htmlFor={id} className="flex min-w-0 flex-col gap-1 text-xs font-medium text-ink-2">
      {label}
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="min-h-11 rounded-[10px] border border-line bg-surface px-3 text-sm text-ink"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  )
}
