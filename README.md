![TRAMA — coordinación de agentes, memoria y conocimiento](docs/banner-trama.png)

# TRAMA

TRAMA es un entorno independiente para coordinar agentes y conectar varios
proyectos con memoria contextual, conocimiento canónico, herramientas MCP y
proveedores de modelos.

El repositorio no contiene la lógica de los proyectos conectados. Cada proyecto
se registra con un manifiesto y conserva sus propias dependencias, pruebas y
reglas de seguridad.

## Componentes

- **Gateway Go:** admisión durable, idempotencia, cuotas y entrega de eventos.
- **Orquestador TRAMA:** planifica, delega y supervisa.
- **CCCC:** coordina tareas, actores, estados, mensajes y handoffs.
- **Agentes:** Codex, OpenCode y otros ejecutores especializados.
- **Hermes Agent:** interfaz local supervisada conectada mediante MCP `stdio`.
- **Colibri Inference:** proveedor local de modelos para Hermes y agentes Python.
- **Memoria de trabajo del agente:** contexto privado y efímero de cada sesión.
- **Semantica:** memoria contextual y episódica mediante un adaptador externo.
- **Utopia:** conocimiento persistente y canónico mediante un adaptador externo.
- **MCP:** conexión controlada con herramientas y servicios.
- **Model Gateway:** selección de modelos, límites y proveedores.

## Arquitectura de alto nivel

![Arquitectura de alto nivel de TRAMA](docs/arquitectura-trama.svg)

La imagen muestra la frontera principal: Hermes interactúa con TRAMA por MCP,
TRAMA mantiene las políticas y la evidencia, CCCC coordina actores, y los
proyectos conectados conservan su propio código y ciclo de vida.

## Entorno propio

TRAMA utiliza su propio entorno Python. No reutiliza el `.venv` del dashboard.

```powershell
uv venv --python 3.12 .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Ejecutar pruebas:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## CLI gateway

El CLI es la interfaz operativa principal de TRAMA. La API local conserva el
estado y la TUI ofrece una vista interactiva de la misma información; no existe
un dashboard web paralelo.

```powershell
trama up
trama status --json
trama doctor --json
trama project list --json
trama task list --json
trama task result task-1 --json
trama audit list --json
trama knowledge validate candidate-1 --organization default --project demo --reviewer human --json
trama tui
```

### TUI TypeScript

Para iniciar la TUI TypeScript, levanta primero la API local y, desde la raíz
del repositorio, ejecuta:

```powershell
.\.venv\Scripts\python.exe -m trama_platform api --host 127.0.0.1 --port 8090
bun install --cwd tui
bun run --cwd tui start
```

La TUI usa `TRAMA_API_URL` para seleccionar la API; si no se define, utiliza
`http://127.0.0.1:8090`. `trama tui` permanece disponible como fallback de la
TUI Python.

La TUI TypeScript es un cockpit operativo OpenTUI. Su dashboard reúne Projects,
Tasks, Agents, Queues, Workers, Events, Memory y System health sin duplicar el
estado de la API. La paleta de comandos se abre con `/`; también acepta `↑/↓`
o `j/k` y números `1-9` para elegir una vista.

Atajos principales:

| Tecla | Acción |
| --- | --- |
| `j/k`, `↑/↓` | mover selección |
| `Enter` | abrir detalle o elegir comando |
| `/` | abrir command palette |
| `p` | cambiar contexto de proyecto |
| `f` | iniciar filtro |
| `r` | actualizar |
| `a` | aprobar tarea seleccionada, con confirmación |
| `x` | cancelar tarea seleccionada, con confirmación |
| `y` | reintentar tarea seleccionada, con confirmación |
| `Esc` | cerrar overlay o cancelar |
| `q` | salir |

Si una actualización falla después de cargar datos válidos, la TUI conserva la
última proyección y muestra `Datos obsoletos`; `r` permite reintentar. Las
acciones destructivas no se envían hasta confirmar con `y` o `Enter`.

