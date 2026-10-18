import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, setCsrf } from './api'
import type { ContextId, Meta, SessionInfo } from './types'

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
      session: session.data,
      presenter: !!session.data?.presenter,
      meta: meta.data,
      refreshSession,
      loginOpen,
      openLogin: () => setLoginOpen(true),
      closeLogin: () => setLoginOpen(false),
    }),
    [contextId, setContextId, session.data, meta.data, refreshSession, loginOpen],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useApp(): AppState {
  const v = useContext(Ctx)
  if (!v) throw new Error('AppStateProvider ausente')
  return v
}
