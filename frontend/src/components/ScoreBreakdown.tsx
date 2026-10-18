import { FACTOR_LABEL, fmtDays, fmtNum, fmtPct, reviewLabel } from '../lib/format'
import type { SupplierDetail } from '../lib/types'

export function ScoreBreakdown({ b }: { b: NonNullable<SupplierDetail['breakdown']> }) {
  const keys = (['C', 'U', 'B', 'G'] as const).filter((k) => k in b.weights)
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p className="rounded-lg bg-lavender p-3 text-xs leading-relaxed text-ink">
        P = 100 × S × ({fmtNum(b.severity_floor, 2)} + {fmtNum(b.exposure_weight, 2)} × E) = 100 × {fmtNum((b.severity ?? 0) / 10, 2)} × ({fmtNum(b.severity_floor, 2)} + {fmtNum(b.exposure_weight, 2)} ×{' '}
        {fmtNum(b.exposure, 3)}) = <strong className="tabular">{fmtNum(b.priority)}</strong>. E es la media ponderada de los factores disponibles; los ausentes se omiten y se renormaliza. Política {b.policy_version}.
      </p>
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Factores de exposición</caption>
        <thead className="text-xs text-ink-2">
          <tr>
            <th scope="col" className="py-1 font-semibold">Factor</th>
            <th scope="col" className="py-1 text-right font-semibold">Peso</th>
            <th scope="col" className="py-1 text-right font-semibold">Valor</th>
            <th scope="col" className="py-1 text-right font-semibold">Aporte a E</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => {
            const present = b.factors[k] !== undefined
            return (
              <tr key={k} className="border-t border-line/70">
                <td className="py-1.5">{FACTOR_LABEL[k]}</td>
                <td className="tabular py-1.5 text-right">{fmtNum(b.weights[k], 2)}</td>
                <td className="tabular py-1.5 text-right">{present ? fmtNum(b.factors[k]!, 2) : <span className="text-ink-2">omitido</span>}</td>
                <td className="py-1.5 text-right">
                  {present ? (
                    <span className="inline-flex items-center justify-end gap-2">
                      <span className="hidden h-1.5 w-16 rounded-full bg-line sm:inline-block" aria-hidden>
                        <span className="block h-1.5 rounded-full bg-accent" style={{ width: `${(b.contributions[k] ?? 0) * 100}%` }} />
                      </span>
                      <span className="tabular">{fmtPct(b.contributions[k], 0)}</span>
                    </span>
                  ) : (
                    '—'
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="text-xs text-ink-2">
        Severidad del evento {fmtNum(b.severity)}/10 (no vuelve a contar criticidad ni fuente única).
        {b.duration_days != null && <> Duración explícita en la fuente: {b.duration_is_lower_bound ? 'al menos ' : ''}{fmtDays(b.duration_days)}{b.duration_is_lower_bound ? ' (límite inferior, no predicción de recuperación)' : ''}.</>}
        {' '}El buffer compara cobertura con lead time/duración; no es una proyección de inventario ni una fecha de rotura.
      </p>
      {b.review_reasons.length > 0 && <p className="text-xs text-review">Revisión: {b.review_reasons.map(reviewLabel).join('; ')}.</p>}
    </div>
  )
}
