# Supplier Risk Radar · Helixa Pharmaceuticals

Aplicación web para leer noticias, reconocer la exposición de la cartera de proveedores (ficticia) de Helixa y decidir qué casos debe revisar procurement. Importa los Excel del reto, ingiere seis RSS reales, clasifica con **JEV de TypeSafe**, calcula una prioridad 0–100 explicable y muestra alertas con sonido dentro de la pestaña, borradores editables y la exportación del reto.

> El kit de especificación original está en `00_LEEME.md`, `docs/`, `config/`, `contracts/` y `reference/`. Este README describe la aplicación construida.

## Arquitectura

| Componente | Qué hace | Código |
| --- | --- | --- |
| Web (FastAPI + React compilado) | API `/api/*`, sesión de presentador, cargas, consultas, exportación; sirve el frontend bajo el mismo origen | `app/main.py`, `app/api/`, `frontend/` |
| Worker (`python -m app.worker`) | Reclama trabajos de la cola PostgreSQL (`FOR UPDATE SKIP LOCKED`, lease 90 s, heartbeat 20 s, reintentos con backoff), llama a JEV (máx. 4 simultáneas), recalcula incidentes y sondea RSS cada 300 s con lease por fuente | `app/worker.py`, `app/jobqueue.py`, `app/rss.py` |
| PostgreSQL | Catálogo, lotes, artículos y versiones, caché JEV, análisis, evaluaciones por proveedor, incidentes, alertas, borradores, trabajos, etiquetas de evaluación (tabla separada) | `app/models.py`, `alembic/` |
| JEV (TypeSafe) | `POST https://api.typesafe.ai/v1/systemone`, Bearer `TYPESAFE_API_KEY`, modelo fijado `jev-1.13.0` | `app/jev/` |

Flujo de un artículo (`app/pipeline.py`):

1. **Etapa A**: un `noul` por cada uno de los 40 proveedores (vínculo por identidad o exposición operativa; no hay filtro de palabras clave previo) + `choice` de tipo y estado del evento.
2. **Etapa B** (una sola petición por artículo): para cada candidato con p_link ≥ 0,35 → `noul` riesgo y urgencia, `score` de severidad (10 niveles, severidad = 1 + score), `choice` de estado de impacto, de frase de evidencia (fragmentos literales con offsets) y de duración (candidatos extraídos del texto o `unknown`).
3. **Política** (`app/scoring.py`, idéntica a `reference/scoring.py` y parametrizada por `config/risk_policy.json` versión 1.0.0): umbrales, revisión, prioridad P = round_half_up(100·S·(0,5 + 0,5·E), 1), banda y elegibilidad sonora.
4. **Incidentes** (`app/incidents.py`): reconstrucción determinista y cronológica por contexto; agrupa actualizaciones del mismo evento (mismo proveedor y tipo, ventana de 14 días) sin sumar scores; una recuperación solo resuelve un incidente compatible anterior (si hay varios, revisión); un artículo antiguo recibido tarde no reabre; resolución manual registrada. Una alerta por revisión del incidente.

Las respuestas de JEV se validan estrictamente (claves, tipos, rangos, opciones); una respuesta inválida o un error HTTP deja el análisis en `error` con flags `null`, **nunca** en N, y bloquea la exportación final hasta reintento o decisión manual explícita.

### Contextos

- **Ejercicio**: los cuatro Excel. Reloj lógico = fecha máxima de publicación analizada (o la que fije el presentador).
- **Noticias reales**: RSS con fuente y fecha originales. Todo vínculo se muestra como *Exposición potencial de cartera simulada*.
- El modo fixture (`DEMO_FIXTURES_ENABLED=true` y sin clave) etiqueta todo como «Modo fixture · Demostración de interfaz» y sus resultados no son exportables.

## Puesta en marcha local

Requisitos comprobados: Python 3.13, Node 24, PostgreSQL 16+ (probado con 18).

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt      # Linux/macOS: .venv/bin/python
cp .env.example .env                                              # rellena DATABASE_URL, ADMIN_PASSWORD, SESSION_SECRET y TYPESAFE_API_KEY
.venv/Scripts/python -m alembic upgrade head
cd frontend && npm ci && npm run build && cd .. && rm -rf static && cp -r frontend/dist static
```

Ejecutar (dos procesos):

```bash
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

```bash
.venv/Scripts/python -m app.worker
```

