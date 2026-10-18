# Despliegue en Railway

## Servicios elegidos

Desplegar un proyecto con web, worker y PostgreSQL. Web y worker parten del mismo repositorio e imagen Docker. La web sirve FastAPI y el build estático de React; el worker usa `python -m app.worker`. JEV vive en su proveedor API. Railway documenta el uso de FastAPI, Docker, PostgreSQL y servicios persistentes. [S12–S15]

El worker persistente evita depender de la puntualidad de cron durante la demo. Su loop programa RSS cada 300 segundos y atiende la cola de PostgreSQL. Si más adelante se migra el sondeo a cron, respetar UTC y las limitaciones de frecuencia y precisión documentadas. El procesamiento manual de LiveDay siempre se encola inmediatamente. [S16]

## Archivos que Codex debe entregar

- Dockerfile multietapa: build de frontend, instalación de backend y copia del frontend al servidor. Imagen ejecutada con usuario sin privilegios.
- Lockfiles y versión Python/Node compatibles comprobadas. No descargar dependencias o modelos en cada arranque.
- `railway.web.json` y `railway.worker.json`, usando los ejemplos del kit y rutas reales del repositorio construido.
- Migraciones Alembic; solo la web las ejecuta como pre-deploy. El worker espera a que el esquema requerido esté disponible y no hace migraciones concurrentes.
- `.env.example` sin secretos; comandos locales de desarrollo y un comando de verificación.
- README con configuración Railway, salud, logs, importación inicial y recuperación.

## Configuración

Escuchar en `0.0.0.0` y en el puerto proporcionado por `PORT`. La web se conecta a la base de datos por `DATABASE_URL`. El worker comparte la conexión. Publicar únicamente el servicio web; JEV y las claves se usan desde backend. Generar un dominio Railway con HTTPS y verificar navegación directa a una ruta de proveedor, no solo a la home. [S13,S17]

Variables requeridas: DATABASE_URL, TYPESAFE_API_KEY, JEV_MODEL, ADMIN_PASSWORD y SESSION_SECRET. Generar secretos fuera del código. Valores de límites, intervalos y rutas en `config/env.example`. La UI pública es de lectura; el presentador entra con contraseña compartida y una cookie HttpOnly, Secure, SameSite=Lax. Proteger mutaciones contra CSRF y limitar intentos de login. Nunca poner la clave de IA ni el secreto de presentador en variables VITE_*.

Guardar artículos, análisis, trabajos y borradores en PostgreSQL. El filesystem del contenedor es efímero: procesar el Excel en memoria/temporal y persistir las filas y el hash; generar la exportación desde la base de datos. Para conservar el fichero original más adelante, usar almacenamiento persistente u object storage explícito. El proyecto no depende de que sobreviva una carpeta local tras un redeploy. [S14]

## Secuencia de despliegue

1. Construir y probar la aplicación localmente, incluida la imagen Docker.
2. Crear proyecto Railway y servicio PostgreSQL.
3. Crear web desde el repo y seleccionar su configuración y Dockerfile.
4. Vincular DATABASE_URL mediante referencia al servicio PostgreSQL; configurar credenciales y secretos.
5. Ejecutar migraciones con pre-deploy de web y verificar /readyz.
6. Crear worker desde la misma imagen, con comando y variables propios, sin dominio público.
7. Generar dominio HTTPS de web, fijar APP_BASE_URL y CORS/sesión para ese origen.
8. Cargar el catálogo y el lote de desarrollo mediante operación idempotente del presentador. El import debe detectar una copia ya cargada.
9. Probar JEV autenticado desde Railway, sincronizar RSS, crear un borrador, comprobar persistencia después de redeploy y exportar.
10. Ensayar en un móvil real y un navegador de escritorio. Activar sonido antes de iniciar el lote de demo.

No asumir que GitHub, Railway o TypeSafe están autenticados. Si falta acceso, Codex termina todo el código y documenta el paso concreto pendiente. La creación de cuentas, gastos nuevos o acceso a credenciales se realiza conforme a la autorización del entorno de ejecución.

## Salud y operación

/healthz comprueba que el proceso está vivo. /readyz comprueba base de datos y migración. Un fallo temporal de JEV o de un RSS no debe hacer que Railway reinicie continuamente el web; se muestra por separado en la pantalla de fuentes/motor. Registrar IDs de batch/job, duración, HTTP status y número de intentos; redactar headers y secretos.

Un reinicio del worker recupera trabajos con lease vencida. Un nuevo análisis usa idempotency key y versiones para no duplicar alertas. Exportaciones se generan bajo demanda. Desactivar suspensión automática del worker durante la demo; preparar y verificar el web antes de proyectar.

## Coste y medición

El proveedor documenta facturación por plan y consumo. No prometer que 5 USD cubren toda la app ni que la inferencia sea gratuita. Establecer alertas de gasto, límites de recursos y presupuesto diario RSS. Un modelo de Ollama local no forma parte del despliegue elegido; si se usa el adaptador opcional, apunta a un servidor externo adecuado. [S12,S18]

Registrar coste estimado de llamadas según uso real y tarifa vigente de la cuenta, sin fijar precios comerciales en el motor. El kit no incluye credenciales ni demuestra una conexión autenticada. La aceptación exige comprobarla antes de la presentación.
