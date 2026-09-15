# Núcleo Python con cola y backpressure para TRAMA

## Objetivo

Construir la primera vertical de `refact1.md` sobre el núcleo Python existente:
persistir el estado de TRAMA mediante sus puertos actuales, admitir tareas con
una cola acotada, limitar el despacho concurrente y devolver backpressure
observable cuando la instancia no tenga capacidad.

Esta fase prepara una frontera estable para futuros adaptadores de PostgreSQL,
Redis, NATS o workers externos sin introducirlos todavía.

## Alcance

La fase conserva:

- REST como interfaz de comandos y consultas del control plane.
- MCP `stdio` como interfaz supervisada para Hermes.
- Contratos Pydantic y esquemas JSON versionados en `1.0`.
- `TramaRuntime` como orquestador y la API como fuente única del estado.
- Validación de `organization_id`, `project_id` y repositorio antes de admitir
  una tarea.
- `StateStorePort` como frontera de persistencia y `SqliteStateStore` como
  adaptador local de desarrollo.

La fase no incorpora Gateway Go, GraphQL, Redis, NATS, PostgreSQL, cron,
ejecución remota ni cambios en el conjunto de herramientas MCP.

## Invariantes

1. Una respuesta HTTP `202` solo se emite después de validar el namespace,
   reservar capacidad, guardar la tarea y registrar su admisión en el estado
   local.
2. Una tarea que no puede reservar capacidad no se guarda ni se entrega al
   coordinador; la API responde `429` con el código `queue_full`.
3. La capacidad reservada se libera cuando el despacho termina o falla. Una
   excepción del coordinador nunca queda como un worker silencioso: se registra
   como transición fallida y como evento auditable.
4. Una tarea con el mismo `task_id` y la misma configuración es idempotente;
   la misma clave con otra configuración se rechaza.
5. Ningún dispatcher puede enviar una tarea antes de que el runtime valide la
   organización, el proyecto y el repositorio del manifiesto.
6. El cierre del runtime es idempotente y no deja threads de workers vivos.
7. El estado persistido y los eventos siguen siendo la fuente de verdad; la
   cola en memoria solo representa trabajo pendiente de despacho.

## Arquitectura

```text
POST /v1/tasks o trama_submit_task
              |
              v
       TramaRuntime
       - valida namespace
       - reserva capacidad
       - persiste accepted + evento
              |
              v
       TaskQueuePort
       cola bounded en memoria
              |
              v
       TaskDispatcher
       max_concurrency workers
              |
              v
       CoordinationPort -> CCCC u otro adaptador
```

### Puertos y adaptadores

`ports.py` añadirá un `TaskQueuePort` pequeño, independiente de `queue.Queue`
o de cualquier broker:

- `put(task)`: inserta una tarea ya admitida y puede indicar cola llena.
- `get(timeout)`: obtiene una tarea para un worker.
- `task_done()`: libera el elemento procesado.
- `qsize()` y `capacity`: exponen observabilidad local.
- `close()`: despierta a los consumidores y evita nuevas inserciones.

El adaptador inicial será una cola bounded thread-safe de la biblioteca
estándar. No publicará eventos ni persistirá datos por sí mismo.

`TaskDispatcher` será responsable de la reserva de capacidad, la creación de
workers, el despacho a `CoordinationPort`, el conteo de activos y el cierre.
Recibirá callbacks internos del runtime para persistir transiciones y eventos,
sin conocer SQLite ni la forma concreta de los registros.

La configuración inicial será tipada en `TramaSettings`:

- `TRAMA_QUEUE_CAPACITY=100`: máximo de tareas esperando despacho.
- `TRAMA_MAX_CONCURRENCY=4`: máximo de llamadas simultáneas al coordinador.
- `TRAMA_DISPATCH_TIMEOUT_SECONDS=900`: límite de espera de cierre y despacho
  controlado.

Los tres valores deben ser enteros positivos. Los defaults mantienen el
arranque local usable y todos los valores inválidos fallan al cargar la
configuración, no durante una solicitud.

### Admisión y persistencia

El dispatcher reservará un slot bajo un lock antes de invocar el callback de
persistencia. La secuencia será:

1. `TramaRuntime.submit_task` valida el proyecto y la identidad de la tarea.
2. El dispatcher intenta reservar capacidad; si no puede, lanza
   `QueueCapacityError` sin mutar el runtime.
3. El runtime guarda la tarea como `accepted` y su evento `task.submit`.
4. El dispatcher publica la tarea en la cola usando el slot reservado.
5. La API devuelve `202`.

