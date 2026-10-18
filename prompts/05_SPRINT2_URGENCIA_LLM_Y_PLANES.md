# Sprint 2 · Urgencia por prioridad, LLM para casos dudosos y planes de acción

Eres el desarrollador de este repositorio (Supplier Risk Radar, reto 4 del GenAI Mavericks Challenge).
Antes de tocar nada, lee `ESTADO_ENTREGA.md`, `config/risk_policy.json`, `app/scoring.py`,
`app/pipeline.py` (sobre todo `analyze_version` y `build_assessment`), `app/jev/questions.py`,
`app/texts.py`, `app/incidents.py`, `app/export.py`, `app/evaluation.py` y `app/models.py`.
**Esta versión es solo local.** La demo pública en Railway se queda como está (versión 1, solo JEV).
Trabaja en la rama `sprint2-local`, **no ejecutes `railway up`** ni cambies variables de Railway.
El LLM es **Ollama en este ordenador** (modelo `qwen3.5:9b` en GPU de 8 GB); OpenAI o Anthropic
llegarán más adelante cambiando solo variables de entorno.

Trabaja por etapas. Al final de cada etapa: `python -m pytest -q` en verde, `tsc -b` y `vite build`
sin errores, y un commit con un mensaje claro. No avances a la siguiente con tests en rojo.

## Reglas que no se negocian

1. `data/Copy of Supplier_Risk_Answer_Key 1.xlsx` y los archivos de LiveDay pueden seguir en el
   repo (los monitores lo han autorizado), pero **ningún umbral, prompt ni regla puede salir de
   ellos**: no los uses para calibrar ni para elegir versiones.
2. **Todo se ajusta solo con el training** (30 noticias). La validación (10) se ejecuta **una sola
   vez** al final, con la configuración congelada, y se informa como "tercer uso de validación".
   Test y LiveDay nunca se usan para ajustar.
3. El LLM **nunca** cambia una decisión que ya es firme (regla y JEV de acuerdo, con confianza alta).
   Solo actúa en los casos dudosos definidos en la etapa 3.
4. Ningún error del LLM se convierte en N ni bloquea el lote: si falla o tarda, se conserva la
   decisión de la regla y se marca `sin_segunda_opinion`.
5. Las cifras de los planes de acción (días, productos, proveedores) salen **siempre** de la base de
   datos, nunca del LLM. El LLM redacta; no inventa contactos, stock, cantidades ni compromisos.

## Etapa 0 · Limpieza de ensayos

- Script `scripts/purge_batch.py --context <id>` que borre por completo un lote y **todo lo que
  deriva de él**: artículos, versiones, análisis, evaluaciones de proveedor, incidentes, alertas y
  borradores. Pruébalo con un test. (Lo usaremos para quitar los ensayos de LiveDay de la base).

## Arranque local

Antes de la etapa 1, deja documentado y probado en el README un arranque local de un solo comando
(por ejemplo `docker compose up` con web, worker y PostgreSQL, o un script de PowerShell con
`uvicorn`, el worker y un PostgreSQL local). JEV sigue llamándose por API, así que hace falta
internet; Ollama corre fuera de Docker, en el propio Windows.

## Etapa 1 · La urgencia se decide con la prioridad P

Hoy `Urgent` sale solo de `p_urgent` de JEV (`scoring.decisions`), y la fórmula `P` no interviene.
Queremos que la decisión exportada y la explicación sean lo mismo.

1. **Ajuste a U en `scoring.priority`:** U = 1 si `Single_Source = Y` **o** si el alternativo
   aprobado también está entre los proveedores afectados por la misma noticia. Añade el parámetro
   `alternate_affected: bool` y su test.
2. **Nueva regla de urgencia por proveedor:**
   `urgent_rule = is_risk and impact_status == "active" and P >= policy.thresholds.urgent_priority`.
3. **Script `scripts/calibrate_urgency.py`:** sin llamar a JEV, lee de `supplier_assessments` el
   último análisis de cada noticia del lote de training, recalcula P con la política (incluido el
   ajuste de U) y lo cruza con las etiquetas `Urgent` del training (desde donde las guarde
   `evaluation.py`, con su acceso separado). Imprime una tabla con:
   - para cada umbral de 30 a 70 (paso 2,5): VP, FP, FN, VN, precisión, recall, F1;
   - las mismas métricas para tres variantes: solo regla, regla **o** `p_urgent ≥ 0,5`,
     regla **y** `p_urgent ≥ 0,5`;
   - la lista de noticias mal clasificadas con su P, gravedad, E y `p_urgent`.
   Elige el umbral con mejor F1 en training. En caso de empate, el que deje **más margen** entre el
   urgente con menor P y el no urgente con mayor P. Guárdalo en `risk_policy.json` como
   `thresholds.urgent_priority` y sube la política a `1.1.0`.
