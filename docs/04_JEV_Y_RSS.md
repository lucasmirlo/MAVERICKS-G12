# Integración de JEV y RSS

## Proveedor y contrato real

JEV es el modelo de decisiones de TypeSafe. La documentación primaria consultada publica `POST https://api.typesafe.ai/v1/systemone`, autenticación Bearer y cuerpo con `model`, `state` y `questions`. Este kit elige TypeSafe directo como ruta principal. `jevai.net` se identifica en su pie como un proyecto comunitario no afiliado; su ejemplo `/v1/decide` no es el contrato que implementaremos. [S1–S4]

Modelo inicial: `jev-1.13.0`, al que apunta el alias estable `jev-latest` en la documentación consultada. La versión `jev-1.14.0`, publicada el 14 de octubre de 2026, figura bajo `jev-preview`; queda como alternativa para evaluar después. Comprobar una llamada autenticada con el ID fijado durante la integración: la lista de modelos puede mostrar solo aliases. Registrar cualquier cambio de versión y repetir la evaluación pertinente. Cloudflare documenta también `typesafe/jev`, con su propio contrato y credenciales. [S3,S5]

No hace falta desplegar pesos de JEV en Railway. El backend llama a la API. Un cliente HTTP con timeout y validación del JSON es suficiente; si se utiliza el SDK oficial, fijar versión y validar su interfaz instalada. La generación de párrafos es otra tarea y utiliza plantillas u otro modelo opcional.

| Primitiva | Uso en este proyecto | Interpretación |
| --- | --- | --- |
| Noul | Vínculo, riesgo y urgencia por proveedor | Valor entre 0 y 1 para una proposición binaria. |
| Choice | Tipo de evento, estado y selección de evidencia | Una opción entre criterios definidos; no es selección múltiple. |
| Score | Severidad según diez niveles | Media ponderada de índices 0–9; convertir a 1–10 en el adaptador. |

La salida estructurada no garantiza una decisión correcta sobre el mundo. Guardar probabilidades, confidence si existe, errores y evidencias. No comunicar Cero errores ni una latencia comercial como resultado medido de esta aplicación. [S6–S9]

## Dos etapas con preguntas agrupadas

Etapa A recibe titular, resumen, fecha, idioma y catálogo compacto de los 40 proveedores. Formula un Noul por proveedor para identificar identidad directa o exposición operacional por lugar/material/ruta; además pregunta tipo y estado del evento. No poner un filtro de keywords que descarte una noticia regional antes de esta etapa. Para RSS, los filtros técnicos de duplicación, fecha y tamaño pueden actuar antes.

Los IDs de las preguntas sirven al programa; TypeSafe indica que las claves no se pasan al modelo para la inferencia. Por eso cada instrucción debe nombrar explícitamente el proveedor o el campo evaluado. Los candidatos incluyen nombres completos, país, ciudad, material y categoría. Las abreviaturas solo generan candidatos; no constituyen evidencia de identidad. [S2]

La selección no es un único Choice de proveedor: se aceptan varios Noul. Una noticia positiva nombrando realmente una empresa conserva su vínculo. Una coincidencia de ciudad con noticias sobre un aeropuerto o un partido de fútbol no establece exposición operacional.

Etapa B se ejecuta una vez por artículo con todos sus candidatos aceptados y, si procede, candidatos ambiguos para revisión. Incluye criticidad, alternativos, lead time, cobertura y spend. Pide por pareja: riesgo, urgencia, severidad, estado de impacto, frase de evidencia y duración explícita si existe. Las preguntas se envían juntas; no encadenar una llamada por atributo.

La evidencia se selecciona con Choice entre fragmentos reales identificados por código. El programa devuelve el texto exacto y sus offsets. Para duración, el programa prepara candidatos encontrados en el texto y JEV selecciona su ID o unknown. Normalizar unidades después. No permitir que JEV invente frases, días, ciudades ni IDs en campos de texto libre. `reference/jev_requests.py` demuestra la construcción y el contexto mínimo.

Para ubicaciones regionales implícitas, mantener una tabla de enriquecimiento con procedencia y estado verified/inferred. Country y City del Excel no contienen provincias ni rutas. Una relación inferida sin evidencia suficiente debe mostrarse como tal y no habilitar sonido automático. No atribuir a todos los proveedores de un país un evento limitado a una ciudad. Una restricción por producto exige comprobar también material y alcance.

## Estados, caché y tolerancia a fallos

Guardar el request_hash derivado de texto, catálogo, modelo y versión de preguntas. Igual hash permite reutilizar resultado explícitamente marcado como cacheado. Cambiar el texto crea una versión; cambiar política recalcula el score, conservando las respuestas originales cuando siguen siendo válidas.

