// Cliente HTTP del mismo origen. El token CSRF solo existe en memoria tras iniciar sesión de presentador.
let csrfToken: string | null = null

export function setCsrf(token: string | null) {
  csrfToken = token
}

export class ApiError extends Error {
  status: number
  code: string
  details: unknown
  retryable: boolean
  constructor(status: number, code: string, message: string, details: unknown, retryable: boolean) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
    this.retryable = retryable
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  let payload: BodyInit | undefined
  if (body instanceof FormData) {
    payload = body
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  if (method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken
  let res: Response
  try {
    res = await fetch(path, { method, headers, body: payload, credentials: 'same-origin' })
  } catch {
    throw new ApiError(0, 'network_error', 'Sin conexión con el servidor.', null, true)
  }
  if (!res.ok) {
    let data: { code?: string; message?: string; details?: unknown; retryable?: boolean } = {}
    try {
      data = await res.json()
    } catch {
      /* cuerpo no JSON */
    }
    throw new ApiError(res.status, data.code ?? `http_${res.status}`, data.message ?? `Error HTTP ${res.status}`, data.details, !!data.retryable)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body ?? {}),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body ?? {}),
  del: <T>(path: string) => request<T>('DELETE', path),
}

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export async function downloadExport(batchId: string): Promise<string> {
  const res = await fetch(`/api/batches/${batchId}/export.xlsx`, { credentials: 'same-origin' })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.code ?? 'export_error', data.message ?? 'No se pudo exportar.', data.details, false)
  }
  const blob = await res.blob()
  const name = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') ?? '')?.[1] ?? 'resultados.xlsx'
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
  return name
}

export function downloadText(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}
