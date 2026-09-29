# Arquitectura de TRAMA

TRAMA es un entorno de coordinación y conocimiento independiente de los
proyectos que conecta. El proyecto conectado conserva su código, dependencias,
pruebas, secretos y ciclo de despliegue.

## Separación de responsabilidades

```text
Todos los clientes (CLI / TUI / Hermes MCP)
  |
  v
Gateway Go (único borde: auth, cuotas, idempotencia y proxy)
  |\
  | +--> PostgreSQL: admisiones, estado, eventos, logs e inbox
  | +--> NATS JetStream: transporte durable, no fuente de verdad
  |
  v
TRAMA Control Plane Python (privado, réplicas sin PVC)
  |
  +--> PostgreSQL: fuente de verdad del control plane
  +--> Workers Python: CCCC, retries e inbox por evento
  |
  +--> CCCC: tareas, actores, estados, mensajes y handoffs
  |      ^
  |      +-- HTTP autenticado --> puente local del host Windows
  |
  +--> Codex / OpenCode / otros agentes
  |
  +--> Hermes local -- MCP stdio --> Control Plane Python API
  |
  +--> MCP: herramientas y servicios
  |
  +--> Model Gateway: proveedores de modelos y Colibri local
  |
  +--> Local Agent Bridge Python: slots, leases y procesos locales

  +--> Semantica AgentContext: contexto, decisiones y memoria episódica
              |
              +--> evidencia aprobada --> Utopia MCP: conocimiento canónico
```

## Aislamiento

Toda tarea, memoria, artefacto y conocimiento lleva `organization_id` y
`project_id`. El acceso cruzado está prohibido por defecto. El conocimiento
compartido requiere una promoción explícita y evidencia verificable.

Los IDs de negocio no son globales: el runtime, la coordinación y los stores
los indexan por `(organization_id, entity_id)`. Los endpoints que reciben un
ID obtienen la organización desde `RequestContext` y el gateway la propaga en
`X-Organization-ID`; en local, omitirla solo es válido si el ID no es ambiguo.
SQLite migra los registros históricos al mismo índice namespace-aware y
PostgreSQL conserva la clave compuesta en `trama.state_records`.

## Integración de un proyecto

Un proyecto se registra con un manifiesto `ProjectManifestV1`. El manifiesto
declara capacidades y comandos seguros, pero nunca credenciales. TRAMA no
instala sus dependencias ni modifica su código.

El primer adaptador es `generador-diccionario-entidades`, que conservará la
extracción code-first y la auditoría Oracle como fuentes de evidencia. Su
linaje `tabla -> trigger -> DML -> tabla auditiva` podrá convertirse en un
`MemoryCandidate` y, tras validación, en una promoción a Utopia.

Semantica se usa nativamente dentro de los workers Python mediante
`AgentContext`, `ContextGraph` y `VectorStore`; el `agent_id`, la tarea y la
fuente viajan como metadata. Su servidor `semantica-mcp` es únicamente `stdio`
local para clientes MCP y no se trata como REST.

Utopia se despliega como aplicación Rust/PostgreSQL y cada knowledge base se
expone por `POST /api/v1/kbs/{kb_id}/mcp`. TRAMA usa `search_chunks` para leer y
`remember` para registrar una frase; la extracción de hechos queda pendiente de
revisión humana en Utopia. Los permisos se delegan a la PAT y al rol del
usuario en la base.

Hermes es un proceso externo supervisado de TRAMA. Puede consultar contexto,
enviar tareas, registrar resultados y capturar candidatos con evidencia a
través de MCP `stdio`. Su TUI de conversación, modelos, skills y memoria
propia no se duplican en TRAMA. No publica conocimiento canónico y no
sustituye a CCCC para coordinar actores. El bridge local Python registra la
capacidad de Hermes y Colibri mediante leases; no abre sus puertos al exterior.

Colibri Inference es un proveedor de modelos local, no memoria de TRAMA ni un
scheduler de tareas. Sus contextos KV son privados por sesión, organización y
proyecto; una instancia Colibri se registra inicialmente con capacidad uno.

La TUI de TRAMA consume los mismos servicios que la CLI: estado, proyectos,
tareas, agentes derivados, eventos de auditoría y candidatos visibles. No crea
estado paralelo ni acciones que no existan en el gateway. La implementación
TypeScript usa OpenTUI como único renderer interactivo y organiza la vista en
un `AppShell`, un rail de navegación, paneles reutilizables y overlays de
command palette/confirmación. Ink, Chalk, cli-table3, ora y yoctocolors quedan
disponibles para utilidades CLI, pero no se montan dentro del árbol OpenTUI.

El shell conserva la última proyección válida durante un fallo de refresh y la
marca como obsoleta, manteniendo visible el contexto para diagnóstico. El
polling se pausa mientras un overlay solicita una decisión. Aprobar, cancelar o
reintentar una tarea requiere confirmación contextual y solo después ejecuta el
POST correspondiente; un error se presenta como aviso recuperable.

