# Motor de riesgo y prioridad

## Qué representa cada resultado

El riesgo responde si hay una amenaza para el suministro de Helixa. La urgencia responde si procurement debe atenderla ahora según gravedad, proximidad y dependencia. La prioridad 0–100 ordena los casos. La confianza describe incertidumbre en la decisión. Ninguno es un porcentaje de probabilidad de quiebra del proveedor.

Calcular por evento y proveedor. Una noticia puede afectar a varios proveedores con diferentes buffers. El ranking de un proveedor toma el máximo score de sus incidentes activos, no la suma de titulares. Mostrar también el número de incidentes distintos. Una noticia positiva identificada conserva supplier_id, Is_Risk=N y Urgent=N.

## Fórmula versionada

La fuente numérica única es `config/risk_policy.json`. `reference/scoring.py` es su implementación de referencia. No introducir ponderaciones adicionales en la UI ni multiplicar por dos otra vez single source.

Para cada factor disponible x con peso w:

`E = sum(w * x) / sum(w disponibles)`

`P = round_half_up(100 * S * (0.50 + 0.50 * E), 1)`

Si la pareja no es riesgo, P=0. Si el evento se resolvió, su prioridad activa es 0 y conserva el score histórico. El resultado siempre permanece en [0,100]. Una llamada fallida deja P=null y estado error; nunca P=0.

| Factor | Peso | Valor normalizado |
| --- | ---: | --- |
| C criticidad | 0.35 | High=1.00, Medium=0.60, Low=0.30. |
| U fuente única | 0.30 | Y=1.00, N=0.00. Es el único efecto de Single_Source. |
| B presión del buffer | 0.25 | Definida abajo, de 0 a 1. |
| G concentración de gasto en categoría | 0.10 | Share_of_Category_Spend_% / 100, dentro de 0–1. |

S es la severidad de impacto sobre ese proveedor dividida por 10. JEV usa diez niveles de Score indexados 0–9; el adaptador convierte a severidad 1–10 con `severity = 1 + native_score`. No redondear a entero antes del cálculo. El score nativo puede ser fraccional. Si no hay riesgo, la puerta determinista fuerza prioridad cero con independencia de la severidad estimada.

## Buffer y datos ausentes

Si hay inventario físico y lead time positivo:

`B_lead = clip((lead_time_days - inventory_cover_days) / lead_time_days, 0, 1)`

Si existe una duración de interrupción expresamente identificada D>0:

`B_event = clip((D - inventory_cover_days) / D, 0, 1)`

Usar el máximo de los términos disponibles. No sumar dos veces la presión. D procede de una frase identificada y normalizada; una duración mínima es un límite inferior, no una predicción de recuperación. Mostrar esa distinción. Indefinido no se transforma en 365 días. Sin D, se utiliza solo B_lead si está disponible.

Esta comparación es un indicador de cobertura, no una proyección de inventario: no hay pedidos en tránsito ni capacidad libre del alternativo en los datos. No escribir Fecha de rotura de stock a partir de ella.

Para Logistics y Services, el inventario del dataset no aplica: omitir B y normalizar por los pesos aplicables. Para un material físico con inventario ausente, omitir B, marcar `inventory_missing` y dejar el análisis en revisión. No convertir null a 0 días ni al peor factor. El warning debe decir qué falta, no una advertencia genérica. Un inventario de 0 días es un dato válido y debe dar presión máxima cuando exista lead o duración.

Si ningún factor contextual está disponible, no se calcula P y el caso pasa a revisión. Valores negativos, porcentajes fuera de [0,100], categorías desconocidas o NaN producen diagnóstico de datos. El código no repara silenciosamente datos inválidos.

## Clasificación y confianza

| Regla | Valor inicial |
| --- | ---: |
| Incluir un proveedor identificado | p_link >= 0.50 |
| Is_Risk=Y para pareja identificada | p_risk >= 0.50 |
| Urgent=Y para pareja con riesgo | p_urgent >= 0.50 |
| Zona de ambigüedad de Noul | 0.35 <= p <= 0.65 |
| Confianza mínima de Choice o Score | 0.60 |
| Probabilidades mínimas para sonido automático | p_link, p_risk y p_urgent >= 0.80 |

Las probabilidades Noul no son el campo confidence de Choice/Score. Conservar ambos sin sustituirlos. El promedio de niveles de Score no es una probabilidad. Un confidence bajo dirige a revisión; no multiplica la prioridad por 0.2 ni esconde una señal grave.

Estos son parámetros iniciales de ingeniería, pendientes de calibración con desarrollo. No prometer rendimiento por el marketing del proveedor. Ajustar en entrenamiento; usar validación como comprobación retenida. Si se usa validación repetidamente para elegir versiones, registrar que deja de ser una prueba independiente. Test y LiveDay nunca se usan para elegir umbrales.

## Agregación de artículo y exportación

- Affected_Supplier_IDs incluye todos los proveedores identificados aceptados, también los de noticias positivas.
- Is_Risk=Y si alguna pareja tiene riesgo. Urgent=Y si alguna pareja con riesgo es urgente.
- Is_Risk=N implica Urgent=N. Affected_Supplier_IDs puede no estar vacío.
- Ordenar IDs únicos y unir con `; `. Conservar orden y News_ID del archivo. Sin proveedores aceptados, ambos flags son N y los IDs quedan vacíos, aunque un caso ambiguo siga visible en revisión.
- Un resultado de baja confianza ya procesado puede exportar su mejor decisión binaria, registrando la revisión pendiente en el informe de ejecución. Un resultado con error de proveedor o campos sin procesar bloquea la exportación final hasta reintento o resolución manual explícita.

## Bandas y alarma

| Prioridad | Etiqueta |
| --- | --- |
| 0–34.9 | Baja |
| 35–64.9 | Media |
| 65–79.9 | Alta |
| 80–100 | Crítica |

La banda es de prioridad, no una regla automática que cambie Urgent. Una prioridad crítica con Urgent=N crea una tarea de revisión por discrepancia. Un Urgent=Y de alta confianza crea alerta sonora aunque su score sea inferior a 80. Se mantiene así la distinción entre presión operativa y petición de atención inmediata.

Emitir sonido únicamente si el evento está activo, Is_Risk=Y, Urgent=Y, todas las probabilidades anteriores superan el mínimo, no hay revisión obligatoria y el usuario activó audio. Cada nueva revisión de alerta suena una vez por pestaña, con cooldown global de 30 segundos. Agrupar varias alertas próximas en un único aviso; no perder sus tarjetas. Reconocer una alerta no resuelve el evento.

## Evolución temporal

Conservar fecha del artículo, fecha de evento cuando esté disponible, fecha de análisis y versión. Una noticia de recuperación solo reduce el estado actual si está asociada al mismo incidente y es posterior; no borra otro incidente del proveedor. Una noticia antigua recibida tarde no reabre un evento más reciente resuelto. Ambigüedad de vinculación o temporalidad crea revisión. Caducar por antigüedad no equivale a resolver: mostrar Requiere actualización después de siete días sin evidencia y mantener el historial.

## Evaluación

Publicar matrices de confusión y precisión/recobrado/F1 para riesgo y urgencia. Para proveedores, evaluar coincidencia exacta del conjunto y precision/recall por ID; incluir no-riesgos con proveedor. No evaluar todo con un único accuracy. Hay 30 noticias de entrenamiento, 10 de validación y solo siete urgentes etiquetadas entre ambas. Presentar los denominadores y no afirmar validez general para una operación real.
