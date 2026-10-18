# Estado de entrega · Supplier Risk Radar

Fecha de la auditoría: 18 de octubre de 2026 (UTC). Estado global: **demo desplegada y verificada con pendientes de dispositivo** (no es «listo para producción regulada»).

## Despliegue

| Elemento | Valor |
| --- | --- |
| URL pública | https://web-production-03417.up.railway.app |
| Proyecto Railway | `supplier-risk-radar` (entorno `production`) |
| Servicios | `web` (FastAPI + React, dominio HTTPS, pre-deploy `alembic upgrade head`, healthcheck `/readyz`), `worker` (`python -m app.worker`, sin dominio, sin suspensión), `Postgres` |
| Esquema | Alembic `0002` |
| Motor | TypeSafe JEV `jev-1.13.0` (modelo devuelto por la API: `jev-1.13.0`), preguntas `1.2.0`, política `1.0.0` |
| Variables (por nombre) | `DATABASE_URL` (referencia a Postgres), `TYPESAFE_API_KEY`, `JEV_MODEL`, `ADMIN_PASSWORD`, `SESSION_SECRET`, `APP_BASE_URL` (solo web), `APP_TIMEZONE`, `RSS_POLL_SECONDS`, `RSS_DAILY_ANALYSIS_BUDGET`, `DEMO_FIXTURES_ENABLED=false`, `EXPLANATION_PROVIDER=template` |
| Credenciales de presentador | En `.env.railway` (local, ignorado por git). No están en el código ni en el frontend. |
| Versión de código | Sin repositorio git: el código se subió con `railway up` desde esta carpeta. |

Nota: la cuenta Railway rechaza *config-as-code* (`railway.json`) por obsoleto; la misma configuración de `railway.web.json` / `railway.worker.json` se aplicó a cada servicio mediante la API (`serviceInstanceUpdate`). Los dos JSON se conservan como referencia.

## Tiempos medidos

| Medición | Entorno | Resultado |
| --- | --- | --- |
| LiveDay, 14 filas: clic de analizar → XLSX descargado | Railway, 10:46:33 UTC | **2,8 s** (p50 0,41 s, p95 0,46 s por artículo, n = 14, 0 en caché) |
| LiveDay repetido tras «Reiniciar análisis del lote» | Railway, 10:52:29 UTC | **2,7 s** (p50 0,30 s, p95 0,39 s, n = 14) |
| Entrenamiento, 30 filas | Local → JEV real | 8,4 s (p50 0,99 s, p95 1,18 s, n = 30) |
| Validación, 10 filas | Local → JEV real | 4,1 s (p50 1,06 s, p95 1,21 s, n = 10) |
| Prueba de conexión JEV | Railway | OK, 114 ms (local: 615 ms) |
| Sincronización manual de las 6 fuentes | Railway, 10:55:54 UTC | 2,3 s |

Muestras pequeñas: los percentiles no son estables. El límite del reto es 300 s.

## Evaluación (con denominadores)

Preguntas ajustadas **solo con entrenamiento** (versiones 1.0.0 → 1.1.0 → 1.2.0). Las métricas de entrenamiento son optimistas por ese motivo. La validación se ejecutó **una única vez** con la versión 1.2.0 congelada; sus fallos no se han inspeccionado para no contaminarla. Test y LiveDay no se han evaluado (no tienen etiquetas) ni usado para ajustar.

| Lote | Is_Risk | Urgent | Proveedores |
| --- | --- | --- | --- |
| Validación (n = 10, 5 riesgos y 2 urgentes etiquetados) | VP 4, FP 0, FN 1, VN 5 · P 1,00 · R 0,80 · F1 0,89 | VP 1, FP 1, FN 1, VN 7 · P 0,50 · R 0,50 · F1 0,50 | Conjunto exacto 10/10 · precisión y recobrado por ID 1,00 (10 IDs) |
| Entrenamiento (n = 30, usado para ajustar) | VP 13, FP 0, FN 1, VN 16 · P 1,00 · R 0,93 | VP 5, FP 0, FN 0, VN 25 | Conjunto exacto 28/30 · precisión por ID 0,73 (22/30) · recobrado 1,00 |

Informes JSON en `evaluation/runs/`. Validación con 10 noticias y 2 urgentes: no permite afirmar validez general. Proporción en revisión: 15/30 en entrenamiento, 6/10 en validación, 6/14 en LiveDay (sobre todo probabilidades en la zona 0,35–0,65 y confianza < 0,60 del estado de impacto, tal como fija la política).

## Criterios A01–A20

