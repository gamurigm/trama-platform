# Protocolo experimental de TRAMA

## Propósito

Evaluar de forma repetible la admisión durable y la entrega de tareas del
gateway Go al worker Python mediante PostgreSQL, outbox y NATS JetStream.
Este protocolo es una base experimental para la tesis; los resultados de una
corrida de humo no constituyen evidencia estadística.

## Pregunta e hipótesis

**Pregunta:** ¿Cómo afectan la carga concurrente y las solicitudes repetidas a
la latencia, la tasa de admisión y la entrega observable de tareas en TRAMA?

- **H1 — idempotencia:** repetir una solicitud con el mismo
  `Idempotency-Key` y el mismo contenido devuelve la misma admisión y no crea
  una segunda tarea lógica ni un segundo evento outbox.
- **H2 — entrega integrada:** toda tarea aceptada por el gateway aparece en el
  estado persistido del control plane después de que outbox y worker la
  procesan.
- **H3 — carga:** al aumentar la concurrencia, la latencia de admisión aumenta;
  se medirá su distribución y la proporción de respuestas aceptadas,
  limitadas o fallidas.

H1 y H2 se pueden contrastar con la versión actual. H3 describe una medición,
no presupone un umbral de rendimiento. Una comparación causal contra una
arquitectura alternativa requiere definir e implementar una línea base antes de
afirmar que TRAMA la supera.

## Sistema bajo prueba

El flujo medido es:

```text
cliente → gateway Go → transacción PostgreSQL (admisión + proyección + outbox)
        → publicador outbox → NATS JetStream → worker Python → PostgreSQL compartido
```

El gateway limita solicitudes a 2000 por segundo en la configuración local de
Compose. Python usa coordinación en memoria salvo que se configure otro backend;
por tanto, que una tarea aparezca como `running` demuestra que llegó al
coordinador, no que un agente externo la haya ejecutado ni que haya terminado.

## Variables y métricas

Variables independientes:

- concurrencia del cliente: 1, 5, 10 y 25 solicitudes simultáneas;
- volumen por corrida: 100 tareas únicas;
- repetición: 1 reenvío idéntico por tarea con la misma clave idempotente.

Métricas por corrida:

- latencia de `POST /v1/tasks` en milisegundos: mediana, p95 y p99;
- tasa de respuestas `202`, `429` y errores;
- conflictos por clave idempotente y admisiones duplicadas;
- proporción de tareas aceptadas que aparecen en `GET /v1/tasks/{task_id}`;
- tiempo desde la admisión hasta que el API observa la tarea persistida;
- conteo de admisiones y eventos publicados, comprobando unicidad por tarea.

Registrar junto a cada corrida: fecha UTC, commit de Git, sistema operativo,
versión de WSL, Docker Engine y Compose, CPU/memoria asignadas a Docker, número
de réplicas, configuración del gateway y parámetros usados. Mantener la misma
máquina, imágenes, configuración y proyecto Compose al comparar niveles de
carga. Ejecutar una corrida de calentamiento que no se incluya en los
resultados.

## Preparación

Desde PowerShell, ejecutar Docker mediante WSL según `AGENTS.md`:

```powershell
wsl.exe -d Ubuntu -- sh -lc 'cd /mnt/c/Users/gamur/Documents/TRAMA/trama-platform && docker compose -f deploy/docker-compose.gateway.yml -f deploy/docker-compose.experiment.yml up --build --detach --wait'
```

Verificar que los siete servicios estén sanos:

```powershell
wsl.exe -d Ubuntu -- sh -lc 'cd /mnt/c/Users/gamur/Documents/TRAMA/trama-platform && docker compose -f deploy/docker-compose.gateway.yml -f deploy/docker-compose.experiment.yml ps'
```

El override experimental publica el control plane solo en `127.0.0.1:8090`;
el gateway está en `127.0.0.1:8080`. Definir
`TRAMA_CONTROL_PLANE_INTERNAL_TOKEN` con el mismo valor que recibe Compose
(por defecto local: `trama-local-internal-only`). Si se habilita la autenticación
del gateway, definir también `TRAMA_GATEWAY_SERVICE_ACCOUNT_TOKEN` con el token
de cuenta de servicio. El runner envía estas credenciales en las cabeceras sin
registrarlas en el manifiesto. Registrar en el control plane un proyecto
experimental con
`organization_id`, `project_id` y `repository` idénticos a los que se enviarán
en las tareas. Usar identificadores de organización y proyecto exclusivos de
la experimentación.

## Procedimiento

El runner automatiza los pasos 2–5, calcula resúmenes de latencia y genera
`tasks.csv` más `manifest.json`. Se ejecuta desde la raíz del repositorio con
el entorno Python del proyecto:

```powershell
$env:TRAMA_CONTROL_PLANE_INTERNAL_TOKEN = 'trama-local-internal-only'
.\.venv\Scripts\python.exe scripts\thesis\run_distributed_experiment.py `
  --run-id pilot-20260927-02 --count 100 --concurrency 5