El estado del control plane se guarda en `TRAMA_STATE_DIR/trama.db`. `trama
down` solo detiene el proceso API cuyo PID fue registrado por `trama up`. En
`TRAMA_ENV=prod`, `TRAMA_DATABASE_URL` es obligatorio y el backend pasa a
PostgreSQL; SQLite no se usa para producción.
En `TRAMA_ENV=prod`, `TRAMA_DATABASE_URL` es obligatorio y el backend pasa a
PostgreSQL; SQLite no se usa para producción. `trama down` solo detiene el
proceso API cuyo PID fue registrado por `trama up`.
La coordinación usa memoria local por defecto para pruebas; para despachar
tareas a CCCC, inicia su daemon y activa el backend explícitamente antes de
levantar TRAMA:

```powershell
cccc daemon start
$env:TRAMA_COORDINATION_BACKEND = "cccc"
trama up --json
trama status --json
```

El estado debe mostrar `coordination: CcccCliAdapter`. El backend CCCC usa
`cccc tracked-send` para entregar tareas y `cccc send` para devolver resultados.
Hermes se integra como proceso externo supervisado:

```powershell
trama hermes check --json
trama hermes configure
trama hermes run
```

La TUI de TRAMA opera proyectos, tareas, agentes y evidencia;
la conversación, los modelos, skills y memoria propia de Hermes siguen siendo
responsabilidad de Hermes.

### Observabilidad de planes y tareas

La IA master propone un `PlanProposal` versionado a partir del requisito y su
contexto. Hermes lo presenta para aprobación humana; solo después TRAMA marca
las fases y tareas como disponibles para CCCC. La propuesta, la aprobación, los
handoffs y los resultados quedan unidos por `correlation_id`.

Los cambios de estado se consultan como eventos y los mensajes de ejecución
como logs saneados:

```powershell
Invoke-RestMethod http://127.0.0.1:8090/v1/plans/plan-1
Invoke-RestMethod http://127.0.0.1:8090/v1/tasks/task-1/timeline
Invoke-RestMethod "http://127.0.0.1:8090/v1/logs?project_id=demo&limit=50"
```

Los logs redactan tokens, cookies, claves y credenciales antes de persistirse.
El almacenamiento SQLite permite filtrar por organización, proyecto, requisito,
fase, tarea y nivel, y podar filas antiguas por proyecto. La TUI muestra la
misma información como carriles de fases paralelas, cola de aprobación, cola
CCCC, actividad reciente y timeline de la tarea seleccionada (`Enter`; `Esc`
para volver).

Los resultados quedan consultables con `GET /v1/tasks/{task_id}/result`. Los
candidatos de memoria permanecen en estado `candidate` hasta una revisión
humana explícita mediante `POST /v1/memory/candidates/{candidate_id}/validate`
o `/reject`, siempre con `organization_id` y `project_id`; solo los candidatos
validados pueden promoverse a conocimiento canónico.

### Planificación por requisitos

Los requisitos se registran desde la TUI o por las herramientas MCP de Hermes.
Hermes propone fases y tareas especializadas; las tareas derivadas quedan en
`planned` hasta recibir aprobación humana. Las fases pueden ejecutarse en
paralelo cuando no tienen `depends_on`; las tareas pueden declarar sus propias
dependencias. La aprobación habilita el despacho a CCCC y la TUI muestra una
vista compacta con barras de progreso por fase, cola CCCC, origen de la tarea,
agente asignado y estados bloqueados/completados.

Iniciar la API local:

```powershell
.\.venv\Scripts\python.exe -m trama_platform api --host 127.0.0.1 --port 8090
```

En otra terminal, desde la raíz del repositorio, iniciar el servidor MCP que
Hermes consumirá:

```powershell
.\.venv\Scripts\python.exe -m trama_platform mcp --api-url http://127.0.0.1:8090
```

En un despliegue distribuido, añade `--gateway-url http://127.0.0.1:8080` (y
`TRAMA_GATEWAY_TOKEN` si el gateway exige autenticación). Todas las llamadas
MCP pasan por el gateway; este conserva la admisión idempotente de tareas y
reenvía el resto del API al control plane Python privado.

