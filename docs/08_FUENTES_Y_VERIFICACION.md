# Fuentes y alcance de la verificación

Revisión realizada el 16 de octubre de 2026. Los enlaces siguientes permiten a Codex comprobar contratos que pueden cambiar. Las decisiones de producto son propuestas de este kit; no son requisitos atribuidos a los proveedores de infraestructura.

## Documentación primaria y página aportada

| ID | Fuente | Uso |
| --- | --- | --- |
| S1 | [Página aportada sobre JEV](https://jevai.net/es/) | Su pie se identifica como comunidad no afiliada. Punto de partida, no contrato de integración. |
| S2 | [TypeSafe API](https://docs.typesafe.ai/api) | Endpoint, autenticación, preguntas, respuestas y errores. |
| S3 | [TypeSafe Models](https://docs.typesafe.ai/models) | Versiones, aliases, límites de contexto y disponibilidad por cuenta. |
| S4 | [TypeSafe Quickstart](https://docs.typesafe.ai/introduction/quickstart) | Flujo inicial y credenciales. |
| S5 | [Cloudflare JEV](https://developers.cloudflare.com/ai/models/typesafe/jev/) | Alternativa de proveedor; no se usa en la ruta principal. |
| S6 | [TypeSafe Score](https://docs.typesafe.ai/primitives/score) | Escala ordinal y salida ponderada. |
| S7 | [TypeSafe Noul](https://docs.typesafe.ai/primitives/noul) | Decisión binaria expresada entre 0 y 1. |
| S8 | [TypeSafe Confidence](https://docs.typesafe.ai/confidence) | Interpretación de confianza en decisiones. |
| S9 | [TypeSafe Fan out](https://docs.typesafe.ai/patterns/fan-out) | Preguntas independientes agrupadas sobre un estado. |
| S10 | [MDN Autoplay](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Autoplay) | Restricciones de reproducción automática. |
| S11 | [MDN Web Audio](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API/Best_practices) | Gesto del usuario y activación de audio. |
| S12 | [Railway hosted inference](https://docs.railway.com/guides/ai-api-hosted-inference) | Inferencia mediante proveedor externo. |
| S13 | [Railway FastAPI](https://docs.railway.com/guides/fastapi) | Servicio web Python y despliegue. |
| S14 | [Railway Services](https://docs.railway.com/services) | Ejecución de servicios y almacenamiento efímero. |
| S15 | [Railway PostgreSQL](https://docs.railway.com/databases/postgresql) | Servicio de base de datos y conexión. |
| S16 | [Railway Cron](https://docs.railway.com/cron-jobs) | Restricciones de planificación. |
| S17 | [Railway Domains](https://docs.railway.com/networking/domains/working-with-domains) | Publicación del servicio web. |
| S18 | [Railway Pricing](https://docs.railway.com/pricing) | Revisar plan y consumo al desplegar. |
| S19 | [Railway Config as Code](https://docs.railway.com/config-as-code/reference) | Configuración separada de web y worker. |
| S20 | [Railway Healthchecks](https://docs.railway.com/deployments/healthchecks) | Comprobación previa de disponibilidad del web. |
| S21 | [TypeSafe Choice](https://docs.typesafe.ai/primitives/choice) | Selección de categoría y evidencia entre opciones. |

La documentación de modelos distingue actualmente `jev-latest` → `jev-1.13.0` y `jev-preview` → `jev-1.14.0`. El kit fija la primera para la demo. No se usa un alias móvil como versión de evaluación. La rapidez del producto no se ha medido con esta cartera y estas preguntas.

## RSS comprobados

Los seis feeds se obtuvieron con una petición HTTP y se analizaron como XML. Todos devolvieron 200 y elementos de noticia. El resultado exacto, content type, URL resuelta y conteo está en `evidence/rss_verification.json`. La configuración operativa vive en `config/rss_sources.json`.

| Fuente | Página de descubrimiento | Endpoint comprobado |
| --- | --- | --- |
| BioPharma Dive | [Sitio editorial](https://www.biopharmadive.com/) | https://www.biopharmadive.com/feeds/news/ |
| Supply Chain Dive | [Sitio editorial](https://www.supplychaindive.com/) | https://www.supplychaindive.com/feeds/news/ |
| The Loadstar | [Sitio editorial](https://theloadstar.com/) | https://theloadstar.com/feed/ |
| GDACS | [Guía oficial](https://www.gdacs.org/documents/2025/GDACS_MHEWS_guide.pdf) | https://www.gdacs.org/xml/rss.xml |
| EMA | [RSS oficiales](https://www.ema.europa.eu/en/rss-feeds) | https://www.ema.europa.eu/en/news.xml |
| EL PAÍS | [Directorio RSS](https://elpais.com/info/rss/) | https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/internacional/portada |

Esta comprobación demuestra que los endpoints respondieron en la fecha indicada desde el entorno de investigación. No prueba continuidad futura, exactitud de sus noticias ni acceso desde Railway. El ensayo de despliegue vuelve a comprobarlos. No se redistribuyen artículos completos en el kit.

## Entradas del usuario y comprobaciones de datos

Se leyeron el brief, Suppliers y Materials, esquemas de los cuatro Excel y etiquetas disponibles de desarrollo/validación para conocer el contrato. Las estadísticas de cartera proceden de esas tablas. No se abrieron ni incorporaron respuestas del answer key. No se clasificaron noticias de test o LiveDay como entregable de este trabajo.

Hallazgos que condicionan el diseño: 40 proveedores; 20 materiales; seis productos; 14 single source, de los cuales siete son High; 10 materiales sin alternativo. Materials cubre 30 proveedores. Seis filas de Logistics/Services no tienen inventario y S035 no tiene lead time. Hay 17 proveedores con cobertura inferior a lead time entre los que permiten esa comparación. El share de gasto corresponde a su categoría, no a cuota de producción.

Hay 30 noticias etiquetadas de entrenamiento y 10 de validación. Suman siete ejemplos urgentes. Los positivos empresariales también pueden contener IDs de proveedor: no vaciar el vínculo solo porque Is_Risk sea N. El README de entrenamiento usa un nombre de hoja distinto de la hoja real News.

## Qué se entrega probado y qué se debe probar al implementar

| Estado | Comprobación |
| --- | --- |
| Verificado en este kit | Lectura de esquemas, conteos de cartera y hashes de entradas. |
| Verificado en este kit | Seis feeds HTTP 200 y XML con noticias. |
| Verificado en este kit | Referencias de fórmula y construcción de peticiones mediante pruebas unitarias. |
| Verificado en este kit | Archivos de configuración, JSON Schema, ejemplos y referencias internas mediante validador. |
| Pendiente de credenciales | Petición autenticada real a JEV y medición de latencia/coste. |
| Pendiente de implementación | Rendimiento de clasificación y evaluación retenida. |
| Pendiente de despliegue | Servicios Railway, persistencia, RSS desde Railway y lote de 14 noticias en 300 segundos. |
| Pendiente de dispositivo | Audibilidad real y uso móvil en los navegadores objetivo. |

El resultado de pruebas locales del kit queda en `evidence/validation_report.json`. No confundir ese informe con las pruebas E2E de una aplicación ya construida.