```

El runner registra el proyecto si aún no existe, siempre con políticas de solo
lectura y sin permisos de escritura externa. Un proyecto existente se reutiliza
solo si organización y repositorio coinciden. Cambiar `--run-id` en cada
corrida; repetir con `--concurrency 1`, `5`, `10` y `25`, y hacer 30 corridas
por nivel. El programa se detiene con código distinto de cero si alguna
admisión, repetición, proyección o entrega falla. El manifiesto incluye commit,
versiones locales, parámetros y SHA-256 del runner, runtime y protocolo para
identificar los archivos exactos de la corrida.

1. Confirmar `/health` del gateway y que el proyecto de prueba esté registrado
   en `/v1/projects`.
2. Para cada nivel de concurrencia, enviar 100 tareas con `task_id` y
   `Idempotency-Key` únicos. Cada tarea debe tener el mismo valor para ambos,
   criterios de aceptación y `read_only: true`.
3. Medir el tiempo de cada primer `POST /v1/tasks` con reloj monotónico y guardar
   código HTTP y cuerpo. Reenviar el mismo cuerpo con la misma clave y guardar
   la respuesta del replay.
4. Consultar `GET /v1/tasks/{task_id}?organization_id={organization_id}` en el
   gateway para verificar read-your-write.
5. Consultar `GET /v1/tasks/{task_id}` en el control plane hasta que aparezca o
   venza el timeout fijado antes de la corrida. Medir tiempo de entrega.
6. Comprobar para cada tarea que existe una sola admisión y un evento outbox y
   que el evento tiene `published_at`. Registrar las diferencias como fallos;
   no descartarlas silenciosamente.
7. Repetir cada nivel 30 veces con espacios de cinco minutos entre corridas.
   Reportar mediana y rango intercuartílico entre corridas, además de p50/p95/
   p99 de latencia dentro de cada corrida.

Verificar cantidad y publicación de eventos outbox desde Ubuntu WSL, cambiando
el prefijo por el `run-id` medido:

```sh
docker compose -f deploy/docker-compose.gateway.yml -f deploy/docker-compose.experiment.yml exec -T postgres \
  psql -U trama -d trama -c "SELECT a.task_id, count(o.event_id) AS outbox_events, bool_and(o.published_at IS NOT NULL) AS published FROM gateway.admissions a LEFT JOIN gateway.outbox o ON o.task_id = a.task_id WHERE a.task_id LIKE 'pilot-20260927-02-%' GROUP BY a.task_id ORDER BY a.task_id;"
```

Guardar datos crudos en CSV/JSON bajo `artifacts/thesis/` con un identificador
de corrida; esa ruta está ignorada por Git. Conservar también un manifiesto JSON
con versiones, configuración, commit, parámetros y resultado de salud. No
incluir tokens, secretos ni variables de entorno sensibles.

## Criterios de validez

- H1 pasa si todos los reenvíos idénticos conservan la misma admisión y cada
  tarea tiene exactamente un evento outbox.
- H2 pasa si todas las admisiones `202` quedan visibles en el control plane
  antes del timeout establecido; informar también la distribución del tiempo
  de entrega.
- Una corrida con servicios no sanos, reloj no monotónico, puertos ocupados,
  reinicios no previstos o tareas de otro experimento se marca inválida y se
  repite, conservando el registro de la corrida inválida.
- Las conclusiones se limitan a la versión de software, hardware y
  configuración registrados. Un único equipo local no permite generalizar a
  producción.

## Corrida de integración observada

Fecha: 2026-09-27. Docker Engine 29.4.3 y Compose 5.1.3 en WSL Ubuntu. El stack
levantó PostgreSQL, Redis, NATS, gateway, outbox, control plane y worker; todos
pasaron el health check.

En aquella versión con SQLite se detectó y corrigió una vista obsoleta en el API
Python: la API y el worker eran procesos separados, pero las lecturas API no
reflejaban escrituras del worker hasta reiniciar el proceso. `TramaRuntime`
pasó a refrescar tareas persistidas al listarlas o consultarlas. La prueba de
regresión reproduce la escritura desde un segundo store.

Tras reconstruir el control plane con la corrección, una tarea de prueba produjo:

- admisión: `accepted`;
- reenvío con la misma clave: devolvió el mismo `task_id`;
- visibilidad posterior en el API Python: sí, estado `running`;
- latencia de la primera admisión: 146.97 ms.

Es una sola corrida manual y la latencia solo mide el primer POST desde este
equipo. Sirve para demostrar el recorrido funcional en el entorno local, no
para aceptar H3 ni comparar rendimiento. El runner tiene una corrida piloto de
cinco tareas a concurrencia dos: 5/5 respuestas `202`, 5/5 replays
idempotentes, 5/5 proyecciones visibles y 5/5 tareas visibles desde el worker;
sin errores. Latencia de admisión p50 19.609 ms y p95 63.328 ms; entrega
observada p50 258.256 ms y p95 774.757 ms. Los archivos piloto están en
`artifacts/thesis/pilot-20260927-01/`. Este tamaño solo valida el runner y el
flujo; no acepta H3. Antes de presentar resultados de tesis, ejecutar las
repeticiones definidas y archivar todos los datos crudos y manifiestos.
