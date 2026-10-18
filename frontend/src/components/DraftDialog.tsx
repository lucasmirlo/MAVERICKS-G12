import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, Copy, Download, Save, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, ApiError, downloadText } from '../lib/api'
import { useApp } from '../lib/app-state'
import type { Draft } from '../lib/types'
import { Button } from './ui'

export function DraftDialog({ draft, onClose }: { draft: Draft | null; onClose: () => void }) {
  const { presenter } = useApp()
  const qc = useQueryClient()
  const [recipient, setRecipient] = useState('')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [copied, setCopied] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  useEffect(() => {
    if (draft) {
      setRecipient(draft.recipient ?? '')
      setSubject(draft.subject)
      setBody(draft.body)
      setMsg(draft.generator_error ?? null)
      setCopied(false)
    }
  }, [draft])
  const save = useMutation({
    mutationFn: () => api.patch<Draft>(`/api/drafts/${draft!.id}`, { subject, body, recipient }),
    onSuccess: () => {
      setMsg('Cambios guardados. Nada se ha enviado.')
      qc.invalidateQueries({ queryKey: ['supplier'] })
    },
    onError: (e) => setMsg(e instanceof ApiError ? e.message : 'No se pudo guardar.'),
  })
  const full = `Para: ${recipient || '(pendiente: no hay dirección en los datos)'}\nAsunto: ${subject}\n\n${body}\n`
  async function copy() {
    try {
      await navigator.clipboard.writeText(full)
      setCopied(true)
      setMsg('Copiado al portapapeles. No se ha enviado nada.')
    } catch {
      setMsg('El navegador no permitió copiar; selecciona el texto manualmente.')
    }
  }
  return (
    <Dialog.Root open={!!draft} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/40" />
        <Dialog.Content className="fixed inset-0 z-50 flex flex-col bg-surface fade-in sm:inset-auto sm:left-1/2 sm:top-1/2 sm:max-h-[90dvh] sm:w-[min(94vw,720px)] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:shadow-xl">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <div>
              <Dialog.Title className="text-base font-semibold">{draft?.kind === 'alternate' ? 'Consulta al alternativo' : 'Consulta al proveedor'}</Dialog.Title>
              <Dialog.Description className="text-xs text-ink-2">Borrador editable. Se copia o descarga; la aplicación nunca lo envía.</Dialog.Description>
            </div>
            <Dialog.Close className="rounded-md p-2 hover:bg-lavender" aria-label="Cerrar borrador">
              <X className="size-5" aria-hidden />
            </Dialog.Close>
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
            {draft?.evidence_changed && <p className="rounded-lg bg-review-bg p-2 text-sm text-review">La evidencia ha cambiado desde que se creó este borrador. Revísalo antes de reutilizarlo.</p>}
            <label className="flex flex-col gap-1 text-sm font-medium">
              Destinatario
              <input value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder="Pendiente: no hay dirección en los datos" className="min-h-11 rounded-[10px] border border-line px-3 text-base sm:text-sm" />
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium">
              Asunto
              <input value={subject} onChange={(e) => setSubject(e.target.value)} className="min-h-11 rounded-[10px] border border-line px-3 text-base sm:text-sm" />
            </label>
            <label className="flex min-h-0 flex-1 flex-col gap-1 text-sm font-medium">
              Cuerpo
              <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={14} className="min-h-[16rem] flex-1 rounded-[10px] border border-line p-3 font-sans text-base leading-relaxed sm:text-sm" />
            </label>
            <p className="text-xs text-ink-2">
              Generado con: {draft?.generator === 'template' ? 'plantilla determinista' : draft?.generator}. Hash de hechos: {draft?.factual_context_hash.slice(0, 12)}. No incluye stock, capacidad ni contactos que no estén en los datos.
            </p>
            {msg && <p role="status" className="text-sm text-ink">{msg}</p>}
          </div>
          <div className="grid grid-cols-3 gap-2 border-t border-line p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
            <Button onClick={copy} icon={copied ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}>Copiar</Button>
            <Button onClick={() => downloadText(`borrador_${draft?.target_supplier_id ?? 'proveedor'}.txt`, full)} icon={<Download className="size-4" aria-hidden />}>Descargar TXT</Button>
            <Button variant="primary" disabled={!presenter} onClick={() => save.mutate()} busy={save.isPending} icon={<Save className="size-4" aria-hidden />} title={presenter ? undefined : 'Solo el presentador guarda cambios'}>
              Guardar
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
