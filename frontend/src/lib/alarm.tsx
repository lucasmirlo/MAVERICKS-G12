/*
 * Alarma dentro de la pestaña con Web Audio.
 * - El AudioContext se crea o reanuda dentro del clic «Activar sonido» (requisito de autoplay).
 * - Cada revisión de alerta elegible suena una vez por pestaña (sessionStorage) con cooldown global de 30 s;
 *   llegadas próximas se agrupan en un único aviso. El historial existente al abrir no suena.
 * - No se piden permisos de notificaciones del sistema.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import { POLL_MS, useApp } from './app-state'
import type { Alert, AlertsResponse } from './types'

export type AudioState = 'off' | 'armed' | 'blocked' | 'muted' | 'unsupported'

interface AlarmApi {
  state: AudioState
  enable: () => Promise<void>
  test: () => void
  setMuted: (m: boolean) => void
  unread: number
  unreadByContext: Record<string, number>
  toast: { id: number; alerts: Alert[]; sounded: boolean } | null
  dismissToast: () => void
  lastPlayedAt: number | null
}

const Ctx = createContext<AlarmApi | null>(null)
const NOTIFIED_KEY = 'srr.notified'
const CURSOR_KEY = 'srr.alertCursor'

declare global {
  interface Window {
    __srrAudioLog?: { at: number; kind: 'alarm' | 'test' | 'unlock'; alerts?: number }[]
    webkitAudioContext?: typeof AudioContext
  }
}

function ssGet(key: string): string | null {
  try {
    return sessionStorage.getItem(key)
  } catch {
    return null
  }
}
function ssSet(key: string, v: string) {
  try {
    sessionStorage.setItem(key, v)
  } catch {
    /* sin almacenamiento de sesión: se usa solo memoria */
  }
}

function log(kind: 'alarm' | 'test' | 'unlock', alerts?: number) {
  window.__srrAudioLog = window.__srrAudioLog ?? []
  window.__srrAudioLog.push({ at: Date.now(), kind, alerts })
}

function tone(ctx: AudioContext, freq: number, start: number, dur: number, peak: number) {
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.type = 'sine'
  osc.frequency.setValueAtTime(freq, start)
  gain.gain.setValueAtTime(0.0001, start)
  gain.gain.exponentialRampToValueAtTime(peak, start + 0.02)
  gain.gain.exponentialRampToValueAtTime(0.0001, start + dur)
  osc.connect(gain).connect(ctx.destination)
  osc.start(start)
  osc.stop(start + dur + 0.02)
}

