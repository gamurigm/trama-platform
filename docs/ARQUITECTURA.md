# Arquitectura de TRAMA

TRAMA es un entorno de coordinación y conocimiento independiente de los
proyectos que conecta. El proyecto conectado conserva su código, dependencias,
pruebas, secretos y ciclo de despliegue.

## Separación de responsabilidades

```text
Usuario
  |
  v
trama CLI / TUI
  |
  v
Gateway Go (admisión, cuotas, auth, idempotencia y lectura)
  |
  +--> PostgreSQL: admisiones, proyecciones y outbox
  |
  +--> NATS JetStream: comandos y eventos durables
  |
  v
TRAMA Control Plane Python
  |
  +--> Cola local SQLite solo para desarrollo aislado
  |
  +--> CCCC: tareas, actores, estados, mensajes y handoffs
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

  +--> Task admission client --> Gateway Go
  |
  +--> Semantica: contexto y memoria episódica
              |
              +--> promoción validada --> Utopia: conocimiento canónico
```

## Aislamiento

Toda tarea, memoria, artefacto y conocimiento lleva `organization_id` y
`project_id`. El acceso cruzado está prohibido por defecto. El conocimiento
compartido requiere una promoción explícita y evidencia verificable.

## Integración de un proyecto

Un proyecto se registra con un manifiesto `ProjectManifestV1`. El manifiesto
declara capacidades y comandos seguros, pero nunca credenciales. TRAMA no
instala sus dependencias ni modifica su código.

El primer adaptador es `generador-diccionario-entidades`, que conservará la
extracción code-first y la auditoría Oracle como fuentes de evidencia. Su
linaje `tabla -> trigger -> DML -> tabla auditiva` podrá convertirse en un
`MemoryCandidate` y, tras validación, en una promoción a Utopia.

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
estado paralelo ni acciones que no existan en el gateway.

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

La API expone `/v1/tasks/{task_id}/timeline`,
`/v1/phases/{phase_id}/timeline`, `/v1/logs` y `/v1/plans/{proposal_id}`.
Los filtros siempre respetan `organization_id` y `project_id`; la redacción
elimina credenciales antes de escribir en SQLite y la retención se limita con
la poda por proyecto. Hermes obtiene estas consultas por MCP, mientras que la
TUI las muestra como un radar compacto: carriles de fases paralelas, cola CCCC,
aprobaciones pendientes, bloqueadores y última actividad.

La cola de tareas local es acotada al proceso para proteger el control plane
aislado:
`TRAMA_QUEUE_CAPACITY` limita las tareas pendientes y
`TRAMA_MAX_CONCURRENCY` los despachos simultáneos. Cuando se alcanza la
capacidad admitida, la API responde `429 queue_full`; no se introduce un broker
compartido en esta fase.

En el modo distribuido, la admisión Go escribe PostgreSQL y su outbox en la
misma transacción. El outbox reclama filas con `FOR UPDATE SKIP LOCKED`, las
publica con `Nats-Msg-Id` y libera el lease si falla el publish. El consumidor
Python usa el durable `trama-python-dispatch`, valida `task.admitted.v1`,
deduplica por `Nats-Msg-Id` y solo hace `ack` tras persistir/entregar la tarea.
Redis aplica el límite de admisión con un script Lua atómico compartido entre
réplicas. Kubernetes se configura con el chart de
`deploy/helm/trama-gateway`; PostgreSQL, Redis y NATS deben ser servicios
gestionados o instalados aparte, y sus URLs llegan por un Secret existente.

## Política de fallos

- La ausencia de Semantica no detiene una tarea.
- La ausencia de Utopia no invalida una evidencia local.
- Un error de MCP se devuelve como resultado fallido de la herramienta.
- Un error de Model Gateway se registra en el `AgentResult`.
- Un conflicto de conocimiento bloquea la promoción canónica.
- DDL, credenciales y secretos nunca entran en la memoria compartida.
- El servidor MCP local solo registra las herramientas declaradas en la
  plantilla de Hermes y no expone recursos ni prompts adicionales.
