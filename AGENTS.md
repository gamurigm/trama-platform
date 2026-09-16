# Contexto de TRAMA

TRAMA es una plataforma Python multi-proyecto. La API es la fuente de estado
para proyectos, tareas, resultados y candidatos de memoria.

## Kubernetes y WSL

- Para este proyecto, las tareas de Kubernetes se ejecutan mediante WSL.
- Esta regla aplica únicamente a `trama-platform`; no modifica las prácticas
  de otros proyectos.
- Antes de usar Kubernetes, verificar desde WSL que estén disponibles los
  comandos y el contexto necesarios (`kubectl`, `helm` y el runtime local o
  clúster configurado).
- No instalar ni cambiar herramientas globales de Windows para Kubernetes sin
  autorización explícita.


## Gateway Go y modo distribuido

- El módulo Go vive en `gateway/`; ejecutar sus pruebas desde ese directorio.
- La admisión durable usa PostgreSQL, el outbox publica a NATS JetStream y
  Redis comparte el rate limit entre réplicas.
- Python conserva la propiedad de CCCC, Hermes, Colibri, agentes locales,
  memoria contextual y conocimiento canónico.
- El consumidor Python debe hacer `ack` de `task.admitted.v1` únicamente
  después de persistir y entregar la tarea al coordinador.
- Para desarrollo integrado usar `deploy/docker-compose.gateway.yml`; para
  Kubernetes usar el chart Helm y un Secret existente, sin versionar URLs o
  credenciales sensibles.

## Límites de Hermes

- Usar el servidor MCP `trama` solamente desde el perfil local del repositorio.
- Mantener aprobaciones manuales; no activar YOLO ni automatizaciones desatendidas.
- Enviar tareas con `organization_id`, `project_id`, repositorio, worktree y criterios de aceptación explícitos.
- Capturar memoria solo con evidencia verificable. Una captura no es conocimiento canónico.
- No exponer ni leer `.env`, credenciales, claves, tokens o archivos de otros proyectos.
- La promoción de conocimiento requiere revisión humana y no es una herramienta MCP.

## Observabilidad y planificación

- La IA master solo puede proponer planes; la aprobación humana es obligatoria
  antes de entregar fases o tareas a CCCC.
- Conservar el linaje `requirement_id` → `phase_id` → `task_id` y un
  `correlation_id` común para cada propuesta.
- Separar eventos de transición (`OperationEvent`) de mensajes de ejecución
  (`TaskLog`); registrar handoffs, reintentos, bloqueadores y resultados.
- Redactar tokens, cookies, claves, credenciales y contenido de `.env` antes de
  persistir o mostrar logs. No copiar secretos a Semantica ni Utopia.
- Para inspeccionar una ejecución usar `/v1/tasks/{id}/timeline`,
  `/v1/phases/{id}/timeline`, `/v1/logs` y `/v1/plans/{id}` o la TUI (`Enter`
  abre el timeline, `Esc` vuelve).
- Las fases sin dependencias pueden ejecutarse en paralelo; una fase o tarea
  bloqueada debe permanecer visible con su dependencia, agente y último log.

## Cambios

Conservar los contratos versionados y los límites por organización/proyecto.
Actualizar pruebas y esquemas cuando cambie una interfaz pública. Mantener la
API ligada a `127.0.0.1` durante la fase local.
