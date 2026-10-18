# Especificación de producto y arquitectura

## Propósito y alcance

Helixa quiere leer noticias, reconocer su exposición de suministro y decidir qué casos deben revisar sus compradores. La entrega es una aplicación de demo pública en Railway que usa los datos del ejercicio y RSS reales. El visitante debe entender una alerta, llegar a su evidencia y preparar una consulta al proveedor desde el móvil.

Requisitos obligatorios: carga Excel, ingesta RSS real, JEV real configurable, score trazable, dashboard, ficha por proveedor, relación con productos, alertas audibles en navegador, borradores locales, analítica de ingestión y exportación del reto. Idioma de interfaz: español. Fechas almacenadas en UTC y mostradas en Europe/Madrid.

La fuente de suministro de referencia tiene 40 proveedores y 20 materiales conectados con seis productos. Son ficticios. Hay 14 proveedores single source, siete de criticidad alta, y 10 materiales sin alternativo aprobado. Materials representa 30 proveedores; todos los 40 siguen participando en la evaluación. Para los otros diez, mostrar Productos no mapeados, nunca cero productos como certeza de ausencia.

## Entradas y aislamiento de datos

| Entrada del kit | Hojas a leer | Uso |
| --- | --- | --- |
| `inputs/supplier_training.xlsx` | Suppliers, Materials, News | Catálogo y 30 noticias de desarrollo con etiquetas. |
| `inputs/supplier_validation.xlsx` | News_Validation | 10 noticias para evaluación retenida. |
| `inputs/supplier_test.xlsx` | News_Test | 20 noticias sin etiquetas; conservar las columnas originales al exportar sobre una copia. |
| `inputs/supplier_liveday.xlsx` | News_Feed | 14 noticias del 6 de octubre de 2026; ejecución independiente para demo. |
| RSS | Configuración de seis feeds | Monitorización externa actual, contexto separado. |

El README de entrenamiento menciona News_Train, pero la hoja real se llama News. Las rutas se toman del manifiesto explícito. La aplicación nunca busca archivos por el patrón global *.xlsx ni importa el answer key.

Permitir xlsx; rechazar ficheros corruptos, formatos con macros y hojas sin columnas mínimas con mensajes concretos. Límite inicial: 10 MB por archivo y 5.000 filas, configurable. Un import crea un batch y devuelve su ID. No ejecutar fórmulas del archivo. Limpiar texto peligroso al generar CSV y escribir texto como texto en XLSX.

Los campos de etiqueta se almacenan en una tabla de evaluación separada, accesible solo al presentador. El trabajador de inferencia recibe exclusivamente datos de entrada. Construir un test que compruebe esta separación en el payload real enviado al proveedor. No copiar Explanation a las explicaciones de producción.

## Contextos y fechas

Ejercicio usa el reloj lógico del lote: su fecha máxima de publicación o una fecha elegida explícitamente por el presentador. RSS usa la hora real. No descartar los artículos del ejercicio por ser anteriores a la fecha del ordenador. Test y LiveDay no se procesan ni se puntúan automáticamente durante el desarrollo. El botón de ejecución final carga el lote completo sin cambiar el código.

La cartera ficticia puede demostrar exposición geográfica a noticias reales. La interfaz debe decir Cartera simulada y Exposición potencial cuando corresponda. Una coincidencia regional no prueba que una instalación específica haya parado. No inventar proveedores reales para hacer encajar un titular. Mostrar también noticias analizadas sin vínculo con la cartera.

## Arquitectura de ejecución

| Componente | Responsabilidad | Persistencia |
| --- | --- | --- |
| Web React y FastAPI | Navegación, API, cargas, consultas, sesión y exportaciones | PostgreSQL |
| Worker Python | Obtener RSS, reclamar trabajos, llamar a JEV, calcular score, actualizar incidentes | PostgreSQL |
| PostgreSQL | Catálogo, artículos, versiones de análisis, cola, eventos, alertas y borradores | Volumen del servicio de base de datos |
| JEV oficial | Clasificación y evaluación estructurada | El worker guarda la respuesta y la versión |
| Generador opcional | Redactar una explicación o borrador desde hechos ya validados | Resultado cacheado con hash de evidencias |

El web y el worker comparten imagen Docker y se inician con comandos distintos. Un worker persistente ejecuta también el sondeo de RSS cada 300 segundos; una lease de base de datos impide que dos workers sincronicen la misma fuente simultáneamente. No se necesita Redis para este volumen. La app debe admitir añadirlo posteriormente sin cambiar los contratos de negocio.

Los trabajos se reclaman con transacciones y `FOR UPDATE SKIP LOCKED`. Cada job tiene lease, heartbeat, intentos, próximo intento y error. Recuperar leases vencidas al reiniciar. Deduplicación y escrituras idempotentes impiden reprocesar la misma versión. En el worker, limitar a cuatro solicitudes JEV simultáneas y dar prioridad a un batch manual frente a RSS atrasados. No mantener una petición HTTP abierta durante todo un lote.

La interfaz consulta progreso y nuevas alertas cada tres segundos mientras está visible. Al recuperar foco, consulta inmediatamente. Es una decisión deliberada para simplificar el despliegue inicial; no afirmar recepción instantánea ni entrega cuando el dispositivo está suspendido.

## Modelo de datos mínimo

