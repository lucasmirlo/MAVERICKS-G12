# Prompt de diseño de interfaz

Diseña e implementa Supplier Risk Radar siguiendo docs/05_DISENO_E_INTERACCION.md. Crea una aplicación de procurement en español, pública en Railway y cómoda desde 390 px. El objetivo de la primera pantalla es entender qué proveedor necesita atención y por qué.

Usa fondo #F8FAFF, tarjetas blancas, lavanda #F3F0FF, texto #0A2540 y acento #635BFF. El gradiente púrpura/cian aparece en una cabecera compacta y pequeños detalles. Tipografía Inter o system-ui, jerarquía clara, números tabulares, bordes delicados y sombras suaves. Mantén contraste accesible y foco de teclado. La sensación visual debe ser precisa, luminosa y sobria.

## Composición de escritorio

Sidebar estrecha con producto y navegación. Cabecera con título operativo, selector Ejercicio / Noticias reales, fecha de actualización, sonido y acceso de presentador. Después cuatro KPIs con definición del denominador. Columna principal con ranking de proveedores; columna secundaria con últimas noticias y estado de fuentes. La urgencia debe distinguirse de la prioridad y de la confianza.

Cada fila contiene proveedor, país, material, prioridad 0–100, urgencia, criticidad, fuente única y fecha de la evidencia. Al abrir, la ficha presenta el evento y las frases fuente antes del desglose numérico. Alternativo aprobado lleva Stock sin confirmar. Productos sin relación conocida lleva Productos no mapeados.

## Composición móvil

Navegación inferior Resumen / Noticias / Alertas / Más. Ranking en tarjetas con proveedor, prioridad, motivo de una línea y acción Ver detalle. Filtros en panel accesible con Aplicar y Limpiar. Métricas en dos columnas. La ficha usa una columna y botones de al menos 44 px. El borrador se abre a pantalla completa con copiar y descargar accesibles al pulgar. Comprueba 360 y 390 px sin scroll horizontal del viewport.

## Estados obligatorios

- Sin catálogo, con una acción de importación para el presentador.
- Motor sin configurar, con nombre de variable solo en vista administrativa.
- Lote procesando, con número completado, pendiente y error.
- Fuente consultada sin novedades y fuente con fallo, diferenciadas.
- Análisis en revisión, con el dato o decisión que lo causa.
- Riesgo activo, evento recuperado y noticia positiva.
- Audio desactivado, activado, bloqueado o silenciado.
- Contexto de fixtures claramente marcado si se usa durante desarrollo.

Los gráficos muestran volumen por fuente y distribución de prioridad, con leyenda, rango de fecha y alternativa textual. No presentes fixtures como métricas reales. No añadas un mapa ornamental que sugiera ubicaciones más precisas que los datos.

Respetar prefers-reduced-motion. Usa microinteracciones breves para apertura, hover y progreso. Mantén quieto el contenido que se está leyendo. Verifica visualmente capturas de 390 y 1440 px y prueba los controles con teclado.

Entrega componentes reutilizables, tokens de diseño, estados conectados a la API y una lista de pantallas revisadas. Prioriza completar el flujo de datos real antes de añadir decoración.
