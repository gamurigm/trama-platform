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
- **Semantica:** memoria contextual y episódica expuesta a Hermes por MCP `stdio`.
- **Utopia:** conocimiento persistente expuesto a Hermes por MCP HTTP, con aprobación
  propia para los cambios.
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
trama services status --json
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
trama hermes configure --all
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
Para activar también los servicios nativos usa `trama hermes configure --all`;
el resultado agrega TRAMA y solo los servicios nativos configurados: Semantica
cuando `TRAMA_SEMANTICA_ENABLED` está activo y Utopia cuando
`TRAMA_UTOPIA_MCP_URL` tiene una URL. También incluye los proveedores locales de
Ollama y Colibri. La plantilla completa está en
[examples/hermes-native-config.yaml](examples/hermes-native-config.yaml).

## Servicios nativos y orden de arranque

Los servicios externos conservan sus propios entornos y ciclos de vida. TRAMA
solo los consulta y los registra en un catálogo read-only; un servicio apagado
aparece como `unavailable` y no impide operar el control plane.

Instala cada proyecto en su propio directorio/entorno siguiendo su documentación:

1. [Ollama](https://ollama.com/) para el modelo de herramientas:

   ```powershell
   ollama serve
   ollama pull qwen3:8b
   ```

2. [Colibri](https://github.com/JustVugg/colibri) para el modelo local de análisis.
   Inicia su servidor OpenAI-compatible en `http://127.0.0.1:8020` con
   `OLMoE-1B-7B-0125-Instruct` cargado según la guía del checkout de Colibri.

3. [Semantica](https://github.com/semantica-agi/semantica) en un entorno Python
   separado. Por ejemplo:

   ```powershell
   uv venv --python 3.12 .venv-semantica
   uv pip install --python .venv-semantica/Scripts/python.exe "semantica[all]"
   $env:TRAMA_SEMANTICA_ENABLED = "true"
   $env:TRAMA_SEMANTICA_EXECUTABLE = (Resolve-Path .venv-semantica/Scripts/semantica-mcp.exe)
   ```

4. [Utopia](https://github.com/deeplethe/utopia) en su checkout independiente,
   con Docker disponible:

   ```powershell
   docker compose --profile app up -d
   $env:TRAMA_UTOPIA_MCP_URL = "http://127.0.0.1:1516/api/v1/kbs/<kb-id>/mcp"
   $env:UTOPIA_API_TOKEN = "<token-solo-en-la-sesion-local>"
   ```

   El token se mantiene en el entorno que Hermes hereda; no se coloca en YAML,
   commits ni salidas del catálogo.

Después inicia TRAMA en `127.0.0.1:8090`, valida el conjunto y genera el perfil:

```powershell
trama up
trama services status --json
trama hermes configure --all
trama hermes run
```

`GET /v1/services` devuelve el mismo catálogo que `trama services status`.
`qwen3:8b` es el modelo primario porque Ollama documenta tool-calling; OLMoE
se conserva en Colibri para análisis local y no se presenta como modelo de
herramientas nativas. Consulta la [matriz de tool-calling de Colibri](https://github.com/JustVugg/colibri/blob/main/docs/api.md)
antes de cambiar esta selección.

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
`TRAMA_DISPATCH_TIMEOUT_SECONDS`. Los puertos de contexto y conocimiento usan
implementaciones locales por defecto; Semantica y Utopia se conectan como
servidores MCP nativos de Hermes sin convertirlos en dependencias obligatorias
de TRAMA.

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

Esta base implementa contratos, namespaces, registro de proyectos, runtime
local, API, catálogo de servicios, adaptador CCCC y un gateway CLI para Hermes.
Semantica, Utopia, Colibri y Ollama permanecen desacoplados detrás de sus
protocolos nativos; el puente MCP para Hermes reenvía las operaciones de TRAMA.
Ningún fallo de un servicio externo debe impedir que un proyecto ejecute sus
pruebas o genere sus propios artefactos.
