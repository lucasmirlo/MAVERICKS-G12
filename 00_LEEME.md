# Supplier Risk Radar

Kit de ejecución para Codex. Decisiones y fuentes revisadas el 16 de octubre de 2026.

El objetivo es construir una aplicación pública en Railway que importe los Excel del reto, ingiera RSS reales, evalúe la exposición de la cartera con JEV y muestre alertas explicables con sonido en el navegador. La interfaz será responsive y estará en español. Los proveedores de Helixa son ficticios.

## Cómo empezar

1. Descomprime este paquete en la carpeta del proyecto que abrirás con Codex. Puedes comenzar en un repositorio vacío.
2. Pega el contenido de `01_PROMPT_MAESTRO_CODEX.md` en Codex. El prompt indica qué documentos y contratos debe leer.
3. Configura una clave de TypeSafe en `TYPESAFE_API_KEY` y acceso al proyecto Railway cuando se llegue al despliegue. Nunca pegues claves en los prompts ni las publiques en el frontend.
4. Codex debe construir y probar la app, preparar el contenedor y ejecutar el despliegue cuando tenga acceso autorizado. Pedir únicamente las credenciales o accesos que falten.
5. Usa `prompts/03_AUDITORIA_Y_ENTREGA.md` para revisar el resultado y `docs/07_ACEPTACION_Y_DEMO.md` para ensayar la presentación.

## Qué incluye

| Archivo o carpeta | Uso |
| --- | --- |
| `Supplier_Risk_Radar_Especificacion.docx` | Documento de producto y ejecución para el equipo. |
| `01_PROMPT_MAESTRO_CODEX.md` | Instrucción inicial que pone en marcha la implementación. |
| `docs/02_ESPECIFICACION.md` | Alcance, datos, arquitectura, API y modelo de persistencia. |
| `docs/03_MOTOR_RIESGO.md` | Fórmula, umbrales iniciales, tratamiento de nulos y estados. |
| `docs/04_JEV_Y_RSS.md` | Integración de clasificación, noticias y evidencias. |
| `docs/05_DISENO_E_INTERACCION.md` | Pantallas, estilo, móvil y comportamiento del audio. |
| `docs/06_RAILWAY.md` | Servicios, variables, persistencia y guía de despliegue. |
| `docs/07_ACEPTACION_Y_DEMO.md` | Casos de prueba, criterios de entrega y guion de cinco minutos. |
| `docs/08_FUENTES_Y_VERIFICACION.md` | Fuentes técnicas, alcance de las comprobaciones y pendientes reales. |
| `prompts/` | Prompts por etapa y para textos explicativos opcionales. |
| `config/` | Política de riesgo, RSS, variables de entorno y configuración Railway. |
| `contracts/` | JSON Schema del resultado que consume la aplicación. |
| `reference/` | Código ejecutable de referencia del score, constructor JEV y pruebas. |
| `fixtures/` | Ejemplos sintéticos para pruebas de contrato, score y flujo. |
| `inputs/` | Copias de los cuatro Excel y del brief del usuario. |
| `evidence/` | Comprobación de RSS, manifiesto de entradas y validación del kit. |

El ZIP es una especificación con referencias ejecutables; la aplicación y su URL pública son el resultado que Codex debe construir. Los umbrales son una política inicial versionada, no una calibración estadística terminada. La integración autenticada de JEV y el despliegue Railway necesitan credenciales y pruebas en el entorno final.

## Decisiones cerradas

- RSS real es parte obligatoria de la primera versión. Se entregan seis fuentes activas verificadas.
- Railway alojará web, worker y PostgreSQL. JEV se consume por API oficial.
- El visitante entra en una URL HTTPS y puede consultar la demo sin registro. Las operaciones que cambian datos o generan coste requieren sesión de presentador.
- Avisos y borradores permanecen en el navegador. El usuario activa el sonido mediante un botón.
- El score se calcula por evento y proveedor. La confianza no se usa para rebajar la gravedad.
- Las noticias reales y el ejercicio mantienen contextos y estadísticas distinguibles.
- El answer key queda fuera del kit y de la aplicación. Ningún proceso puede cargarlo por exploración de carpetas.

## Orden de autoridad

Los requisitos expresos del usuario prevalecen. Para implementar, usar los contratos y `config/risk_policy.json` como fuente numérica; después las especificaciones Markdown. El Word resume las decisiones. El brief original conserva la procedencia y no debe reintroducir la fórmula sustituida.

## Comprobación local del kit

Desde la raíz del paquete:

```bash
python -m pip install -r reference/requirements.txt
python -m unittest discover -s reference -p 'test_*.py' -v
python reference/validate_bundle.py
```

Estas comprobaciones no llaman a servicios de pago. El README de la aplicación que cree Codex deberá añadir sus propios comandos reales de instalación, migración, ejecución y prueba.