Desarrollo del frontend con recarga: `cd frontend && npm run dev` (proxy de `/api` a `:8000`).

### Pruebas

```bash
.venv/Scripts/python -m pytest -q
```

Usa la base `TEST_DATABASE_URL` (por defecto `postgresql+psycopg://srr@localhost:5433/srr_test`), que se **borra y migra** al empezar. Cubren: política frente a la referencia (rejilla completa), constructor de peticiones y ausencia de etiquetas en el cuerpo HTTP real enviado, cliente JEV (401 sin reintentos, 429/529 acotados, validación), pipeline (positiva conserva proveedor con N/N, homónimo, evento regional multi-proveedor con una sola etapa B, inventario ausente/no aplicable/cero, error → bloqueo de exportación, caché), incidentes (duplicados, eventos distintos, recuperación, llegada tardía, recuperación procesada antes, alertas estables, revisión bloquea sonido, resolución manual), cola (dos reclamadores, lease vencida, prioridad, backoff), RSS (nuevo, 304, duplicado, edición con mismo GUID, XML inválido, entidades, caída aislada, antigüedad, cupo, SSRF), importación de los cuatro esquemas y rechazos, API (permisos, CSRF, límite de intentos, sin etiquetas en respuestas públicas, exportación bloqueada, borradores).

Comprobación de una URL: `python scripts/smoke_test.py <url>`. Medición de un lote de extremo a extremo: `ADMIN_PASSWORD=... python scripts/measure_batch.py <url> inputs/supplier_liveday.xlsx`.

## Uso (presentador)

1. Pulsa **Acceso de presentador** y entra con `ADMIN_PASSWORD`.
2. **Presentador → Importar Excel**: sube un `.xlsx` o importa una entrada del manifiesto (`evidence/input_manifest.json`; la app nunca recorre carpetas ni busca `*.xlsx`). `supplier_training.xlsx` crea el catálogo (40 proveedores, 20 materiales, 6 productos) y el lote de entrenamiento. La importación es idempotente por hash.
3. **Analizar lote**: encola un trabajo por fila (prioridad sobre RSS). El progreso, el tiempo transcurrido y la latencia p50/p95 (con n) se actualizan cada 3 s.
4. **Exportar XLSX**: hoja `Resultados` (News_ID, Is_Risk, Urgent, Affected_Supplier_IDs con IDs únicos ordenados unidos por `; `), copia de la hoja original con las columnas de entrada y las respuestas, y hoja `Informe` (modelo, política, revisiones pendientes, decisiones manuales, caché). Bloqueada (HTTP 409) si hay filas pendientes, con error o de fixture.
5. **Fuentes → Actualizar ahora** encola la sincronización real de las seis fuentes.
6. **Activar sonido** (cada carga de página necesita el gesto), **Probar alarma**, **Silenciar**. Una revisión de alerta elegible suena una vez por pestaña, con cooldown de 30 s y agrupación; el historial no suena al abrir.
7. En la ficha de proveedor: **Borrador de consulta al proveedor** / **Consultar alternativo** (editable, copiar, descargar TXT; nunca se envía; destinatario pendiente).
8. **Evaluar contra etiquetas** (solo lotes con etiquetas: entrenamiento y validación).

Test y LiveDay son ejecución final: no se procesan automáticamente; el botón del lote los ejecuta sin cambiar código. **Reiniciar análisis del lote** borra resultados, alertas derivadas y la caché JEV de ese lote (no las filas importadas) para repetir un ensayo en directo; úsalo con LiveDay antes de la demo.

Preguntas JEV: versión `1.2.0` (`app/jev/questions.py`), ajustada solo con entrenamiento; contexto geográfico inferido en `config/location_enrichment.json` (estado `inferred`, con procedencia). Un vínculo solo inferido por región o ruta se marca `inferred_region` y no habilita sonido automático.

## Variables de entorno

Ver `.env.example`. Imprescindibles en Railway: `DATABASE_URL`, `TYPESAFE_API_KEY`, `JEV_MODEL`, `ADMIN_PASSWORD`, `SESSION_SECRET`, `APP_BASE_URL` (https). Ninguna clave se expone al frontend (no hay variables `VITE_*`).

## Despliegue en Railway

Despliegue actual: **https://web-production-03417.up.railway.app** (proyecto `supplier-risk-radar`). Estado y mediciones en `ESTADO_ENTREGA.md`.