Si la persistencia falla, la reserva se libera y la tarea no se publica. La
cola no se comparte entre procesos: cada proceso API tiene su propia capacidad
y el adaptador durable permite recuperar las tareas al reiniciar.

La capacidad de esta primera fase separa tareas esperando de workers activos.
Por tanto, una instancia admite como máximo `TRAMA_QUEUE_CAPACITY` tareas en
cola más `TRAMA_MAX_CONCURRENCY` tareas en despacho. La limitación de tareas
que CCCC mantiene activas después de aceptar el envío queda fuera de esta
fase, porque el contrato actual no ofrece una señal de finalización de esa
ejecución externa.

## Ciclo de vida y recuperación

Al tomar una tarea, el worker registra `accepted -> running`, ejecuta
`CoordinationPort.submit_task` y libera su slot al terminar la llamada.

- Si el envío termina correctamente, la tarea queda `running` hasta que
  `POST /v1/results` registre el resultado terminal existente.
- Si el coordinador lanza una excepción, el runtime registra `failed`, un
  evento con detalles sanitizados y libera el slot.
- `cancel_task` marca una tarea en cola como `cancelled`; el worker comprueba
  el estado antes de llamar al coordinador y la descarta si ya fue cancelada.
  No se intentará matar un proceso externo en ejecución.
- `retry_task` vuelve a solicitar admisión; si no hay capacidad, conserva el
  estado anterior y devuelve `429`.
- En el arranque, las tareas persistidas en `accepted` se reencolan hasta la
  capacidad disponible. Las tareas persistidas en `running` se normalizan a
  `accepted` antes de reencolarlas, porque el proceso anterior pudo morir
  durante el despacho.

El cierre detendrá nuevas admisiones, esperará hasta el timeout configurado,
marcará como `blocked` las tareas no despachadas si no puede drenarlas y
cerrará los workers sin bloquear indefinidamente el proceso API.

## API y observabilidad

`POST /v1/tasks` mantiene su respuesta `{"task_id": ..., "status":
"accepted"}` para admisiones exitosas. Cuando la capacidad esté agotada,
responderá:

```json
{
  "detail": {
    "code": "queue_full",
    "message": "La cola de tareas está llena"
  }
}
```

con HTTP `429` y un header `Retry-After` calculado de forma conservadora.

`GET /v1/status` conservará sus campos actuales y añadirá:

- `queue_depth`;
- `queue_capacity`;
- `active_dispatches`;
- `max_concurrency`;
- `dispatcher_status` (`running`, `draining` o `closed`).

Esto permite distinguir API disponible de API sin capacidad de admisión. La
salida no incluirá comandos, credenciales, argumentos completos ni secretos.

## Seguridad y aislamiento

La cola no relaja ninguna frontera de namespace. La validación ocurre antes de
reservar capacidad y antes de llamar al coordinador. Los eventos solo contienen
identificadores, estados y detalles operativos sanitizados. No se añadirán
variables con claves, tokens, cookies o credenciales a contratos, logs,
manifiestos o configuración de workers.

Los límites son globales por instancia en esta fase. La política de admisión se
mantendrá separada del dispatcher para poder añadir límites por organización,
proyecto, agente o tipo de tarea cuando exista un requisito medido.

## Pruebas de aceptación

Se añadirán pruebas que cubran:

- defaults y rechazo de valores no enteros, cero o negativos;
- admisión hasta la capacidad y respuesta `429 queue_full` al excederla;
- que el número de despachos simultáneos nunca supere
  `TRAMA_MAX_CONCURRENCY`;
- persistencia antes de la publicación y liberación ante errores;
- aislamiento de organización/proyecto/repositorio bajo carga;
- idempotencia de `task_id` y rechazo de configuraciones conflictivas;
- transición a `running`, error del coordinador y evento auditable;
- cancelación de una tarea aún en cola y reintento con backpressure;
- recuperación de tareas `accepted` y `running` desde SQLite;
- cierre repetido sin workers huérfanos;
- respuestas HTTP de admisión, `429` y estado operativo;
- suite completa, Ruff, exportación de esquemas y smoke MCP sin cambios de
  stdout fuera del protocolo.

## Evolución posterior

La siguiente etapa podrá implementar un adaptador durable multi-proceso y un
broker externo detrás de los mismos puertos. Esa evolución no podrá convertir
eventos o mensajes en una segunda fuente de verdad ni cambiar las reglas de
namespace, aprobación humana y promoción canónica.
