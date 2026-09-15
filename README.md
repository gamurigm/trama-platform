![TRAMA — coordinación de agentes, memoria y conocimiento](docs/banner-trama.png)

# TRAMA

TRAMA es un entorno independiente para coordinar agentes y conectar varios
proyectos con memoria contextual, conocimiento canónico, herramientas MCP y
proveedores de modelos.

El repositorio no contiene la lógica de los proyectos conectados. Cada proyecto
se registra con un manifiesto y conserva sus propias dependencias, pruebas y
reglas de seguridad.

## Componentes

- **Orquestador TRAMA:** planifica, delega y supervisa.
- **CCCC:** coordina tareas, actores, estados, mensajes y handoffs.
- **Agentes:** Codex, OpenCode y otros ejecutores especializados.
- **Hermes Agent:** interfaz local supervisada conectada mediante MCP `stdio`.
- **Colibri:** memoria rápida/local del agente.
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
trama audit list --json
trama tui
```

El estado del control plane se guarda en `TRAMA_STATE_DIR/trama.db`. `trama
down` solo detiene el proceso API cuyo PID fue registrado por `trama up`.
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

Iniciar la API local:

```powershell
.\.venv\Scripts\python.exe -m trama_platform api --host 127.0.0.1 --port 8090
```

En otra terminal, desde la raíz del repositorio, iniciar el servidor MCP que
Hermes consumirá:

```powershell
.\.venv\Scripts\python.exe -m trama_platform mcp --api-url http://127.0.0.1:8090
```

La plantilla [examples/hermes-config.yaml](examples/hermes-config.yaml) se
puede copiar a `%USERPROFILE%\.hermes\config.yaml`. Hermes debe ejecutarse
desde la raíz del repositorio para que `uv` resuelva este proyecto. El perfil
habilita solo las herramientas TRAMA y mantiene las aprobaciones manuales.

También puede iniciarse con Docker:

```powershell
docker compose -f deploy/docker-compose.yml up --build
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
promociones y eventos en SQLite. El dispatcher mantiene una cola acotada dentro
del proceso: admite hasta `TRAMA_QUEUE_CAPACITY + TRAMA_MAX_CONCURRENCY` tareas,
ejecuta como máximo `TRAMA_MAX_CONCURRENCY` despachos simultáneos y devuelve
HTTP 429 con código `queue_full` cuando no puede admitir otra tarea. Esta cola
no es un broker compartido entre procesos; configura sus límites con
`TRAMA_QUEUE_CAPACITY`, `TRAMA_MAX_CONCURRENCY` y
`TRAMA_DISPATCH_TIMEOUT_SECONDS`. Los puertos de contexto y conocimiento todavía
usan implementaciones locales por defecto; Semantica y Utopia se conectarán como
adaptadores externos sin convertirlos en dependencias obligatorias de TRAMA.

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
runtime local, API y adaptador CCCC. Semantica, Utopia, MCP y Model Gateway
quedan desacoplados detrás de puertos explícitos; el puente MCP para Hermes
reenvía las operaciones a la API. Ningún fallo de un adaptador
externo debe impedir que un proyecto ejecute sus pruebas o genere sus propios
artefactos.