Timeout inicial de JEV: 15 segundos por intento, hasta dos reintentos con backoff y jitter para 429, 529, errores de conexión y 5xx transitorios. Respetar Retry-After. 401, 400 y 422 requieren diagnóstico y no reintentos ciegos. Máximo cuatro solicitudes simultáneas y presupuesto de 60 segundos por artículo. Un lote manual tiene prioridad sobre RSS. Reservar margen para exportar dentro de los 300 segundos de la demo; medir, no asumir, la latencia. [S2]

Si no hay credenciales, la UI muestra Motor sin configurar. Fixtures permiten desarrollo en un contexto Demostración de interfaz claramente identificado. Un fallo de API nunca produce un falso No hay riesgos.

## Selección inicial de RSS

Las URLs exactas están en `config/rss_sources.json`. El 16 de octubre de 2026 todas respondieron HTTP 200 y su XML contenía elementos item. La evidencia de comprobación está en `evidence/rss_verification.json`; no supone disponibilidad futura desde Railway.

| Fuente | Cobertura | Elementos observados en comprobación |
| --- | --- | ---: |
| BioPharma Dive | Sector farmacéutico | 10 |
| Supply Chain Dive | Operación y cadena de suministro | 10 |
| The Loadstar | Transporte y logística | 10 |
| GDACS | Desastres y ubicación | 238 |
| EMA | Noticias y comunicación regulatoria | 11 |
| EL PAÍS Internacional | Actualidad general en español | 24 |

La selección cubre señal sectorial y ruido general sin depender de una sola editorial. FDA, FiercePharma, Economic Times, otros diarios y Google News pueden añadirse después de comprobar sus endpoints; no figuran como fuentes activas ficticias. Añadir feeds es una configuración de presentador, con validación de URL y prueba de respuesta.

## Contrato de ingesta

El worker consulta cada 300 segundos y el presentador dispone de Actualizar ahora. Al inicio, tomar hasta diez artículos por fuente publicados en las últimas 48 horas; si una fuente publica menos, mostrar esa realidad. Límite inicial de análisis RSS: 100 artículos nuevos por día UTC, configurable. Superar el cupo deja trabajo en espera visible y no lo declara irrelevante.

Usar ETag y Last-Modified; HTTP 304 cuenta como consulta correcta sin novedades. Limitar respuesta a 4 MB, diez segundos de timeout y redirects acotados. Parsear RSS/Atom con una biblioteca mantenida, desactivar entidades externas y extraer título, resumen suministrado, enlace, GUID, fecha y metadatos geográficos cuando existan. No exigir texto completo ni sortear muros de acceso.

Sanear HTML antes de mostrarlo. Guardar URL original y texto recibido. Revalidar hosts permitidos y destinos de redirects para impedir peticiones a localhost, rangos privados o servicios internos. No permitir que el contenido de la noticia modifique instrucciones, herramientas o URLs de integraciones.

La clave de identidad prefiere source_id + GUID, después URL canónica; el hash de contenido identifica versiones. No borrar parámetros que identifiquen un artículo. Las similitudes entre fuentes proponen agrupación de incidentes, no eliminan la procedencia. GDPR/etiquetas de publishers y payloads ajenos no se usan para entrenar el modelo de la app.

Guardar last_attempt_at, last_success_at, HTTP status, item_count, error_count y un mensaje concreto. En una caída conservar los artículos previos con fecha visible. Nunca mostrar Fuente en vivo si solo se está presentando una caché histórica.

## Evidencias históricas y recuperación

Los lotes del ejercicio comparten una cartera pero mantienen métricas y exportaciones por batch. Cuando se ejecutan en su fase autorizada, las noticias anteriores pueden aportar historial de eventos a LiveDay, sin etiquetas ni razonamientos del answer key. Una recuperación solo se aplica a un incidente compatible y más antiguo dentro del contexto Ejercicio. RSS nunca cambia los resultados exportados de un examen.

## Explicaciones y borradores

La explicación básica se forma con nombres validados, fragmento de noticia, categoría, p_link, impacto, criticidad, alternativo y desglose de score. Conservar incertidumbres y no atribuir capacidad o stock a un alternativo si el archivo no lo declara.

El generador opcional recibe ese JSON ya validado y escribe un resumen de hasta 100 palabras o un borrador. Usar `prompts/04_TEXTOS_Y_BORRADORES.md`. Si falla, conservar la plantilla determinista. El botón Copiar no envía correo. Las direcciones de destinatario no se inventan.
