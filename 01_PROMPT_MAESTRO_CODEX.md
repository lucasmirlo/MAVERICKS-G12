# Construye Supplier Risk Radar

Actúa como ingeniero responsable de entregar una aplicación web funcional, probada y preparada para una demo pública en Railway. Trabaja en este repositorio hasta completar el alcance. La interfaz y la documentación de uso estarán en español.

## Lee primero

Lee `00_LEEME.md`, todos los documentos de `docs/`, `config/risk_policy.json`, `config/rss_sources.json` y los contratos de `contracts/`. Revisa el código de referencia y las entradas declaradas en `evidence/input_manifest.json`. Respeta AGENTS.md si existe y las instrucciones vigentes del entorno. No recorras indiscriminadamente archivos XLSX ni busques el answer key.

## Objetivo que debes entregar

Una aplicación Supplier Risk Radar para Helixa Pharmaceuticals con URL HTTPS pública, diseño responsive para móvil y escritorio, ingesta real de Excel y RSS, decisiones con JEV, ranking explicable de proveedores, ficha de proveedor y material, alertas sonoras dentro de la pestaña, borradores editables y exportación del reto.

RSS es obligatorio en la primera entrega. Conecta las seis fuentes de `config/rss_sources.json`, muestra estado y hora de última sincronización, y proporciona actualización manual al presentador. Un proveedor externo caído debe producir un estado visible y no romper las demás fuentes. Nunca simules que has consultado una fuente ni presentes fixtures como noticias en vivo.

## Stack elegido

- Frontend React con TypeScript, Vite, Tailwind y componentes accesibles; gráficos con una librería estable. Fija las versiones instaladas en el lockfile.
- Backend Python FastAPI, Pydantic, SQLAlchemy, Alembic y PostgreSQL. Procesa Excel sin modificar los originales.
- Un contenedor web sirve API y frontend compilado bajo el mismo origen; otro servicio worker usa la misma imagen. PostgreSQL conserva trabajos, artículos, resultados, incidentes, alertas y borradores. La cola inicial vive en PostgreSQL, con reclamación transaccional, leases y reintentos.
- JEV mediante `POST https://api.typesafe.ai/v1/systemone`, Bearer desde variable de entorno y modelo configurable. Por defecto del kit: `jev-1.13.0`, versión estable indicada por la documentación consultada; comprobarla con la cuenta. Sigue la documentación oficial de TypeSafe. No implementes `/v1/decide` tomado de sitios comunitarios.
- Para explicaciones, usa primero plantillas trazables. Añade un adaptador opcional a LLM compatible o a Ollama remoto; la demo completa debe funcionar sin ese generador adicional. El generador no cambia decisiones ni puntuaciones.

## Reglas de producto

1. Importa proveedores, materiales y noticias desde los cuatro Excel de `inputs/`. News, News_Validation, News_Test y News_Feed tienen columnas diferentes: detecta por esquema y conserva News_ID y orden original.
2. Excluye Is_Risk, Urgent, Affected_Supplier_IDs, Event_Type y Explanation del contexto de inferencia de cada artículo. Guarda etiquetas solo para evaluación. No entrenes ni ajustes prompts con validación, test o LiveDay.
3. Ejecuta JEV con preguntas acotadas. Evalúa todas las identidades de la cartera para no perder eventos regionales. Usa Noul por proveedor para selección múltiple; Choice devuelve una sola opción. El constructor de referencia es el punto de partida.
4. Distingue identidad, exposición operativa, riesgo, urgencia, severidad y confianza. Las noticias positivas pueden conservar proveedores identificados con riesgo N.
5. Implementa exactamente la política inicial de `config/risk_policy.json` y sus invariantes. Es una prioridad 0–100, no una probabilidad de quiebra ni de desabastecimiento. Registra la versión usada.
6. Agrupa actualizaciones del mismo evento; evita sumar artículos duplicados al score. Recuperaciones confirmadas pueden cerrar un incidente sin borrar el historial.
7. Crea dos contextos visibles: Ejercicio y Noticias reales. En Noticias reales, cualquier vínculo con la cartera ficticia se etiqueta como exposición potencial de la cartera simulada. Conserva la fuente original y la fecha real.
8. Exporta una fila por artículo con News_ID, Is_Risk, Urgent, Affected_Supplier_IDs. IDs únicos, ordenados, separados por `; `. Los errores pendientes se resuelven o se bloquea la exportación final; no los conviertas en N silenciosamente.
9. Incluye alertas dentro de la web y un botón Activar sonido. No solicites permisos de notificaciones del sistema ni conectes correo/Slack. Los borradores se editan, copian o descargan sin enviarse.
10. La URL pública permite lectura. Un acceso de presentador protege cargas, análisis, sincronización manual, cambios de política y generación de borradores. No publiques secretos ni etiquetas de evaluación en el frontend.

## Interfaz

Usa `docs/05_DISENO_E_INTERACCION.md` y `prompts/02_DISENO_UI.md`. El estilo es preciso y luminoso: blanco, lavanda, tipografía navy y acentos púrpura/cian. La pantalla principal es una herramienta operativa con noticias, proveedores y alertas; prioriza lectura y acciones. Cuida 390 px y 1440 px, estados vacíos, errores y foco de teclado. No reduzcas la versión móvil a una tabla diminuta.

## Forma de trabajar

Empieza por un plan corto, inspecciona el repositorio y crea la implementación por entregas verticales. Deja funcionar primero importación → JEV → persistencia → ficha → exportación, y después completa RSS, eventos, sonido y pulido. RSS permanece requisito de entrega, no un backlog opcional. Ejecuta pruebas significativas y verifica visualmente móvil y escritorio.

Cuando falte una clave, deja la integración real y su prueba de conexión preparadas, comunica el nombre de la variable necesaria y sigue con el trabajo independiente. El modo fixture debe estar explícitamente identificado. No afirmes haber probado JEV real, RSS desde Railway, audio en un dispositivo ni despliegue si no lo has hecho.

## Entrega técnica y criterios finales

Entrega código, migraciones, Dockerfile, configuración web/worker, `.env.example`, documentación, pruebas, evaluación separada de etiquetas y guía de despliegue. Despliega en Railway cuando haya acceso autorizado; si falta, entrega todos los artefactos y las acciones exactas pendientes. Realiza un smoke test sobre la URL final.

Antes de terminar usa `prompts/03_AUDITORIA_Y_ENTREGA.md`. Deben funcionar RSS real, proceso de 14 filas dentro de 300 segundos en el entorno de demo, exportación, alarmas tras el gesto de activación y experiencia móvil. Reporta tiempos medidos y limitaciones concretas, nunca una precisión inventada.