| Entidad | Campos esenciales e invariantes |
| --- | --- |
| Supplier | supplier_id único; nombre; país; ciudad; categoría; material; spend; share_category_pct; single_source; alternate_id; lead_days; cover_days; criticality; quality_score. |
| Material y MaterialSupplier | IDs primario/alternativo; productos como lista normalizada; cantidad y unidad separadas. |
| Source | feed_id, URL, estado, ETag, Last-Modified, last_success_at, error, intervalo, enabled. |
| ImportBatch | id, context_id, split, fecha lógica, hash de archivo, orden de filas, progreso. |
| Article y ArticleVersion | UUID interno; external_id; source_id; URL; titular; resumen; published_at; fetched_at; content_hash; version. |
| Analysis | article_version_id, model_id, prompt_version, policy_version, estado, payload_hash, duración, decisiones y referencias. |
| SupplierAssessment | Una relación por análisis y proveedor, probabilidades, severidad, riesgo, urgencia, score y razones. |
| Incident | context_id, proveedor, tipo, lugar, active/monitoring/resolved, historia de cambios y evidencias. |
| Alert | incident_id, revision, unread/acknowledged, priority, created_at; unicidad por incidente y revisión. |
| Draft | tipo consulta/alternativo, supplier_id, incident_id, texto editable, factual_context_hash. |
| Job | tipo, payload, estado, attempts, lease_until, next_attempt_at, error_code. |
| EvaluationLabel | batch_id y news_id; etiquetas originales separadas del pipeline. |

En artículos RSS, una edición del texto conserva article_id y crea una versión; un GUID puede conservarse con contenido nuevo. No desechar una actualización solo porque la URL ya existe. Deduplicar versiones iguales por hash. Agrupar publicaciones diferentes que describan el mismo evento conservando sus fuentes; no fusionar automáticamente dos incendios distintos en una misma ciudad.

## API interna

| Método y ruta | Contrato de comportamiento |
| --- | --- |
| GET /healthz | Liveness sin pedir respuestas a proveedores externos. |
| GET /readyz | Comprueba conexión y versión de esquema de PostgreSQL. |
| POST /api/session | Verifica secreto de presentador y emite cookie de sesión. |
| DELETE /api/session | Cierra sesión. |
| GET /api/overview?context_id= | KPIs, prioridad actual, fuentes y última actualización. |
| GET /api/suppliers | Filtros, búsqueda y paginación; orden estable. |
| GET /api/suppliers/{id} | Ficha, alternativos, materiales, productos, incidentes y noticias. |
| GET /api/articles | Filtros por origen, rango de fecha, relevancia, evento y estado. |
| GET /api/articles/{id} | Evidencia fuente y análisis por proveedor. |
| POST /api/imports | Multipart xlsx, kind y context_id; devuelve batch_id y diagnóstico. |
| POST /api/batches/{id}/analyze | Encola análisis idempotente y devuelve job_id, HTTP 202. |
| GET /api/jobs/{id} | Progreso, filas pendientes y errores, sin secretos. |
| GET /api/batches/{id}/export.xlsx | Fichero listo si no hay filas con error sin resolver; si no, 409 con diagnóstico. |
| POST /api/sources/sync | Encola sincronización manual, HTTP 202. |
| GET /api/sources | Salud de los feeds y resumen del último sondeo. |
| GET /api/alerts?after= | Cursor estable para nuevas revisiones y contador. |
| POST /api/alerts/{id}/ack | Reconoce alerta sin cerrar el incidente. |
| POST /api/incidents/{id}/resolve | Resolución manual motivada y registrada. |
| POST /api/drafts | Crea borrador desde evidencia; soporta plantilla sin generador. |
| PATCH /api/drafts/{id} | Guarda cambios del presentador. |
| POST /api/evaluations/{batch_id} | Calcula métricas contra etiquetas disponibles, nunca contra test sin respuestas. |

Todas las mutaciones y la exportación de etiquetas de evaluación requieren sesión de presentador. La consulta de resultados de demo es pública. Responder a errores con `{code, message, details, retryable}` y mensajes de interfaz claros. No devolver traces, tokens ni cabeceras de autorización.

## Flujo de usuario

El presentador carga el Excel, revisa el reconocimiento de hojas y comienza el lote. La web muestra contadores y resultados conforme se completan. Al terminar puede exportar, filtrar por urgencia y abrir un proveedor. En su ficha ve noticias, productos y alternativo; un botón crea el borrador. El monitor RSS recibe noticias independientemente y muestra la hora de consulta y la fuente real.

Un visitante puede ver las pantallas y activar sonido local. Las acciones de edición muestran Acceso de presentador si no existe sesión. No hay registro de usuarios ni integración de correo para la demo.

## Analítica con denominadores explícitos

Medir recibidas, duplicadas, pendientes, procesadas, con error, vinculadas, riesgo y urgentes. Relevante significa que existe vínculo con al menos un proveedor, aunque sea noticia positiva. Contar proveedores únicos por separado de artículos. Nunca presentar fallos como irrelevantes. Incluir distribución de prioridad por contexto y fuente, latencia p50/p95 y fecha del último éxito. Una ejecución no basta para sostener un p95 estable: mostrar el tamaño de la muestra.

## Alcance de la entrega de Codex

Código ejecutable, migraciones, lockfiles, imagen reproducible, .env.example, fixtures identificados, pruebas, capturas de revisión móvil/escritorio, informe de evaluación y README. Las seis fuentes deben estar conectadas y sus fallos gestionados. Incluir URL pública y resultado del smoke test si las credenciales de Railway están disponibles; de lo contrario, dejar el despliegue preparado e identificar el único acceso que falta.
