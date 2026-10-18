# Implementación por etapas

Este prompt sirve para continuar un trabajo iniciado con el prompt maestro. No sustituye los contratos ni reinicia un repositorio que ya contiene avances válidos.

## Prompt

Lee el estado actual del repositorio, los documentos de este kit y las pruebas existentes. Identifica la siguiente etapa incompleta. Construye entregas verticales y deja cada una ejecutable antes de avanzar. No detengas el trabajo para confirmar decisiones ya cerradas. Cuando una credencial falte, prepara el adaptador real y sigue con lo independiente.

### Etapa 1 Datos y aplicación básica

Crea backend, frontend, base de datos y migraciones. Implementa importaciones idempotentes mediante lista explícita de entradas. Conserva IDs, orden, campos nulos y fechas. Normaliza Products a relación y crea diagnóstico de columnas/hojas. Separa etiquetas de evaluación del contexto de inferencia. Muestra el catálogo y la ficha responsive con datos reales del Excel. Añade exportación vacía bloqueada hasta análisis completo.

Aceptación: catálogo de 40/20/6; diez proveedores sin correspondencia de producto visibles; todos los esquemas reconocidos; sin lectura del answer key; reinicio no pierde importación.

### Etapa 2 JEV y decisión explicable

Implementa el adaptador TypeSafe desde el constructor de referencia, validación estricta de respuestas y registro de modelo/versión/latencia. Normaliza resultados de Noul, Choice y Score. Integra la política, revisión y agregación por artículo. Completa jobs, progreso y exportación. Usa desarrollo para afinar las preguntas, manteniendo la evaluación separada.

Aceptación: una noticia positiva conserva identidad; un evento regional admite varios proveedores; errores no se transforman en N; score coincide con referencia. Una prueba de payload confirma ausencia de etiquetas. Ejecuta una llamada real cuando exista TYPESAFE_API_KEY y registra el resultado sin secreto.

### Etapa 3 RSS y evolución de eventos

Conecta las seis fuentes. Implementa ETag, Last-Modified, límites, deduplicación y versiones por cambio de contenido. Crea el loop del worker y sus leases. Da prioridad al lote manual y conserva la cola excedida por presupuesto. Agrupa incidentes de forma conservadora, permite recuperación posterior y evita reapertura por recepción tardía. Separa contextos de ejercicio y noticias reales.

Aceptación: dos sincronizaciones iguales no duplican; cambio bajo mismo GUID crea versión; caída de una fuente no frena las demás; las fuentes muestran hora de consulta real; las noticias no vinculadas también se ven.

### Etapa 4 Alertas y acción

Completa filtros, ficha, evidencias, explicación por plantilla, bandeja de alertas y borradores. Implementa Activar sonido, Probar alarma y Silenciar con Web Audio. Usa cursor y sessionStorage para avisar una vez por revisión. El lote histórico inicial no reproduce sonidos acumulados.

Aceptación: audio depende de gesto y elegibilidad; cooldown agrupa; revisión bloquea sonido; copiar/descargar no envía nada; alternativo tiene stock sin confirmar.

### Etapa 5 Railway y demo

Completa contenedor multietapa, migraciones pre-deploy y configuraciones separadas. Despliega cuando haya acceso autorizado. Ensaya persistencia y recuperación de trabajos, rutas profundas, sesión, móvil y audio real. Congela versión antes de validación y ejecución final. Mide las 14 filas y la exportación dentro del límite del reto.

Aceptación: cumplir A01–A20 de docs/07. Si un acceso externo falta, termina los artefactos y entrega pasos exactos con ese bloqueo identificado. No afirmar que existe una URL o una prueba si no se ejecutó.

Al terminar cada etapa, resume cambios, comando de prueba ejecutado, resultado y siguiente paso. Conserva una lista breve de pendientes reales en el repositorio.
