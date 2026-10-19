# Estado de entrega · Supplier Risk Radar

Fecha de la auditoría: 18 de octubre de 2026 (UTC). Estado global: **demo desplegada y verificada con pendientes de dispositivo** (no es «listo para producción regulada»).

## Despliegue

| Elemento | Valor |
| --- | --- |
| URL pública | https://web-production-03417.up.railway.app |
| Proyecto Railway | `supplier-risk-radar` (entorno `production`) |
| Servicios | `web` (FastAPI + React, dominio HTTPS, pre-deploy `alembic upgrade head`, healthcheck `/readyz`), `worker` (`python -m app.worker`, sin dominio, sin suspensión), `Postgres` |
| Esquema | Alembic `0003` (incidentes y alertas por lote Excel) |
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

Repetición en Railway (18 oct, 11:51 UTC, mismas preguntas 1.2.0, sin caché): entrenamiento 30 filas en 5,2 s (riesgo VP 13/FP 0/FN 1, urgencia 5/5 sin FP, conjunto exacto 28/30, precisión por ID 0,76); validación 10 filas en 2,9 s (riesgo VP 5/FP 0/FN 0, urgencia VP 1/FP 1/FN 1, conjunto exacto 10/10). La diferencia en el riesgo de validación (4/5 en local, 5/5 en Railway) indica que JEV no es totalmente determinista entre ejecuciones. Con esta repetición, la validación se ha ejecutado dos veces, ambas sin ajustar nada a partir de sus resultados.

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

`python -m pytest -q` → 76 pruebas, todas en verde (PostgreSQL 18 local). Frontend: `tsc -b` y `vite build` sin errores.

## Pendientes reales

1. Ensayo de audio audible en un móvil real (Safari/Chrome) y en Chrome/Edge de escritorio con volumen; no funciona con la pestaña cerrada, el móvil bloqueado o en silencio.
2. Revisión en dispositivo móvil físico.
3. Antes de la demo, pulsar **Reiniciar análisis del lote** en LiveDay (Panel de presentador) para procesarlo en directo; hoy está analizado por los ensayos.
4. Copiar / Descargar TXT del borrador con clic real.
5. Supervisar coste y cupo de JEV en la cuenta TypeSafe (no hay precios en el motor). Cupo RSS: 100 análisis/día UTC.
6. El código no está en un repositorio git; conviene versionarlo antes de seguir iterando.
7. Bundle principal de 796 kB (241 kB gzip) por la librería de gráficos.

## Versión 2 (local) · sprint 2

Rama `sprint2-local`. **Solo local:** Railway sigue en la versión 1 (solo JEV), sin `railway up` ni cambios de variables. Fecha: 18 de octubre de 2026.

| Elemento | Valor |
| --- | --- |
| Arranque | `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1` (PostgreSQL en `.pgdata`, migraciones, frontend, worker y web) |
| Esquema | Alembic `0005` (decisión por pareja `0004`, planes de acción `0005`) |
| Política | `1.1.0`: urgencia por prioridad, `thresholds.urgent_priority = 50`, U = 1 también si el alternativo está afectado, `action_rules` 1.0.0 |
| JEV | `jev-1.13.0`, preguntas `1.2.0` (sin cambios) |
| LLM | Ollama 0.40.4 en Windows, `qwen3.5:9b` en RTX 4060 de 8 GB (`ollama ps`: 100% GPU), API compatible con OpenAI, `reasoning_effort=none`, `max_tokens` 800, `LLM_MAX_CONCURRENCY=2`. Prompt de adjudicación 1.1 |

### Umbral de urgencia elegido (solo training, sin llamar a JEV)

`scripts/calibrate_urgency.py` recalcula P de las 30 noticias de training y lo cruza con sus 5 urgentes etiquetadas. F1 de la regla por umbral: 30–35 → 0,62; 37,5–40 → 0,67; 42,5 → 0,77; 45 → 0,83; **47,5 / 50 / 52,5 → 0,91**; 55–57,5 → 0,67; 60–67,5 → 0,57; 70 → 0,33. Empate entre 47,5, 50 y 52,5; se eligió **50** por dejar más margen (2,5 puntos) al P más cercano. En 50: solo regla VP 5, FP 1, FN 0, VN 24; regla ∨ JEV F1 0,91; regla ∧ JEV F1 1,00. Única noticia mal clasificada por la regla: N046 (P 58,3, p_urgent 0,45), que al discrepar con JEV pasa al LLM. Informe: `evaluation/runs/calibracion_urgencia_training.json`.

### Métricas con denominadores