4. `p_urgent` de JEV pasa a ser **segunda opinión**: si `urgent_rule` y `p_urgent ≥ 0,5` coinciden,
   la decisión es firme; si no coinciden, el caso es dudoso (etapa 3).
5. Guarda en `SupplierAssessment` un campo nuevo `decision_source` con uno de estos valores:
   `regla`, `regla+jev`, `llm`, `humano`. Necesita migración de Alembic (`0004`).

## Etapa 2 · Cliente LLM configurable

- Módulo `app/llm/` con una función `adjudicate(...)` y otra `draft(...)` sobre una única interfaz.
- Configuración por entorno: `LLM_PROVIDER` (`ollama` | `none`, y más adelante `openai` |
  `anthropic`), `LLM_MODEL` (`qwen3.5:9b`), `LLM_BASE_URL` (`http://localhost:11434`; si la app
  corre dentro de Docker en Windows, `http://host.docker.internal:11434`), `LLM_API_KEY` (vacía
  con Ollama), `LLM_TIMEOUT_SECONDS` (45 por defecto) y `LLM_MAX_CONCURRENCY` (2 por defecto:
  una GPU de 8 GB no aguanta más en paralelo). Sustituye a `EXPLANATION_PROVIDER` y a las
  variables `OLLAMA_*` actuales, manteniendo la compatibilidad durante la migración.
- **Implementa ahora solo `ollama`, `none` y un proveedor falso para tests.** Deja la interfaz
  preparada para que añadir OpenAI o Anthropic sea un archivo nuevo y una variable, sin tocar el
  resto. Si usas PydanticAI, ya trae los tres proveedores.
- Ollama: usa su API compatible con OpenAI (`/v1`). Desactiva el modo de pensamiento propio de
  Qwen (nuestro campo `razonamiento` ya hace ese papel) y limita la salida (`max_tokens` ≈ 800).
  Documenta en el README que el servidor de Ollama debe arrancar con
  `OLLAMA_CONTEXT_LENGTH=8192` y que `ollama ps` debe mostrar `100% GPU`.
- Si Ollama no responde al arrancar, la app funciona igual en modo `none` (solo regla + JEV) y lo
  muestra en la pantalla de estado del motor.
- Salida estructurada y validada con Pydantic (PydanticAI con `NativeOutput`, o el modo de salida
  JSON del SDK del proveedor). Si la respuesta no valida tras 2 reintentos, cuenta como fallo.
- El contenido de las noticias va siempre como dato, delimitado y con la instrucción de no seguir
  órdenes que aparezcan dentro.
- Registra modelo, tokens, latencia y resultado de cada llamada, sin secretos.
- Tests con un proveedor falso: respuesta válida, inválida, timeout y `none`.

## Etapa 3 · El LLM decide los casos dudosos

**Un caso es dudoso** (por pareja noticia–proveedor) si se cumple alguna de estas condiciones:
- `urgent_rule` y `p_urgent` de JEV no coinciden;
- `p_link` o `p_risk` está en la banda de revisión (0,35–0,65);
- el vínculo es solo por región inferida (`link_basis == "inferred_region"`) y `p_link < 0,80`.

**Lo que recibe el LLM** (JSON, sin texto libre añadido):
- la noticia (titular, resumen, fecha) y la frase de evidencia elegida por JEV;
- la ficha del proveedor: material, ciudad, país, categoría, fuente única, alternativo y si está
  afectado, criticidad, cobertura, plazo de reposición y productos en los que se usa;
- las respuestas de JEV (probabilidades, tipo de evento, gravedad, estado, duración);
- el desglose de P y el umbral de urgencia vigente;
- las definiciones del reto: qué es riesgo y qué es urgente, copiadas del README del training.

**Lo que devuelve** (esquema Pydantic, con `razonamiento` como **primer** campo, para que razone
antes de decidir):
```
razonamiento: str        # 2–4 frases, citando la evidencia
vinculado: bool
es_riesgo: bool
urgente: bool            # solo puede ser true si es_riesgo
confianza: "alta" | "media" | "baja"
```

**Cómo se usa:**
- Con confianza alta o media, su decisión sustituye a la de la regla para esa pareja y queda
  `decision_source = "llm"`, guardando el razonamiento.
- Con confianza baja, la pareja sigue en revisión humana con la propuesta del LLM visible.
- Las llamadas van en paralelo con `LLM_MAX_CONCURRENCY`. Los resultados de JEV se publican al
  momento; las parejas dudosas aparecen como "en análisis" hasta que responde el LLM.
- **Objetivo de tiempo (en local, con Ollama):** el lote de Test (20 noticias) completo, con LLM
  incluido, en ≤ 3 min, y 14 noticias en ≤ 2 min. Mídelo con `scripts/measure_batch.py` y anota
  cuántas parejas llegaron al LLM y su latencia media. Si no se alcanza, reduce primero el texto
  que se envía al LLM antes de tocar umbrales.