La plantilla [examples/hermes-config.yaml](examples/hermes-config.yaml) se
puede copiar a `%USERPROFILE%\.hermes\config.yaml`. Hermes debe ejecutarse
desde la raíz del repositorio para que `uv` resuelva este proyecto. El perfil
habilita solo las herramientas TRAMA y mantiene las aprobaciones manuales.

También puede iniciarse con Docker:

```powershell
docker compose -f deploy/docker-compose.yml up --build
```

El entorno de gateway distribuido para desarrollo levanta PostgreSQL, NATS
JetStream, Redis, el gateway Go, el outbox y el consumidor Python. El control
plane y los agentes siguen siendo Python; Colibri y Hermes nunca quedan
expuestos por el gateway público:

```powershell
docker compose -f deploy/docker-compose.gateway.yml up --build
```

Si una red corporativa intercepta TLS y Docker muestra `UnknownIssuer`, usar
el modo explícito de contingencia solo en esa red:

```powershell
$env:TRAMA_PIP_INSECURE = "1"
docker compose -f deploy/docker-compose.yml up --build
Remove-Item Env:TRAMA_PIP_INSECURE
```

El valor predeterminado mantiene la validación TLS normal.

El control plane local persiste proyectos, tareas, resultados, candidatos,
promociones y eventos en SQLite. El dispatcher local mantiene una cola acotada
dentro del proceso: admite hasta `TRAMA_QUEUE_CAPACITY + TRAMA_MAX_CONCURRENCY` tareas,
ejecuta como máximo `TRAMA_MAX_CONCURRENCY` despachos simultáneos y devuelve
HTTP 429 con código `queue_full` cuando no puede admitir otra tarea. Esta cola
no es un broker compartido entre procesos; configura sus límites con
`TRAMA_QUEUE_CAPACITY`, `TRAMA_MAX_CONCURRENCY` y
`TRAMA_DISPATCH_TIMEOUT_SECONDS`. Los puertos de contexto y conocimiento usan
implementaciones locales por defecto. Semantica se conecta nativamente como
`AgentContext` de Python; Utopia se conecta por el endpoint MCP HTTP de una base
 de conocimiento. Ambas integraciones son opcionales.

Los identificadores de proyectos, requisitos, fases, propuestas, tareas,
resultados y candidatos no son globales: se resuelven por
`(organization_id, entity_id)`. En producción, la API toma la organización y
el proyecto del `RequestContext` (`X-Organization-ID` y `X-Project-ID`) y no
permite usar un ID de otra organización. Si un consumidor local omite la
organización, solo se acepta la consulta cuando existe una única coincidencia;
las colisiones devuelven conflicto. El MCP reenvía el mismo contexto mediante
headers y campos de contrato, sin guardar credenciales.

En el modo distribuido, todos los clientes entran por el gateway Go. `POST
/v1/tasks` usa una operación transaccional de PostgreSQL (admisión, proyección
read-your-write y outbox); el resto de `/v1/*` se reenvía al control plane
Python, que también persiste en PostgreSQL. El proceso `trama-outbox` publica
`task.admitted.v1` en NATS JetStream y `trama worker` lo consume con un durable,
`ack_wait`, límite de entregas e inbox deduplicado; el `ack` ocurre después de
que Python persiste y entrega la tarea a CCCC. Redis comparte el rate limit
entre réplicas. Para producción, configura OIDC/JWKS o una cuenta de servicio,
el token interno entre gateway y control plane, y usa el chart Helm de
`deploy/helm/trama-gateway`.

El control plane coordina la ejecución mediante `trama.task_leases`: una fila
por `(organization_id, task_id)` conserva owner, token, intento y
`expires_at`. El worker reclama la tarea antes de emitir `task.dispatch` y la
renueva mientras CCCC la procesa; al persistir un `AgentResult` terminal, el
runtime completa el lease. Si el worker cae, otra réplica puede reclamar la
tarea cuando vence el lease, por lo que la semántica es at-least-once y el
coordinador debe tolerar redeliveries. El TTL se configura con
`TRAMA_TASK_LEASE_SECONDS` y por defecto es de 60 segundos.

