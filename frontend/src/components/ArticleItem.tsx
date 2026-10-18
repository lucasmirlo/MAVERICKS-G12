import { AlertTriangle, CheckCircle2, CircleDashed, Hourglass, Link2, ShieldAlert, ThumbsUp, Unlink, XCircle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ERROR_LABEL, EVENT_LABEL, RELEVANCE_LABEL, fmtPub } from '../lib/format'
import type { ArticleBrief, Relevance } from '../lib/types'
import { Badge } from './ui'

const REL_TONE: Record<Relevance, { tone: 'urgent' | 'review' | 'info' | 'ok' | 'neutral' | 'accent'; icon: typeof ShieldAlert }> = {
  urgent: { tone: 'urgent', icon: ShieldAlert },
  risk: { tone: 'review', icon: AlertTriangle },
  positive: { tone: 'ok', icon: ThumbsUp },
  recovery: { tone: 'ok', icon: CheckCircle2 },
  linked: { tone: 'info', icon: Link2 },
  unlinked: { tone: 'neutral', icon: Unlink },
  pending: { tone: 'neutral', icon: CircleDashed },
  deferred: { tone: 'review', icon: Hourglass },
  error: { tone: 'urgent', icon: XCircle },
}

export function RelevanceBadge({ relevance }: { relevance: Relevance }) {
  const { tone, icon: Icon } = REL_TONE[relevance]
  return (
    <Badge tone={tone} icon={<Icon className="size-3.5" aria-hidden />}>
      {RELEVANCE_LABEL[relevance]}
    </Badge>
  )
}

export function ArticleItem({ a, compact }: { a: ArticleBrief; compact?: boolean }) {
  return (
    <li className="border-b border-line/70 last:border-0">
      <Link to={`/noticias/${a.id}`} className="block px-4 py-3 hover:bg-bg focus-visible:bg-bg sm:px-5">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-2">
          <span className="font-semibold text-ink">{a.source_name ?? 'Fuente desconocida'}</span>
          <span aria-hidden>·</span>
          <time dateTime={a.published_at ?? undefined}>{fmtPub(a.published_at ?? a.first_seen_at, a.context_id)}</time>
          {a.news_id && (
            <>
              <span aria-hidden>·</span>
              <span className="tabular">{a.news_id}</span>
            </>
          )}
          {a.cached && <Badge>Caché</Badge>}
          {a.engine_mode === 'fixture' && <Badge tone="review">Fixture</Badge>}
        </div>
        <p className={compact ? 'mt-1 line-clamp-2 text-sm font-semibold text-ink' : 'mt-1 font-semibold text-ink'}>{a.headline}</p>
        {!compact && a.summary && <p className="mt-0.5 line-clamp-2 text-sm text-ink-2">{a.summary}</p>}
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <RelevanceBadge relevance={a.relevance} />
          {a.needs_review && <Badge tone="review">Requiere revisión</Badge>}
          {a.event_type && a.event_type !== 'not_relevant' && <Badge tone="accent">{EVENT_LABEL[a.event_type] ?? a.event_type}</Badge>}
          {a.affected_supplier_ids.length > 0 && (
            <span className="text-xs text-ink-2">
              {a.context_id === 'rss' ? 'Exposición potencial: ' : 'Proveedores: '}
              <span className="tabular font-semibold text-ink">{a.affected_supplier_ids.join('; ')}</span>
            </span>
          )}
          {a.relevance === 'error' && a.error_code && <span className="text-xs text-urgent">{ERROR_LABEL[a.error_code] ?? a.error_code}</span>}
        </div>
      </Link>
    </li>
  )
}