| Lote | Versión | Is_Risk | Urgent | Proveedores |
| --- | --- | --- | --- | --- |
| Training (n = 30; 14 riesgos, 5 urgentes) | v1 (JEV) | VP 13 · FP 0 · FN 1 · VN 16 | VP 5 · FP 0 · FN 0 · VN 25 | exacto 28/30 · precisión ID 0,73 · recobrado 1,00 |
| Training | **v2 final** | VP 12 · FP 0 · FN 2 · VN 16 (P 1,00 · R 0,86) | VP 5 · FP 0 · FN 0 · VN 25 (P = R = 1,00) | exacto 28/30 · precisión ID 0,73 · recobrado 1,00 |
| Validación (n = 10; 5 riesgos, 2 urgentes) | v1 (local / Railway) | 4/5 y 5/5 aciertos, 0 FP | VP 1 · FP 1 · FN 1 · VN 7 | exacto 10/10 |
| Validación · **tercer uso** | **v2 final** | VP 5 · FP 0 · FN 0 · VN 5 (P = R = 1,00) | VP 1 · FP 2 · FN 1 · VN 6 (P 0,33 · R 0,50 · F1 0,40) | exacto 9/10 · precisión ID 1,00 · recobrado 0,90 |

Training se usó para ajustar (umbral y una iteración del prompt de adjudicación), así que sus cifras son optimistas. La validación se ejecutó una sola vez con la configuración congelada y sus fallos no se han inspeccionado. En urgencia, la versión 2 queda **por debajo** de la versión 1 en validación (F1 0,40 frente a 0,50), con solo 2 urgentes etiquetadas: no hay base para afirmar mejora. Fuente de decisión de las parejas (aceptadas o dudosas): training regla+JEV 15, IA 15; validación regla+JEV 7, IA 4. Ninguna sin segunda opinión ni de baja confianza.

### Tiempos medidos en local (JEV real + Ollama)

| Lote | Tiempo clic → XLSX | Parejas al LLM | Latencia media del modelo |
| --- | --- | --- | --- |
| Test, 20 noticias (objetivo ≤ 180 s) | **55,8 s** | 7 | 12,2 s |
| 14 noticias (objetivo ≤ 120 s) | **41,1 s** | 5 | 12,2 s |
| Training, 30 noticias (JEV en caché) | 103,0 s | 15 | 11,1 s |
| Consenso de Test, 3 ejecuciones sin caché | 64,1 · 60,8 · 50,6 s | 8 · 8 · 7 | — |

Ollama atiende las peticiones en serie en esta GPU: con 2 en paralelo, la latencia por llamada incluye la espera de la otra (unos 6–8 s de cálculo propio, unos 1.150 tokens de entrada y 220 de salida).

### Exportación del Test

`scripts/export_consensus.py --split test`: 3 ejecuciones completas (JEV sin caché + regla + LLM), voto por mayoría de Is_Risk, Urgent y cada ID. **18 de 20 filas unánimes**; N003 (urgencia 1-2) y N016 (riesgo 1-2) por mayoría. Resultado: 8 riesgos y 4 urgentes. Archivo: `evaluation/runs/supplier_risk_radar_News_Test_consenso_20261018_2217.xlsx`; ejecuciones y votación en los JSON con el mismo sello. Test no se usó para ajustar nada.

### Pendientes de la versión 2

1. El servidor de Ollama de este equipo corre con contexto 4096 (no se arrancó con `OLLAMA_CONTEXT_LENGTH=8192`); los prompts actuales caben (unos 1.150 tokens), pero conviene arrancarlo como indica el README.
2. La IA no considera riesgo la adquisición de un proveedor por un competidor ni la salida de su CEO (N018, N025 en training) pese al ajuste del prompt.
3. Urgencia en validación peor que la versión 1 con una muestra de 2 urgentes: revisar con más datos etiquetados antes de sustituir la versión 1 en Railway.
4. LiveDay y Test quedaron analizados en la base local por las mediciones; antes de una demo local se pueden limpiar con `scripts/purge_batch.py` y reimportar.
5. OpenAI y Anthropic: interfaz preparada (`app/llm/providers.py`), sin implementar.
6. Audio y móvil físico: sin ensayo en dispositivo real en esta versión.

## Versión 3 (local) · sprint 3

Rama `sprint3`. **Solo local:** Railway sigue en la versión 1, sin `railway up` ni cambios de variables. Fecha: 19 de octubre de 2026. Combina lo mejor de la v2 y de las dos apps del equipo (A y B, que usan la pregunta de urgencia original del kit y en validación sacaban F1 de urgencia 0,80).

| Elemento | Valor |
| --- | --- |
| Esquema | Alembic `0006` (`analyses.urgency_mode`) |
| Modo de urgencia | `URGENCY_MODE=jev` (por defecto): Urgent lo decide JEV con su pregunta. `regla_y_jev` (regla P ≥ 50 **y** JEV) y `llm` (la IA adjudica las parejas dudosas, la v2) siguen disponibles |
| JEV | `jev-1.13.0`, preguntas **`1.3.0`**: vínculo y riesgo de la 1.2.0 + pregunta de urgencia idéntica a `reference/jev_requests.py` |
| Política | `1.1.1` (umbral de prioridad 50; `action_rules` 1.1.0 con la acción `verify_link`, p_vínculo < 0,65) |
| LLM | Ollama `qwen3.5:9b`: explica, redacta planes y da su opinión, visible para revisión. Fuera del modo `llm` no decide ni bloquea la exportación, y sus trabajos van con prioridad baja y sin lote |

