# Observabilidad de planificación y ejecución

## Objetivo

Dar visibilidad verificable del recorrido completo de un requisito: propuesta
de la IA master, aprobación humana, fases paralelas, tareas derivadas,
despacho a CCCC, handoffs de especialistas y resultado final. La API de TRAMA
continúa siendo la fuente de verdad; Hermes solo media la interacción y
Semantica/Utopia permanecen detrás de sus adaptadores.

## Actores y límites

```text
Requisito + contexto
        |
        v
IA master (Model Gateway, perfil compatible con Codex)
        |  PlanProposal: fases + dependencias + tareas + criterios
        v
Hermes (MCP, supervisado) -- aprobación humana --> TRAMA API
                                                  |
                                                  v
                                      CCCC + especialistas
                                                  |
                                  resultados, handoffs, eventos y logs
```

- La IA master puede proponer y explicar un plan, pero no puede aprobarlo ni
  ejecutar tareas.
- Hermes presenta la propuesta, solicita aprobación y puede registrar ajustes;
  no mantiene una cola paralela.
- TRAMA valida linaje, permisos, dependencias y aprobación antes de admitir
  una tarea en CCCC.
- CCCC es responsable de asignación, handoffs y ejecución de especialistas.
- Semantica aporta contexto episódico y Utopia conocimiento canónico después de
  una promoción validada; ninguno sustituye el estado operativo de TRAMA.

## Modelo de datos

### PlanProposal

La propuesta se registra como evidencia versionada asociada a un requisito.
Incluye `proposal_id`, `requirement_id`, `model_profile`, `input_refs`,
`phase_ids`, `task_ids`, `summary`, `status` (`proposed`, `approved`,
`rejected`, `superseded`), `created_at` y `approved_by`. Una nueva propuesta no
borra la anterior.

### TaskLog

Los logs explicativos se separan de `OperationEvent`, que seguirá representando
transiciones de estado. Cada entrada contiene:

- `log_id`, `created_at`, `level` (`debug`, `info`, `warning`, `error`);
- `message` y `metadata` saneados;
- `organization_id`, `project_id`, `requirement_id`, `phase_id`, `task_id`;
- `actor` (IA master, Hermes, CCCC o especialista);
- `correlation_id` para seguir una ejecución completa;
- `duration_ms` opcional y `sequence` monotónico por tarea.

Los modelos limitan longitud y tamaño de metadata. Antes de persistir se
redactan tokens, cookies, claves, variables de entorno, contenido de `.env` y
rutas fuera del worktree permitido. La retención es acotada por proyecto y
tarea mediante configuración; al superar el límite se conservan las entradas
más recientes y un contador de truncamiento.

## Flujo operativo

1. Hermes registra el requisito y pide a la IA master una propuesta con
   `correlation_id` propio.
2. TRAMA persiste la propuesta, sus fases y tareas en `planned`, junto con
   eventos `plan.proposed` y logs de explicación.
3. La persona revisa la propuesta. La aprobación genera `plan.approve` y deja
   disponibles solo las fases cuyas dependencias están satisfechas.
4. Las fases sin dependencia se muestran como carriles paralelos. Cada tarea
   aprobada pasa a la cola CCCC; una tarea bloqueada por dependencia permanece
   visible como `awaiting_dependency`.
5. Cada despacho, handoff, reintento y resultado produce un `OperationEvent` y
   uno o más `TaskLog` asociados al mismo `correlation_id`.
6. Al terminar todas las tareas de una fase, TRAMA recalcula su progreso y
   habilita las fases dependientes. El requisito se completa cuando todas sus
   fases terminan.

## API de observabilidad

Se añaden consultas de solo lectura, filtradas por organización y proyecto:

- `GET /v1/tasks/{task_id}/timeline`: eventos y logs ordenados por secuencia;
- `GET /v1/phases/{phase_id}/timeline`: resumen de la fase y timeline agregado;
- `GET /v1/logs?task_id=&phase_id=&requirement_id=&level=&limit=`: búsqueda
  acotada de logs;
- `GET /v1/plans/{proposal_id}`: propuesta, versión y estado de aprobación.

`/v1/overview` incorpora `parallel_groups`, `pending_approval`,
`blocked_dependencies` y un resumen de la última actividad para que la TUI no
necesite reconstruir el grafo completo.

## TUI: radar operativo

La pantalla mantiene el formato denso y navegable de terminal:

```text
+---------------- FASES / PARALELISMO ----------------+ +------ COLA CCCC ------+
| A  ███████░░  3/4   B  ███░░░░░  1/3   C ↳ B        | | > tarea  agente  estado|
| dependencias: ✓ A, ✓ B     bloqueadores: 1          | | > tarea  agente  origen|
+------------------ ÚLTIMA ACTIVIDAD -----------------+ +------------------------+
| 12:04 CCCC handoff → especialista-api                |  Enter: timeline       |
| 12:03 Hermes plan aprobado                            |  r: actualizar  q: salir|
+------------------------------------------------------+--------------------------+
```

- `Enter` abre un panel de detalle de tarea con timeline de logs y eventos;
  `Esc` vuelve al radar.
- Filtros rápidos permiten alternar requisito, fase, agente, nivel y estado.
- Las fases paralelas se dibujan en carriles separados; las dependientes usan
  flechas y color atenuado hasta estar desbloqueadas.
- La paleta aprobada usa azul noche/morado oscuro como base y naranja para
  actividad, advertencias y barras; azul medio representa fases activas y
  morado identifica especialistas.
- Los mensajes de log se truncan en la vista y se pueden expandir sin cambiar
  la fuente persistida.

## Fallos y seguridad

- Si la IA master falla, el requisito queda `proposed` y el motivo se registra;
  no se crean tareas ejecutables.
- Si CCCC no responde, la tarea queda `blocked`/`queued` según el punto del
  flujo y conserva su timeline para reintento.
- Un fallo de Semantica o Utopia se muestra como advertencia contextual, no
  invalida la evidencia local ni el estado de la tarea.
- Las consultas nunca cruzan `organization_id` ni `project_id` y no devuelven
  secretos; los detalles sensibles se reemplazan por una marca de redacción.

## Verificación y entrega

- Pruebas de contrato para `PlanProposal` y `TaskLog`, incluyendo límites y
  redacción.
- Pruebas de persistencia y reinicio para timelines y retención.
- Pruebas de API para filtros, aislamiento y orden estable.
- Pruebas de runtime para paralelismo, bloqueadores y correlación de eventos.
- Pruebas TUI para carriles, cola, detalle y estados sin datos.
- Mantener compatibilidad con los contratos `1.0`; los nuevos campos y
  endpoints deben ser aditivos.

