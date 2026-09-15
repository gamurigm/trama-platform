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
- **Colibri:** memoria rápida/local del agente.
- **Semantica:** memoria contextual y episódica mediante un adaptador externo.
- **Utopia:** conocimiento persistente y canónico mediante un adaptador externo.
- **MCP:** conexión controlada con herramientas y servicios.
- **Model Gateway:** selección de modelos, límites y proveedores.

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

Iniciar la API local:

```powershell
.\.venv\Scripts\python.exe -m trama_platform api --host 127.0.0.1 --port 8090
```

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

La API inicial usa almacenamiento en memoria para validar contratos y flujos.
La persistencia productiva se conectará mediante los puertos de memoria y
conocimiento, sin introducir SQLite como dependencia compartida.

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
quedan desacoplados detrás de puertos explícitos. Ningún fallo de un adaptador
externo debe impedir que un proyecto ejecute sus pruebas o genere sus propios
artefactos.