Archivos: `Dockerfile` (multietapa, usuario sin privilegios, frontend compilado en la imagen), `railway.web.json`, `railway.worker.json` (referencia), `.dockerignore`, `.railwayignore`.

> Railway rechaza ya *config-as-code* (`railway.json`) en cuentas nuevas. Los valores de `railway.web.json` / `railway.worker.json` se aplican como ajustes del servicio (en el panel o con `railway api` → `serviceInstanceUpdate`: `dockerfilePath`, `preDeployCommand`, `startCommand`, `healthcheckPath`, `healthcheckTimeout`, `restartPolicyType`, `sleepApplication=false`).

1. `railway login`, `railway init --name supplier-risk-radar`, `railway add --database postgres`, `railway add --service web`, `railway add --service worker`.
2. Sube el código desde esta carpeta: `railway up --service web --ci` y `railway up --service worker --ci` (respeta `.gitignore`: no sube `.env`, `.venv`, `node_modules`).
3. Servicio **web**: Dockerfile, pre-deploy `alembic upgrade head`, start `uvicorn … --port $PORT --proxy-headers`, healthcheck `/readyz`. Secretos con `railway variable set NOMBRE --stdin --service web` para no dejarlos en la línea de comandos.
4. Variables del web: `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `TYPESAFE_API_KEY`, `JEV_MODEL=jev-1.13.0`, `ADMIN_PASSWORD`, `SESSION_SECRET` (aleatorio largo), `APP_BASE_URL=https://<dominio>`.
5. *Networking → Generate domain*. Actualiza `APP_BASE_URL` con ese dominio (activa cookies `Secure` y HSTS).
6. Servicio **worker** desde el mismo repo: config file `railway.worker.json` (start `python -m app.worker`, sin dominio, sin suspensión). Mismas variables salvo `APP_BASE_URL` (opcional). El worker espera a que el esquema esté en `head`; no migra.
7. Comprueba `https://<dominio>/readyz`, entra como presentador, **Probar conexión** del motor, importa `supplier_training.xlsx`, pulsa **Actualizar ahora** en Fuentes.
8. `python scripts/smoke_test.py https://<dominio>` y un ensayo con `scripts/measure_batch.py`.
9. Redeploy de ambos servicios y verifica que resultados, incidentes, ETag RSS y trabajos persisten.

### Operación y recuperación

- `/healthz` (vivo) y `/readyz` (BD + migración en head). Un fallo de JEV o de un RSS no tumba la web: se muestra en Fuentes/Motor.
- Logs: `job=… kind=… attempt=… duration_ms=…`, `jev call status=… attempt=…`, `rss source=… result=…`. La cabecera Authorization y patrones de secreto se redactan.
- Un reinicio del worker recupera trabajos con lease vencida; sin intentos restantes pasan a `failed` y se reintentan con **Reintentar errores** del lote. Los análisis que fallaron solo por falta de clave se reencolan solos al configurarla.
- Caché JEV por hash de petición (texto, catálogo, modelo, versión de preguntas): repetir un análisis no vuelve a llamar al proveedor y se marca «Resultado en caché».
- Cupo RSS: 100 análisis por día UTC; el excedente queda en espera visible, no se declara irrelevante.

## Seguridad

Lectura pública; mutaciones con cookie de sesión firmada `HttpOnly`, `SameSite=Lax` y `Secure` en https, token CSRF por cabecera y límite de 5 intentos de login cada 5 min por IP. Evaluaciones solo para presentador. CSP restrictiva sin recursos de terceros (Inter autoalojada). RSS: solo http(s), sin credenciales en URL, hosts que resuelven a direcciones públicas en cada redirect (máx. 3), 4 MB, 10 s, rechazo de XML con entidades, HTML saneado a texto. Celdas exportadas siempre como texto.

## Evaluación

`python -m app.evaluation --batch <id>` o el botón del panel. Guarda el JSON en `evaluation/runs/` (fuera de la app pública) y en `evaluation_runs`. Publica matrices de confusión, precisión, recobrado y F1 de riesgo y urgencia, coincidencia exacta del conjunto de proveedores y precisión/recobrado por ID, con denominadores. 30 noticias de entrenamiento y 10 de validación (7 urgentes entre ambas): muestra pequeña, sin validez general.

## Limitaciones y pendientes

Ver `ESTADO_ENTREGA.md` para el estado A01–A20 con evidencias, tiempos medidos y lo que queda por probar.
