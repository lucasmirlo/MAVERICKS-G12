# Contratos de integración

`article_analysis.schema.json` define el resultado normalizado de un artículo. Es distinto de la respuesta de TypeSafe. Validar la respuesta externa primero y aplicar luego política y agregación. Guardar el JSON externo y su versión en backend; no publicarlo sin filtrar.

## Mapeo de TypeSafe

| Entrada externa | Campo interno | Regla |
| --- | --- | --- |
| answers.linked_ID.noul | p_link | Número finito 0–1; no convertir con bool(number). |
| answers.risk_ID.noul | p_risk | Número finito 0–1. |
| answers.urgent_ID.noul | p_urgent | Número finito 0–1; la puerta de riesgo fuerza N cuando corresponda. |
| answers.severity_ID.score | severity | 1 + score; diez niveles permiten rango 1–10. |
| answers.severity_ID.confidence | severity_confidence | Registrar; revisión si menor de 0.60. |
| answers.impact_state_ID.choice | impact_status | Debe existir en criterios. |
| answers.evidence_ID.choice | evidence_ids | Resolver ID a fragmento exacto; none no es una cita. |
| answers.duration_ID.choice | duration_days | Resolver candidato preextraído; unknown → null. |
| model | model_id | Registrar versión realmente usada. |
| usage | registro de uso | Persistir para observabilidad y coste. |

Comprobar que existen todas las respuestas pedidas, coinciden sus tipos y los valores son finitos. Para Choice/Score comprobar opciones, confidence y distribución válida. Una clave ausente, rango inválido o JSON incompleto es un error de análisis; no sustituirlo por cero. Rechazar una versión devuelta inesperada o dejarla en revisión con diagnóstico antes de publicar resultados de evaluación.

## Invariantes adicionales al JSON Schema

- supplier_id debe existir en la cartera y no repetirse dentro del artículo.
- affected_supplier_ids contiene el conjunto aceptado por p_link; assessments puede incluir candidatos ambiguos de revisión que no superen 0.50. Las agregaciones de riesgo/urgencia usan solo aceptados.
- Riesgo o urgencia agregados son OR de sus parejas elegibles. Un resultado de error nunca tiene flags Y/N definitivos.
- evidence_ids referencia elementos existentes de evidence; cada texto debe coincidir con el substring de headline o summary según sus offsets.
- Prioridad, factores y banda coinciden con la versión de política. No inferir prioridad desde confidence.
- priority=null necesita error o motivo de revisión; severity=null es válida para no-riesgo o análisis incompleto.
- impact_status resolved conserva la prioridad histórica en el incidente, mientras la prioridad activa es cero.
- Únicamente las parejas aceptadas, activas, urgentes y sin revisión pueden llegar a la puerta de audio.

Las fixtures son inventadas para demostrar contratos. `analysis_valid.json` no procede de una llamada a JEV ni resuelve una noticia del reto. Los cuerpos `jev_stage_a_request.json` y `jev_stage_b_request.json` son ejemplos para pruebas del adaptador.

Codex debe generar modelos Pydantic/TypeScript coherentes con este contrato, añadir validación de invariantes y pruebas de exportación. No usar los ejemplos como respuestas de producción.