### Métricas con denominadores

| Lote | Versión | Is_Risk | Urgent | Proveedores |
| --- | --- | --- | --- | --- |
| Training (n = 30; 14 riesgos, 5 urgentes) | v1 | VP 13 · FP 0 · FN 1 · VN 16 | VP 5 · FP 0 · FN 0 · VN 25 | exacto 28/30 |
| Training | v2 | VP 12 · FP 0 · FN 2 · VN 16 | VP 5 · FP 0 · FN 0 · VN 25 | exacto 28/30 |
| Training | **v3** | VP 13 · FP 0 · FN 1 · VN 16 (P 1,00 · R 0,93 · F1 0,96) | VP 5 · FP 4 · FN 0 · VN 21 (P 0,56 · R 1,00 · F1 0,71) | exacto 28/30 · precisión ID 0,76 · recobrado 1,00 |
| Validación (n = 10) | v3 | **no ejecutada** | — | — |

Training solo se usó para **confirmar** la v3, no para ajustarla: la pregunta de urgencia es la del kit, sin retoques. Sus 4 falsos positivos de urgencia (N018, N046, N053, N057) son el precio de copiar la pregunta que mejor generalizó en validación en las apps A y B. La validación **no se ha vuelto a ejecutar**: ya lleva 3 usos y un cuarto dejaría de ser una medida limpia. Por eso, en la base local, el lote de validación conserva sus análisis de la v2 (preguntas 1.2.0), que aparecen como «Regla + JEV» o «IA» en la mesa de atención.

### Test por consenso

`scripts/export_consensus.py --split test` con `URGENCY_MODE=jev`: 3 ejecuciones completas con la caché JEV vaciada (6,1 · 6,1 · 6,2 s), voto por mayoría. **18 de 20 filas unánimes**; N036 (ID S032 en 2 de 3) y N055 (riesgo 2 de 3). Resultado: 8 riesgos y 5 urgentes. Archivo: `evaluation/runs/supplier_risk_radar_News_Test_consenso_20261018_2352.xlsx`. Coincidencia con las otras apps (solo comparación, sin etiquetas): con A, 19/20 en riesgo y 19/20 en urgencia; con B, 20/20 en riesgo. Test no se usó para ajustar nada.

### Tiempos medidos en local

| Lote | v2 (modo llm) | v3 (modo jev) |
| --- | --- | --- |
| 14 noticias, clic → XLSX (objetivo ≤ 120 s) | 41,1 s | **8,3 s** |
| Test, 20 noticias, una ejecución (objetivo ≤ 180 s) | 55,8 s | **≈ 6 s** |

El panel del lote separa ahora el **tiempo en cola** del **tiempo de proceso**.

### Funciones nuevas

- **Mesa de atención** (Resumen, idea de B): los casos activos, primero los urgentes y luego por prioridad, cada uno con quién decide (JEV, regla, IA, humano), el margen de stock y sus dos próximas acciones con plazo.
- **Modelo** (idea de B): configuración activa, quién decidió cada pareja, consenso por fila y uso de JEV y del LLM; en cada noticia, historial de sus ejecuciones.
- **Materiales** (idea de B): qué material se queda sin salida si su principal está afectado, con el alternativo aprobado y los productos en juego.
- **Borradores** (idea de A): lista de todos los correos con filtro por tipo. Nuevo tipo **Verificación de vínculo**: si el vínculo es solo regional, tiene p_vínculo < 0,65 o la IA discrepa, el plan pide confirmar con el proveedor y redacta el correo en su idioma.
- **CSV** del lote (idea de A) con las mismas reglas que el XLSX.
- **Versión de web y worker** (idea de B): el worker publica su revisión en el heartbeat y el Resumen avisa si no coincide con la de la web.
- Arreglo: al reconstruir incidentes se desvinculan las evaluaciones de análisis antiguos (antes la mesa mostraba fuentes de decisión de versiones anteriores).

### Pruebas y revisión

125 pruebas automáticas en verde. Revisión visual de Resumen, Alertas, Materiales, Borradores y Modelo a 1440, 768, 390 y 360 px sin desbordamiento horizontal; se corrigió el nombre largo del XLSX en Modelo, que desbordaba en móvil.

### Pendientes de la versión 3

1. Urgencia: la v3 cambia 4 falsos positivos en training por la pregunta que mejor generalizó en A y B. No hay medida limpia en validación (se evitó el cuarto uso); la única referencia independiente es la coincidencia del Test con A y B.
2. Llevar la v3 a Railway solo con autorización: migración `0006`, `URGENCY_MODE=jev`, redeploy de web y worker (la mesa avisará si quedan con revisiones distintas) y volver a analizar los lotes.
3. Los pendientes 1, 2, 5 y 6 de la versión 2 siguen igual.
