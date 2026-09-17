# Runtime aislado por namespace - Diseño

## Objetivo

Eliminar las colisiones de identificadores entre organizaciones en el runtime
Python. El mismo `project_id`, `task_id`, `requirement_id`, `phase_id` o
`proposal_id` debe poder existir en organizaciones distintas sin que la
memoria del proceso, la coordinación o la API devuelvan o modifiquen el objeto
de otro tenant.

## Evidencia del problema

Los leases y `state_records` de PostgreSQL ya usan organización, pero los
registros en memoria de `TramaRuntime` y `InMemoryCoordination` se indexan solo
por el identificador visible. Además, los endpoints con IDs en la ruta llaman
primero a `get_*` sin el contexto del request y después intentan validar el
namespace. Con IDs repetidos, el último registro cargado puede ocultar al
anterior antes de que ocurra la validación.

## Decisión

Introducir una colección interna `ScopedStore` que almacena cada valor bajo la
clave `(organization_id, entity_id)`. La colección conservará compatibilidad
de lectura para el caso histórico `default` (`store["task-1"]`), pero todas
las operaciones del runtime que resuelven un ID de ruta usarán el
`organization_id` explícito o rechazarán una búsqueda ambigua.

Se aplicará a proyectos, requisitos, fases, propuestas, tareas, resultados,
candidatos de memoria y promociones. Las listas continuarán devolviendo solo
valores, por lo que no cambia el formato de las respuestas existentes.

`AgentResult` incorporará `organization_id` con valor por defecto `default`.
El campo permite transportar el namespace del resultado hasta el runtime y
la coordinación sin incluir credenciales ni modificar la forma de las URLs.
El API rellenará/validará ese campo con `X-Organization-ID` cuando el contexto
de tenant esté activo.

## Propagación del contexto

- `TaskDispatcher` resolverá la tarea con `(organization_id, task_id)`.
- Los métodos `get_task`, `get_result`, `get_project`, `get_requirement`,
  `get_plan_proposal`, `task_timeline` y `phase_timeline` aceptarán un
  `organization_id` opcional. Si no se entrega y hay más de una coincidencia,
  devolverán un error de ambigüedad en vez de escoger arbitrariamente.
- Las operaciones de aprobación, cancelación, reintento y registro de logs
  recibirán el namespace derivado del objeto cargado.
- Los endpoints con IDs en la ruta pasarán la organización del request antes
  de validar la autorización. Las URLs permanecen compatibles.
- `InMemoryCoordination` y `AgentResult` usarán la misma clave namespace-aware.
  El adaptador CCCC seguirá enviando el contrato JSON sin conocer la
  implementación del store.

## Compatibilidad y seguridad

Los consumidores locales que trabajan únicamente con `organization_id=default`
conservarán sus llamadas actuales. En modo multi-tenant, omitir la
organización para un ID repetido será un error controlado, no una selección
silenciosa. No se agregan archivos de configuración, secretos, tokens ni
credenciales.

Los filtros de listados, overview y timelines mantendrán el filtrado por
organización/proyecto. La corrección de las colecciones en memoria evita que
un objeto de otra organización sea visible antes de esos filtros; la
autorización seguirá derivándose del `RequestContext`, nunca de un
`organization_id` arbitrario del body.

## Pruebas de aceptación

- Dos organizaciones pueden registrar el mismo `project_id` y conservar
  configuraciones diferentes.
- Dos organizaciones pueden registrar el mismo `task_id` y despachar solo la
  tarea del namespace solicitado.
- Resultados con el mismo `task_id` quedan separados por organización.
- Un lookup sin organización con IDs duplicados falla con ambigüedad.
- Los endpoints tenant-aware no permiten leer, aprobar, cancelar, reintentar o
  registrar resultados de otra organización.
- Las dependencias de tareas y fases se resuelven dentro de su namespace.
- Las pruebas existentes de `default`, SQLite, leases, API y MCP continúan
  pasando.

## Fuera de alcance

Este corte no cambia la clave primaria de las tablas PostgreSQL, no introduce
GraphQL, no rediseña la identidad del gateway y no agrega un scheduler global.
La migración de datos históricos no es necesaria porque el almacenamiento
duradero ya conserva organización; solo se corrigen los índices en memoria y
la propagación del contexto.
