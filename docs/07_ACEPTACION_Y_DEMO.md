# Aceptación y demostración

## Criterios que bloquean la entrega

| ID | Prueba | Resultado esperado |
| --- | --- | --- |
| A01 | Importar catálogo | 40 proveedores, 20 materiales, seis productos; los 40 entran en matching. |
| A02 | Importar los cuatro esquemas | Reconoce News, News_Validation, News_Test y News_Feed sin edición manual. |
| A03 | Payload de JEV | No contiene las cinco columnas de etiquetas de la fila analizada ni datos del answer key. |
| A04 | Nombre parecido | No atribuye automáticamente un incidente de una organización homónima al proveedor. |
| A05 | Noticia positiva | Mantiene proveedor identificado con riesgo N y urgencia N. |
| A06 | Evento regional | Admite varios proveedores y restringe la exposición al alcance material/geográfico. |
| A07 | Varios incidentes | Agrupa duplicados sin sumar scores; un incidente distinto sigue independiente. |
| A08 | Recuperación | Actualización posterior resuelve el incidente compatible y conserva su historial. |
| A09 | Inventario | Nulo de servicio no se transforma en cero; físico desconocido genera revisión; cero real es válido. |
| A10 | Score | Acotado 0–100, sin doble single source, independiente de confidence, coherente con referencia. |
| A11 | RSS real | Al menos cuatro de las seis fuentes devuelven contenido desde Railway en el ensayo; las seis están configuradas y las caídas visibles. |
| A12 | RSS repetido/actualizado | Mismo contenido no duplica análisis ni alerta; contenido nuevo con mismo GUID crea versión. |
| A13 | Fallo de IA | 401 diagnosticado; 429 reintentado de forma acotada; no se generan falsos N. |
| A14 | Audio | Primer clic activa; probar suena; nueva alerta elegible suena una vez; mute funciona; no hay sonido al abrir historial. |
| A15 | Borradores | Consulta y consulta a alternativo editables, copiables, descargables; no se envían ni inventan stock/contactos. |
| A16 | Exportación | Una fila por entrada, IDs exactos, Y/N y delimitador correcto; no se mezclan RSS ni fixtures. |
| A17 | Persistencia | Tras redeploy continúan resultados, incidentes, cursor RSS y trabajos recuperables. |
| A18 | Acceso público | URL HTTPS funciona sin registro; mutaciones denegadas sin sesión; secretos ausentes del bundle frontend. |
| A19 | Responsive | 360/390/768/1440 px utilizables; sin overflow de viewport; filtros y modal con teclado. |
| A20 | Tiempo LiveDay | 14 artículos y exportación final completados en <=300 s en Railway, medidos en el ensayo. |

Si A11 falla por un proveedor externo, conservar el error real y usar las otras fuentes verificadas. Reponer una fuente antes de la demo si quedan menos de cuatro. Nunca usar datos ficticios para afirmar que una conexión real funcionó. Los fixtures solo prueban el comportamiento de la app y están etiquetados.

## Pruebas automáticas solicitadas a Codex

Unitarias: normalización de hojas, parseo de fechas/unidades, conservación de IDs, fórmula, umbrales, referencias, deduplicación y estado de evento. Usar `reference/test_scoring.py` como mínimo de invariantes, no como única prueba.

Integración: HTTP JEV simulado con respuestas reales de forma, errores 401/429/529, feeds RSS/Atom con 304, repetición, edición y XML inválido; cola con dos reclamadores; recuperación de lease; exportación completa. Un test explícito asegura que la etapa B procesa múltiples proveedores en una sola solicitud.

E2E: acceso de presentador, upload, progreso, proveedor, filtros, borrador, alerta, mute y exportación. Playwright puede comprobar estados y llamada a reproducción, pero la audibilidad requiere ensayo manual de dispositivo. Un test de navegador no prueba que el teléfono emita sonido.

Evaluación de IA: desarrollar con training, congelar versión y medir validation. Calcular precision/recall/F1 de riesgo y urgencia y exactitud de conjunto de proveedores. Test y LiveDay son ejecución final. Guardar resultados separados de la app pública; no poner etiquetas de evaluación en fixtures de producción.

## Guion de cinco minutos

Antes de empezar: abrir URL en escritorio y móvil; verificar motor configurado, worker activo, cuatro o más fuentes saludables; entrar como presentador; Activar sonido y Probar alarma. No depender del bloqueo de pantalla ni del volumen por defecto del teléfono.

| Tiempo orientativo | Acción |
| --- | --- |
| 0:00–0:30 | Mostrar URL pública en móvil y seleccionar contexto del ejercicio. |
| 0:30–1:00 | Cargar el feed LiveDay sin editarlo; iniciar proceso y mostrar progreso. |
| 1:00–2:00 | Mientras procesa, abrir Fuentes, pulsar Actualizar ahora y mostrar RSS real con hora y enlace. |
| 2:00–3:15 | Abrir una alerta obtenida por el sistema, escuchar el aviso si es elegible y explicar sus factores. |
| 3:15–4:15 | Abrir proveedor/productos/alternativo y generar un borrador desde evidencia. |
| 4:15–5:00 | Exportar resultados y mostrar que todas las filas están completas. |

El orden puede adaptarse a la latencia medida. No elegir ni escribir de antemano las respuestas de test/LiveDay para construir una demo que aparente inferencia. Si falla un proveedor, mostrar el fallo y el reintento; los resultados previos llevan fecha y estado cacheado.

## Entrega final de Codex

Informar commit o versión, URL, servicios desplegados, variables necesarias por nombre, comandos de operación, fuentes realmente consultadas desde Railway, tiempo medido del lote, métricas de validation con denominadores, dispositivos revisados y pruebas pendientes. No declarar Listo para producción regulada por haber completado una demo.
