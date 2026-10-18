# Diseño e interacción

## Dirección visual

Nombre del producto: Supplier Risk Radar. Idioma: español. Crear una herramienta de procurement que permita ver exposición, entender evidencia y actuar. La inspiración visual de Stripe se traduce en tipografía clara, contraste navy, superficies blancas y lavanda y un acento de gradiente discreto. Mantener la interfaz operativa visible desde la primera pantalla.

| Token | Valor inicial |
| --- | --- |
| Fondo | #F8FAFF |
| Superficie | #FFFFFF |
| Superficie secundaria | #F3F0FF |
| Texto principal | #0A2540 |
| Texto secundario | #52647A |
| Borde | #DCE3EE |
| Acento | #635BFF |
| Gradiente decorativo | #635BFF → #2BB9E8, con rosa #F5A9CC ocasional |
| Tipografía | Inter si está disponible, system-ui como fallback |
| Texto base | 16 px móvil; 14–16 px tablas de escritorio |
| Radio de tarjetas | 14 px |
| Espaciado | Escala 4, 8, 12, 16, 24, 32 px |

Usar rojo para urgente, ámbar para revisión, azul para información y verde para recuperado. Los estados llevan texto e icono; no depender del color. Verificar contraste WCAG AA. Los gradientes y las transiciones diagonales pueden aparecer en una cabecera compacta, sin competir con tablas y avisos. No incluir enormes titulares publicitarios en la pantalla de trabajo.

## Navegación y pantallas

Escritorio: sidebar con Resumen, Proveedores, Noticias, Alertas y Fuentes. Barra superior con contexto Ejercicio / Noticias reales, última actualización, búsqueda y control de sonido. Importar archivo y acceso de presentador son acciones identificables. Móvil: navegación inferior para Resumen, Noticias, Alertas y Más; filtros en panel desplegable.

| Pantalla | Contenido y acciones |
| --- | --- |
| Resumen | KPIs de proveedores urgentes, incidentes activos, noticias procesadas y fuentes operativas; ranking; novedades; progreso del lote. |
| Proveedores | Búsqueda, categoría, criticidad, fuente única, alternativo, urgencia y productos conocidos; orden por prioridad estable. |
| Ficha de proveedor | Identidad y ubicación, material, criticidad, cobertura y lead time, alternativo, productos, desglose del score e historial de eventos. |
| Noticias | Feed con fuente, fecha, titular, tipo y vínculo; distinguir positivas, irrelevantes, riesgos y pendientes. |
| Detalle de noticia | Resumen fuente, enlace original, frases que justifican el vínculo, evaluación por proveedor y botón de explicación. |
| Alertas | Nuevas, reconocidas y resueltas; urgencia, prioridad, origen, confianza y acciones. |
| Fuentes | Estado de los seis RSS, última consulta, número de novedades, errores y sincronización manual del presentador. |
| Borrador | Modal o pantalla con asunto, destinatario sin inventar, cuerpo editable, copiar y descargar TXT. |

Un proveedor puede estar sin riesgo activo y tener riesgo histórico. Mostrar ambas cosas con claridad. Si no hay correspondencia de productos, usar Productos no mapeados. Si faltan datos o el modelo no terminó, mostrar Pendiente o Requiere revisión. No pintar verde un estado desconocido.

## Responsive y accesibilidad

Comprobar 360, 390, 768 y 1440 px. No debe existir scroll horizontal en el viewport. El ranking móvil usa tarjetas compactas con proveedor, prioridad, urgencia y motivo; el detalle ofrece el resto de columnas. Botones táctiles de al menos 44 px, filtros accesibles, foco visible y diálogos que devuelvan el foco al cerrar. Los gráficos tienen leyenda y alternativa textual. Respetar `prefers-reduced-motion` y evitar parpadeo.

Renderizar tablas paginadas y listas eficientes. Estados loading, vacío, error, parcialmente completado y sin configurar deben estar diseñados. No depender de animaciones para comprender progreso.

## Sonido dentro de la pestaña

Mostrar Activar sonido, Probar alarma y Silenciar. El gesto de Activar crea o reanuda el AudioContext dentro del handler del clic. Probar reproduce un tono corto identificable, sin generar un incidente. Si el navegador rechaza la reproducción, mostrar el estado y conservar la alerta visual. La preferencia guardada no prueba que el audio esté desbloqueado en una nueva carga. [S10,S11]

La alarma dura aproximadamente un segundo con volumen moderado. Una alerta nueva elegible suena una vez por pestaña; almacenar los IDs de revisiones ya avisadas en sessionStorage. Aplicar cooldown de 30 segundos y agrupar las llegadas. No reproducir todas las alarmas históricas al abrir el dashboard. Al volver de una pestaña oculta, consultar novedades y como máximo emitir un aviso agrupado por lo ocurrido desde el último cursor.

Actualizar el título de la pestaña con el contador de alertas sin leer y mostrar un indicador persistente. El usuario puede silenciar sin reconocer alertas. Registrar errores de audio solo localmente, sin atribuirlos al motor de riesgo.

El objetivo verificable es Chrome/Edge escritorio y Safari/Chrome móvil con la página activa, audio habilitado y volumen del dispositivo disponible. No garantizar sonido con la pestaña cerrada, el teléfono bloqueado, el navegador suspendido o el dispositivo silenciado. Estas restricciones deben figurar en el guion de demo. No se requiere servicio de push ni permiso de notificaciones del sistema.

## Textos de interfaz

Etiquetas preferidas: Prioridad 82,4 de 100; Urgente; Requiere revisión; Inventario no aplicable; Inventario no informado; Alternativo aprobado, stock sin confirmar; Última consulta; Sin novedades; Error de conexión; Exposición potencial de cartera simulada; Datos del ejercicio.

Una ficha debe contestar con datos visibles: qué ocurrió, por qué vinculamos este proveedor, qué está en riesgo, qué sabemos del buffer, qué alternativa existe y cuál es el siguiente paso. No mostrar razonamientos internos del modelo ni argumentos comerciales del proveedor de IA.