export function AlarmProvider({ children }: { children: ReactNode }) {
  const { meta } = useApp()
  const cooldownMs = (meta?.audio.cooldown_seconds ?? 30) * 1000
  const ctxRef = useRef<AudioContext | null>(null)
  const [state, setState] = useState<AudioState>(() => (typeof window !== 'undefined' && !(window.AudioContext || window.webkitAudioContext) ? 'unsupported' : 'off'))
  const stateRef = useRef(state)
  stateRef.current = state
  const lastPlay = useRef<number | null>(null)
  const [lastPlayedAt, setLastPlayedAt] = useState<number | null>(null)
  const pendingTimer = useRef<number | null>(null)
  const cursor = useRef<number | null>(ssGet(CURSOR_KEY) ? Number(ssGet(CURSOR_KEY)) : null)
  const notified = useRef<Set<string>>(new Set(JSON.parse(ssGet(NOTIFIED_KEY) ?? '[]') as string[]))
  const [toast, setToast] = useState<AlarmApi['toast']>(null)

  const playAlarm = useCallback((count: number) => {
    const ctx = ctxRef.current
    if (!ctx || ctx.state !== 'running') {
      if (stateRef.current === 'armed') setState('blocked')
      return false
    }
    const t = ctx.currentTime + 0.02
    // Aproximadamente un segundo: tres pulsos alternos, volumen moderado.
    tone(ctx, 880, t, 0.28, 0.16)
    tone(ctx, 660, t + 0.34, 0.28, 0.16)
    tone(ctx, 880, t + 0.68, 0.32, 0.16)
    lastPlay.current = Date.now()
    setLastPlayedAt(lastPlay.current)
    log('alarm', count)
    return true
  }, [])

  const enable = useCallback(async () => {
    const AC = window.AudioContext || window.webkitAudioContext
    if (!AC) {
      setState('unsupported')
      return
    }
    try {
      if (!ctxRef.current) ctxRef.current = new AC()
      const ctx = ctxRef.current
      // Buffer silencioso en el mismo gesto: desbloquea Safari iOS.
      const buf = ctx.createBuffer(1, 1, 22050)
      const src = ctx.createBufferSource()
      src.buffer = buf
      src.connect(ctx.destination)
      src.start(0)
      await ctx.resume()
      log('unlock')
      setState(ctx.state === 'running' ? 'armed' : 'blocked')
    } catch (err) {
      console.warn('[audio] activación rechazada', err)
      setState('blocked')
    }
  }, [])

  const test = useCallback(() => {
    const ctx = ctxRef.current
    if (!ctx || ctx.state !== 'running') {
      setState(ctx ? 'blocked' : 'off')
      return
    }
    const t = ctx.currentTime + 0.02
    tone(ctx, 740, t, 0.22, 0.14)
    tone(ctx, 988, t + 0.24, 0.22, 0.14)
    log('test')
  }, [])

  const setMuted = useCallback((m: boolean) => {
    setState((s) => (m ? (s === 'armed' ? 'muted' : s) : s === 'muted' ? 'armed' : s))
  }, [])

  const alerts = useQuery({
    queryKey: ['alerts-feed'],
    queryFn: () => api.get<AlertsResponse>('/api/alerts?limit=50'),
    refetchInterval: POLL_MS,
    refetchOnWindowFocus: 'always',
  })

  useEffect(() => {
    const data = alerts.data
    if (!data) return
    if (cursor.current === null) {
      // Primera carga: el historial no suena.
      cursor.current = data.cursor
      ssSet(CURSOR_KEY, String(data.cursor))
      return
    }
    const fresh = data.items.filter((a) => a.seq > (cursor.current ?? 0))
    cursor.current = Math.max(cursor.current, data.cursor)
    ssSet(CURSOR_KEY, String(cursor.current))
    if (!fresh.length) return
    const eligible = fresh.filter((a) => a.sound_eligible && a.incident_status === 'active' && !notified.current.has(`${a.incident_id}:${a.revision}`))
    for (const a of fresh) notified.current.add(`${a.incident_id}:${a.revision}`)
    ssSet(NOTIFIED_KEY, JSON.stringify([...notified.current].slice(-500)))
    let sounded = false
    if (eligible.length && stateRef.current === 'armed') {
      const since = lastPlay.current === null ? Infinity : Date.now() - lastPlay.current
      if (since >= cooldownMs) {
        sounded = playAlarm(eligible.length)
      } else if (pendingTimer.current === null) {
        // Dentro del cooldown: un único aviso agrupado al terminar.
        pendingTimer.current = window.setTimeout(() => {
          pendingTimer.current = null
          if (stateRef.current === 'armed') playAlarm(eligible.length)
        }, cooldownMs - since)
      }
    }
    setToast({ id: Date.now(), alerts: fresh, sounded })
  }, [alerts.data, cooldownMs, playAlarm])

  useEffect(() => {
    const unread = alerts.data?.unread ?? 0
    document.title = unread > 0 ? `(${unread}) Supplier Risk Radar` : 'Supplier Risk Radar'
  }, [alerts.data?.unread])

  useEffect(() => () => {
    if (pendingTimer.current) window.clearTimeout(pendingTimer.current)
  }, [])

  const value = useMemo<AlarmApi>(
    () => ({
      state,
      enable,
      test,
      setMuted,
      unread: alerts.data?.unread ?? 0,
      unreadByContext: alerts.data?.unread_by_context ?? {},
      toast,
      dismissToast: () => setToast(null),
      lastPlayedAt,
    }),
    [state, enable, test, setMuted, alerts.data, toast, lastPlayedAt],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAlarm(): AlarmApi {
  const v = useContext(Ctx)
  if (!v) throw new Error('AlarmProvider ausente')
  return v
}