## Etapa 4 · Planes de acción

Hoy solo hay borradores de correo. Queremos que cada incidente activo tenga un **plan de acción**:
qué hacer, por qué, para cuándo y qué productos están en juego.

**Las acciones las elige Python con reglas explícitas** (`app/actions.py`, versionadas en la
política). El LLM solo las redacta. Catálogo de acciones:

| Código | Acción | Cuándo se propone |
|---|---|---|
| `monitor` | Vigilar y revisar en el informe semanal | Riesgo no urgente, o P por debajo del umbral |
| `contact_supplier` | Pedir al proveedor impacto, pedidos afectados y fecha de recuperación | Todo riesgo con vínculo confirmado |
| `shift_to_alternate` | Mover volumen al alternativo aprobado | Hay alternativo aprobado **y no está afectado** |
| `increase_safety_stock` | Adelantar pedidos y subir el stock de seguridad | Urgente, o duración desconocida o mayor que la mitad de la cobertura |
| `start_dual_sourcing` | Iniciar la cualificación de una segunda fuente | Fuente única, criticidad High y (urgente o evento prolongado) |
| `reroute_logistics` | Cambiar de transportista o de ruta | Categoría Logistics afectada (usar el alternativo si existe) |
| `escalate_planning` | Avisar a planificación de producción | Urgente y la parada puede superar la cobertura (o duración desconocida con fuente única) |

Cada plan incluye, calculado desde la base de datos:
- **margen de stock** en días (`Inventory_Cover_Days`; "no aplica" en Logistics y Services) y la
  fecha estimada de rotura si la parada continúa;
- **productos afectados** (columna `Used_In_Products` de Materials; "Productos no mapeados" si no
  hay fila);
- **alternativo** (nombre, ciudad y si está afectado por algún incidente activo);
- **plazo** por acción: hoy, esta semana o próximo informe, según urgencia y margen.

Implementación:
- Entidad `ActionPlan` (migración `0005`) ligada al incidente, con `actions` (lista de códigos con
  motivo), `facts` (el JSON de hechos usado) y `facts_hash`. Se regenera si cambian los hechos.
- Texto del plan: plantilla por defecto; si hay LLM, este redacta un resumen de 80–120 palabras
  **a partir de `facts` y `actions`**, sin añadir acciones nuevas ni cifras que no estén en `facts`.
  Si falla, se queda la plantilla.
- **Los borradores de correo salen del plan:** `contact_supplier` genera el correo al proveedor y
  `shift_to_alternate` el correo al alternativo (que pide disponibilidad, capacidad y plazo, **sin
  comprometer compras**). El idioma lo decide el país del destinatario: español para España y
  Latinoamérica; inglés para el resto. Destinatario siempre `[contacto de compras]`.
- Tests: cada regla de acción con su caso, un proveedor sin alternativo, alternativo afectado,
  servicios sin inventario y el LLM sin añadir cifras (compara números del texto con `facts`).

## Etapa 5 · Interfaz

- **Proveedores:** muestra `E` como "Índice de dependencia" (0–1) con sus componentes, y ordena por
  ese índice cuando no hay incidentes activos.
- **Detalle de noticia y de alerta:** muestra `decision_source` con una etiqueta clara (Regla,
  Regla + JEV, IA, Persona) y, si decidió el LLM, su razonamiento.
- **Alerta:** bloque "Plan de acción" con las acciones, plazos, margen de stock, productos y
  botones para abrir los borradores ya generados.
- Mantén accesibilidad y las pruebas de 360/390/768/1440 px.

## Etapa 6 · Evaluación y exportación del Test

1. Pasa el training completo con la configuración final y guarda el informe en
   `evaluation/runs/`, con un desglose de cuántas parejas decidió cada fuente.
2. Pasa la validación **una vez** y anótala como tercer uso.
3. Script `scripts/export_consensus.py --batch <test>`: ejecuta el lote 3 veces (JEV no es
   determinista), vota por mayoría `Is_Risk`, `Urgent` y cada ID de proveedor, y exporta el XLSX
   en el formato del reto con fecha y hora en el nombre. Guarda también las 3 ejecuciones.
4. Actualiza `ESTADO_ENTREGA.md` con una sección nueva "Versión 2 (local)": métricas con
   denominadores, tiempos en local, umbral elegido y por qué, modelo de Ollama usado y pendientes.
   Deja claro que Railway sigue en la versión 1.

## Entrega

Al terminar, resume en el chat: commits por etapa, tabla de calibración del umbral, métricas de
training y validación antes y después, tiempo del lote de Test en local y lo que haya quedado
pendiente.
