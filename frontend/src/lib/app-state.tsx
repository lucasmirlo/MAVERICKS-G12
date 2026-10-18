import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, setCsrf } from './api'
import type { BatchProgress, ContextId, Meta, SessionInfo } from './types'

export const POLL_MS = 3000

function readPref(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
function writePref(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* almacenamiento no disponible */
  }
}

interface AppState {
  contextId: ContextId
  setContextId: (c: ContextId) => void
  /** Lote Excel seleccionado en Ejercicio ('' = todos). Siempre '' en Noticias reales. */
  batchId: string
  setBatchId: (b: string) => void
  batches: BatchProgress[]
  /** Parámetros comunes para la API según contexto y lote. */
  scope: { context_id: ContextId; batch_id?: string }
  session: SessionInfo | undefined
  presenter: boolean
  meta: Meta | undefined
  refreshSession: () => Promise<void>
  loginOpen: boolean
  openLogin: () => void
  closeLogin: () => void
}

const Ctx = createContext<AppState | null>(null)

export function AppStateProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [contextId, setCtx] = useState<ContextId>(() => (readPref('srr.context') === 'rss' ? 'rss' : 'exercise'))
  const [loginOpen, setLoginOpen] = useState(false)
  const [storedBatch, setStoredBatch] = useState<string>(() => readPref('srr.batch') ?? '')
  const batchesQ = useQuery({
    queryKey: ['batches', 'exercise'],
    queryFn: () => api.get<{ items: (BatchProgress & { kind: string })[] }>('/api/batches?context_id=exercise'),
    refetchInterval: POLL_MS,
  })
  const batches = useMemo(() => {
    const order = ['training', 'validation', 'test', 'liveday', 'other']
    return (batchesQ.data?.items ?? []).filter((b) => b.kind === 'news').sort((x, y) => order.indexOf(x.split) - order.indexOf(y.split))
  }, [batchesQ.data])
  // Un lote borrado o inexistente vuelve a «todos».
  const batchId = contextId === 'exercise' && batches.some((b) => b.id === storedBatch) ? storedBatch : ''
  const setBatchId = useCallback((b: string) => {
    setStoredBatch(b)
    writePref('srr.batch', b)
  }, [])
  const session = useQuery({ queryKey: ['session'], queryFn: () => api.get<SessionInfo>('/api/session'), staleTime: 60_000 })
  const meta = useQuery({ queryKey: ['meta'], queryFn: () => api.get<Meta>('/api/meta'), refetchInterval: 15_000 })

  useEffect(() => {
    setCsrf(session.data?.csrf ?? null)
  }, [session.data])

  const setContextId = useCallback((c: ContextId) => {
    setCtx(c)
    writePref('srr.context', c)
  }, [])

  const refreshSession = useCallback(async () => {
    await qc.invalidateQueries({ queryKey: ['session'] })
    await qc.invalidateQueries({ queryKey: ['meta'] })
  }, [qc])

  const value = useMemo<AppState>(
    () => ({
      contextId,
      setContextId,
      batchId,
      setBatchId,
      batches,
      scope: batchId ? { context_id: contextId, batch_id: batchId } : { context_id: contextId },
      session: session.data,
      presenter: !!session.data?.presenter,
      meta: meta.data,
      refreshSession,
      loginOpen,
      openLogin: () => setLoginOpen(true),
      closeLogin: () => setLoginOpen(false),
    }),
    [contextId, setContextId, batchId, setBatchId, batches, session.data, meta.data, refreshSession, loginOpen],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useApp(): AppState {
  const v = useContext(Ctx)
  if (!v) throw new Error('AppStateProvider ausente')
  return v
}
