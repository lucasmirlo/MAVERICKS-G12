# Prompt de auditoría final

Revisa y corrige la aplicación construida contra este kit. Trabaja sobre la implementación existente y resuelve los fallos observados. No te limites a describir recomendaciones. No cambies umbrales ni preguntas para mejorar resultados de test o LiveDay.

1. Lee docs/07_ACEPTACION_Y_DEMO.md y registra A01–A20 como pasa, falla o no ejecutado, con evidencia concreta y fecha.
2. Revisa importación, IDs, nulos, aislamiento de etiquetas y exportación. Inspecciona el payload efectivo de JEV con un test; no expongas claves en logs. Asegura que todos los 40 proveedores son candidatos.
3. Compara el score de casos sintéticos con reference/scoring.py. Comprueba fuente única una sola vez, confidence separado, inventario ausente distinto de cero, score nulo ante fallo y prioridad por máximo de incidentes activos.
4. Prueba multi-supplier, positivo, homónimo, noticia regional, recuperación y evento antiguo recibido tarde. No conviertas cada titular en un incidente nuevo ni cierres todos los incidentes del proveedor por una recuperación.
5. Consulta RSS real desde el entorno final y registra hora/HTTP/contador. Verifica 304, duplicado y edición. No cambies a fixtures silenciosamente. No declares en vivo un análisis cacheado.
6. Comprueba permisos de presentador en cada mutación, secretos ausentes del frontend, HTML sanitizado y destinos RSS limitados. La lectura pública debe funcionar sin registro.
7. Comprueba el audio con gesto real, mute y repetición. Revisa la visualización cuando el navegador bloquea sonido. El ensayo auditivo debe indicar dispositivo/navegador; Playwright solo valida la lógica de reproducción.
8. Ejecuta las pruebas y el build de contenedor. Reinicia worker y web para verificar leases y persistencia. Comprueba /readyz, rutas profundas y exportación en URL pública.
9. Revisa 360, 390, 768 y 1440 px, sin overflow de viewport. Comprueba que filtros, ficha y borrador tienen acciones visibles, foco y lectura clara.
10. Mide el lote final autorizado desde clic de procesar hasta exportación disponible. Incluye fallos/reintentos en el tiempo total. Nunca rellenes salidas a mano ni inventes métricas.

Entrega un resumen con URL real si existe, versión/commit, pruebas ejecutadas y resultados, fuentes operativas, tiempo medido, métricas de validación con denominadores y limitaciones pendientes. Si no se pudo desplegar, incluye los comandos y accesos que faltan. No uses Listo como estado global si quedan criterios bloqueantes sin ejecutar.