Los requisitos se descomponen en fases y tareas con trazabilidad explícita.
Hermes actúa como planificador asistido por MCP: registra el requisito,
propone fases, dependencias y especialistas CCCC, y deja las tareas derivadas
en estado `planned` hasta la aprobación humana. Las fases sin dependencias
pueden ejecutarse en paralelo; una fase dependiente se habilita cuando todas
sus fases predecesoras completan sus tareas. Las tareas también pueden declarar
dependencias independientes dentro o fuera de su fase.

El endpoint `/v1/overview` entrega a la TUI una proyección gráfica del plan:
progreso por fase, cola (incluyendo tareas manuales y derivadas), agentes y
carga activa. La TUI lo representa con paneles densos, color semántico y
barras de progreso, manteniendo la API como única fuente de estado.

### Observabilidad y trazabilidad

La propuesta de la IA master se persiste como `PlanProposal` inmutable por
versión. Su `correlation_id` se hereda a requisito, fase y tarea para seguir
un cambio completo aunque varias fases corran en paralelo. `OperationEvent`
representa transiciones auditables; `TaskLog` representa mensajes de agentes,
handoffs, duración y diagnósticos. Ambos se pueden combinar en un
`TimelineEntry` por tarea o fase.

El worker puede usar `TRAMA_COORDINATION_BACKEND=cccc-bridge` para llegar al
CCCC del host Windows mediante un puente HTTP autenticado y de alcance local.
El backend predeterminado sigue siendo `memory`. Cada intento registra el
`task_id`, el `tracking_id` de CCCC y `dispatch_duration_ms`, que mide el envío
HTTP hasta la aceptación del `tracked-send`. La admisión del Gateway Go, el
outbox, la entrega NATS y `python_handoff_ms` son mediciones distintas; ninguna
de ellas prueba el inicio del modelo o la primera respuesta del actor.

La API expone `/v1/tasks/{task_id}/timeline`,
`/v1/phases/{phase_id}/timeline`, `/v1/logs` y `/v1/plans/{proposal_id}`.
Los filtros siempre respetan `organization_id` y `project_id`; la redacción
elimina credenciales antes de escribir en SQLite y la retención se limita con
la poda por proyecto. Hermes obtiene estas consultas por MCP, mientras que la
TUI las muestra como un radar compacto: carriles de fases paralelas, cola CCCC,
aprobaciones pendientes, bloqueadores y última actividad.

En local, la cola de tareas es acotada al proceso para proteger el control plane
aislado:
`TRAMA_QUEUE_CAPACITY` limita las tareas pendientes y
`TRAMA_MAX_CONCURRENCY` los despachos simultáneos. Cuando se alcanza la
capacidad admitida, la API responde `429 queue_full`; no se introduce un broker
compartido en esta fase.

En el modo distribuido, la admisión Go y el outbox escriben PostgreSQL en la
misma transacción. El gateway reenvía el resto de `/v1/*` al servicio privado
Python y propaga el principal como `X-Organization-ID`, `X-Project-ID`,
`X-Actor-ID`, scopes y correlación, autenticado con un token interno. El
outbox reclama filas con `FOR UPDATE SKIP LOCKED`, las publica con
`Nats-Msg-Id` y libera el lease si falla el publish. El consumidor Python usa
el durable `trama-python-dispatch`, `ack_wait` y `max_deliver`, deduplica por
`Nats-Msg-Id` mediante `trama.consumed_events` y solo hace `ack` tras
persistir/entregar la tarea. Redis aplica el límite de admisión compartido
entre réplicas. Kubernetes crea el schema mediante un Job de migración,
mantiene el servicio Python como ClusterIP y no monta PVC de estado. PostgreSQL,
Redis y NATS deben ser servicios gestionados o releases separados; sus URLs y
tokens llegan por un Secret existente.

La entrega a CCCC tiene además ownership durable en `trama.task_leases`, con
clave `(organization_id, task_id)`. El claim atómico asigna `owner_id`,
`lease_token`, `attempt` y `expires_at`; solo el owner con su token puede
renovar o liberar el lease. Python renueva periódicamente durante el despacho
y completa por namespace después de validar y persistir el resultado terminal.
Un worker caído deja un lease vencible para redelivery; el contrato es
at-least-once, no exactamente una ejecución externa. Las tareas `succeeded`,
`partial`, `failed`, `blocked` o `cancelled` no se vuelven a despachar al
recuperar el estado persistido. El TTL se controla con
`TRAMA_TASK_LEASE_SECONDS` (60 segundos por defecto).

## Política de fallos

- La ausencia de Semantica no detiene una tarea.
- La ausencia de Utopia no invalida una evidencia local.
- Un error de MCP se devuelve como resultado fallido de la herramienta.
- Un error de Model Gateway se registra en el `AgentResult`.
- Un conflicto de conocimiento bloquea la promoción canónica.
- DDL, credenciales y secretos nunca entran en la memoria compartida.
- El servidor MCP local solo registra las herramientas declaradas en la
  plantilla de Hermes y no expone recursos ni prompts adicionales.
