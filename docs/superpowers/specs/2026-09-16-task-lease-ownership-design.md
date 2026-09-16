# Ownership distribuido de tareas - Diseño

## Objetivo

Evitar que dos réplicas del worker Python despachen la misma tarea a CCCC y
permitir que otra réplica recupere una tarea cuando el worker propietario se
detiene. Postgres será la fuente de verdad para el ownership; NATS continuará
siendo el transporte de eventos y su entrega seguirá siendo al menos una vez.

## Problema actual

Al iniciar `TramaRuntime`, cada proceso carga las tareas `accepted` y `running`
y las entrega a su `TaskDispatcher` local. En un despliegue con varias
réplicas, todas las instancias pueden ejecutar la misma tarea. El inbox de
NATS deduplica un `event_id`, pero no coordina tareas que fueron recuperadas
por procesos diferentes ni cubre todos los reinicios.

## Decisión

Agregar un lease duradero por tarea, identificado por la tupla
`(organization_id, task_id)`. El lease tendrá un `lease_token` opaco, el
`owner_id` del worker, `claimed_at`, `expires_at`, `attempt` y un estado
`active` o `completed`.

La interfaz del almacenamiento será:

```python
claim_task(
    task: TaskEnvelope,
    *,
    owner_id: str,
    lease_seconds: int,
) -> TaskLease | None
renew_task_lease(
    lease: TaskLease,
    *,
    lease_seconds: int,
) -> bool
complete_task_lease(lease: TaskLease) -> bool
release_task_lease(lease: TaskLease) -> bool
complete_task_lease_for_task(
    organization_id: str,
    task_id: str,
    *,
    attempt: int | None = None,
) -> bool
is_task_lease_current(lease: TaskLease) -> bool
```

`claim_task` será atómico. Devuelve un lease solo si la tarea no tiene un
lease activo o si el lease anterior expiró; en caso contrario devuelve
`None`. Todas las operaciones posteriores validarán simultáneamente la
organización, el task ID, el owner y el token para impedir que un worker
antiguo libere o renueve el lease de otro.

El camino de transición a `running` usará una operación condicional que solo
persiste la transición si el intento del lease sigue activo. El camino que
persiste un resultado terminal validará de forma atómica el namespace, el
`execution_attempt` vigente y el lease activo antes de guardar la tarea, el
resultado y la finalización del lease. Así, un resultado tardío de un intento
anterior no puede sobrescribir el estado de una recuperación posterior.

La finalización genérica `complete_task_lease_for_task` queda disponible para
operaciones administrativas y acepta un intento opcional; el flujo normal de
resultados usa la operación atómica anterior.

El dispatcher reclamará el lease justo antes de pasar la tarea a `running` y
la conservará mientras la tarea siga siendo responsabilidad de ese worker.
Un hilo de renovación extenderá el vencimiento periódicamente. Al recibir un
resultado terminal se marca el lease como `completed`; si el despacho falla,
se libera el lease y se conserva la transición `failed` existente. Si el
proceso muere, deja de renovar y una réplica posterior puede reclamar el lease
vencido.

## Flujo de entrega

1. Gateway admite la tarea una sola vez mediante su idempotency key y publica
   `task.admitted.v1`.
2. Cualquier worker puede recibir el evento o encontrar la tarea al iniciar.
3. Antes de ejecutar, el worker intenta `claim_task` en Postgres.
4. Solo el worker que obtiene el lease encola y entrega la tarea a CCCC.
5. Un evento duplicado o una recuperación que no obtiene lease se confirma o
   se ignora sin volver a ejecutar la tarea; no cambia su estado.
6. El owner renueva el lease mientras la tarea esté activa.
7. El resultado terminal completa el lease. Un crash permite reclamar después
   de `expires_at`.

El modelo es at-least-once: una caída exactamente después de enviar a CCCC y
antes de persistir el avance puede causar un reintento tras vencer el lease.
El task ID seguirá siendo el identificador estable de idempotencia hacia CCCC
y el resultado continuará siendo idempotente en TRAMA. No se promete
exactly-once sobre un proveedor externo.

## Persistencia

Se añadirá la migración `000004_task_leases.sql` con una tabla namespace-aware
e índices para leases activos y vencidos. La tabla no tendrá una foreign key a
la tabla tipada de tareas porque el adaptador actual persiste tareas en
`trama.state_records`; el servicio validará que la tarea exista y pertenezca
al namespace recibido.

SQLite tendrá una tabla equivalente para conservar el comportamiento local y
permitir pruebas deterministas. La implementación en memoria será un doble de
prueba, no una ruta de producción distribuida.

## Contratos y compatibilidad

`TaskLease` será un contrato interno de infraestructura y no se expondrá en
la API pública ni en MCP. `TaskEnvelope` añade el campo nullable
`execution_attempt`, que solo se completa después de reclamar el lease y se
ignora al comparar reentregas idempotentes. `AgentResult` transporta el
intento que está confirmando y conserva el valor `1` por defecto para
compatibilidad con productores existentes. No se crea una configuración JSON.
El owner se generará por proceso a partir de un UUID y datos no sensibles del
worker; la duración se mantendrá como parámetro interno del servicio con
valores seguros para local y producción.

La recuperación dejará de convertir ciegamente todos los estados `running` a
`accepted`. La decisión de volver a encolar dependerá del lease: solo se
recuperarán tareas elegibles y reclamadas por la instancia actual.

## Errores y operación

- Lease activo de otra réplica: no es error de aplicación; se registra como
  `in_flight` y no se duplica el despacho.
- Lease expirado: se incrementa `attempt` y se registra el nuevo owner.
- Renovación perdida: el worker deja de considerarse owner y no debe aceptar
  nuevos cambios terminales con ese token.
- Error de Postgres: el worker no ejecuta sin coordinación duradera en modo
  distribuido; la tarea queda para redelivery o recuperación posterior.
- Lease abandonado: queda visible para diagnóstico mediante owner, intento y
  expiración, sin guardar secretos ni payload adicional.

## Pruebas de aceptación

- Dos stores/owners compitiendo por la misma tarea: exactamente uno reclama.
- Un lease activo no puede renovarse ni completarse con otro owner/token.
- Un lease vencido puede ser reclamado por otro owner y aumenta `attempt`.
- Una recuperación de dos runtimes no produce dos llamadas a coordinación.
- Un resultado terminal completa el lease y una entrega duplicada no vuelve a
  despachar.
- Un resultado de un intento expirado no puede sobrescribir el task ni
  completar el lease de un intento posterior.
- Una transición o resultado que pierda la carrera contra una recuperación se
  rechaza sin publicar un estado obsoleto.
- El camino SQLite existente y todas las pruebas de NATS continúan pasando.
- La migración PostgreSQL se valida sintácticamente y se añade una prueba de
  integración cuando el entorno de CI tenga Postgres disponible.

## Fuera de alcance

Este cambio no implementa todavía pool de conexiones, autorización por
proyecto, GraphQL, un scheduler global ni exactly-once externo. Tampoco agrega
`settings.json`, `.env`, credenciales ni configuración local versionable.