Variables mínimas del control plane distribuido:

```powershell
$env:TRAMA_ENV = "prod"
$env:TRAMA_DATABASE_URL = "postgresql://..."
$env:TRAMA_INTERNAL_SERVICE_TOKEN = "<secret-del-gateway>"
$env:TRAMA_REQUIRE_TENANT_CONTEXT = "true"
# Opcional: TTL de ownership distribuido.
$env:TRAMA_TASK_LEASE_SECONDS = "60"
```

El API Python expone `/livez` y `/readyz` para probes. El endpoint Python no
debe publicarse fuera de la red interna; `/v1` público pertenece al gateway.

Para usar Semantica en el worker Python, instala la integración y configura un
directorio absoluto de persistencia:

```powershell
uv sync --extra integrations
$env:TRAMA_SEMANTICA_KG_PATH = "C:\data\trama\semantica-context"
```

Semantica recomienda `AgentContext` nativo para código Python. Su servidor MCP
`semantica-mcp` es `stdio` local para clientes MCP y no es un servicio REST;
TRAMA no intenta conectarse a él por URL.

Para usar Utopia, inicia su aplicación y crea una PAT con permiso `read` o
`write` según corresponda. Configura la URL del servidor, el ID de la base y el
token:

```powershell
$env:TRAMA_UTOPIA_URL = "http://127.0.0.1:1516"
$env:TRAMA_UTOPIA_KB_ID = "<knowledge-base-uuid>"
$env:TRAMA_UTOPIA_TOKEN = "utp_pat_..."
```

Utopia se consulta con `search_chunks` y registra propuestas con `remember` en
`/api/v1/kbs/{kb_id}/mcp`. `remember` deja los hechos en la cola de revisión;
no significa que el grafo canónico haya sido modificado. Si no se configura la
base externa, TRAMA conserva las implementaciones locales.
Usa HTTPS para servicios remotos.

## Agentes locales y Colibri

El bridge local de agentes se ejecuta en Python y es el único componente que
inicia Hermes o usa Colibri en el equipo del agente. Colibri se consume como
proveedor OpenAI-compatible local; una instancia atiende una generación a la
vez, por lo que su capacidad se registra como un slot y no se confunde con la
capacidad del gateway. Hermes mantiene el modo interactivo supervisado y el
modo worker requiere activación explícita y sigue respetando aprobaciones
manuales.

El worker Python distribuido se inicia con:

```powershell
trama worker
```

El modo worker local de Hermes continúa siendo opt-in; consumir eventos NATS no
concede por sí solo permiso para ejecutar acciones locales.

El proceso MCP no mantiene estado de negocio propio: reenvía sus operaciones a
la API HTTP local. Reiniciar la API conserva el estado persistido en SQLite.

## Registrar un proyecto

```powershell
.\.venv\Scripts\python.exe -m trama_platform validate-project examples\generador-diccionario.project.yaml
```

El manifiesto de cada proyecto define su repositorio, capacidades, comandos y
políticas. No contiene credenciales.

## Contratos

Los modelos Pydantic de `src/trama_platform/contracts.py` son la fuente de
validación. Los esquemas JSON se pueden exportar con:

```powershell
.\.venv\Scripts\python.exe -m trama_platform export-schemas contracts
```

## Alcance inicial

Esta primera base implementa contratos, namespaces, registro de proyectos,
runtime local, API y adaptador CCCC. Semantica nativa, Utopia MCP, MCP y Model
Gateway quedan desacoplados detrás de puertos explícitos; el puente MCP para
Hermes reenvía las operaciones a la API. Ningún fallo de un adaptador
externo debe impedir que un proyecto ejecute sus pruebas o genere sus propios
artefactos.