| ID | Estado | Evidencia |
| --- | --- | --- |
| A01 Catálogo | Pasa | 40 proveedores, 20 materiales, 6 productos (local y Railway); 10 proveedores con «Productos no mapeados»; los 40 en la etapa A (test que cuenta las preguntas del cuerpo HTTP real). |
| A02 Cuatro esquemas | Pasa | News, News_Validation, News_Test y News_Feed reconocidos sin edición (test y en Railway). |
| A03 Payload sin etiquetas | Pasa | `test_payload_sent_to_provider_has_no_labels` inspecciona el cuerpo HTTP enviado tras importar el Excel real. |
| A04 Homónimo | Pasa (contrato) | Test con p_link bajo: sin vínculo ni alarma. Con JEV real no se ha construido un caso homónimo específico. |
| A05 Noticia positiva | Pasa (contrato) | Test: proveedor conservado con N/N y prioridad 0. |
| A06 Evento regional | Pasa | Test multi-proveedor con una sola etapa B; con JEV real, entrenamiento N046 vincula Valencia y Barcelona. Vínculos solo inferidos por región no habilitan sonido (`link_basis`). |
| A07 Varios incidentes | Pasa | Tests de duplicados (máximo, no suma) y de evento distinto independiente. |
| A08 Recuperación | Pasa | Tests: resuelve solo el compatible, conserva historial; también si la recuperación se procesa antes. |
| A09 Inventario | Pasa | Tests: servicio sin B y sin revisión; físico ausente → revisión; cero → B = 1. |
| A10 Score | Pasa | Rejilla completa idéntica a `reference/scoring.py`; acotado; sin doble fuente única; independiente de confidence. |
| A11 RSS real | Pasa | Desde Railway (10:44 UTC) las 6 fuentes devolvieron contenido; luego 304 por ETag/Last-Modified. Caída aislada probada con test. |
| A12 RSS repetido/editado | Pasa | Tests: mismo contenido sin nuevo análisis, mismo GUID con texto nuevo → versión 2. 304 observado en producción. |
| A13 Fallo de IA | Pasa (tests) | 401 sin reintentos, 429/529 acotados, respuesta inválida → error (nunca N) y exportación bloqueada. No se han observado errores reales del proveedor. |
| A14 Audio | Lógica pasa | Navegador del panel (Chromium) en producción: el clic desbloquea; el historial no suena; nueva tanda de 2 alertas elegibles → 1 aviso agrupado; silenciado → 0 avisos con 5 alertas nuevas; prueba de tono en local. **Audibilidad en dispositivo real no comprobada.** |
| A15 Borradores | Pasa (parcial) | Consulta y consulta al alternativo creadas y editadas (API y UI); sin destinatario inventado; alternativo con «stock sin confirmar»; sin alternativo → 409. Copiar y Descargar TXT no ejercitados con clic en navegador. |
| A16 Exportación | Pasa | XLSX de LiveDay en Railway: 14 filas, Y/N válidos, Is_Risk=N ⇒ Urgent=N, IDs únicos ordenados con `; `; celdas como texto; fixtures no exportables; bloqueo si hay filas pendientes, con error o con trabajos en cola. |
| A17 Persistencia | Pasa | Tras redesplegar web y worker se conservan resultados, incidentes, alertas y cursor/ETag RSS. Recuperación de lease probada con test (no forzada a mitad de trabajo en Railway). |
| A18 Acceso público | Pasa | HTTPS sin registro; mutaciones → 401 sin sesión y 403 sin CSRF; cookie `HttpOnly` + `Secure`; 10 bundles sin secretos (`scripts/smoke_test.py`, 12/12). |
| A19 Responsive | Pasa (emulación) | Sin overflow a 360, 390, 768 y 1440 px en todas las pantallas de producción; filtros en panel con Aplicar/Limpiar; diálogos devuelven el foco. Sin revisión en un móvil físico. |
| A20 Tiempo LiveDay | Pasa | 2,8 s y 2,7 s en Railway (≤ 300 s). |

## Pruebas automáticas

`python -m pytest -q` → 75 pruebas, todas en verde (PostgreSQL 18 local). Frontend: `tsc -b` y `vite build` sin errores.

## Pendientes reales

1. Ensayo de audio audible en un móvil real (Safari/Chrome) y en Chrome/Edge de escritorio con volumen; no funciona con la pestaña cerrada, el móvil bloqueado o en silencio.
2. Revisión en dispositivo móvil físico.
3. Antes de la demo, pulsar **Reiniciar análisis del lote** en LiveDay (Panel de presentador) para procesarlo en directo; hoy está analizado por los ensayos.
4. Copiar / Descargar TXT del borrador con clic real.
5. Supervisar coste y cupo de JEV en la cuenta TypeSafe (no hay precios en el motor). Cupo RSS: 100 análisis/día UTC.
6. El código no está en un repositorio git; conviene versionarlo antes de seguir iterando.
7. Bundle principal de 796 kB (241 kB gzip) por la librería de gráficos.
