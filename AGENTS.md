# Contexto de TRAMA

TRAMA es una plataforma Python multi-proyecto. La API es la fuente de estado
para proyectos, tareas, resultados y candidatos de memoria.

## Comandos

- Entorno: `uv venv --python 3.12 .venv` y `uv pip install --system-certs --python .venv/Scripts/python.exe -e ".[dev]"`.
- Pruebas: `.venv/Scripts/python.exe -m pytest`.
- Calidad: `.venv/Scripts/python.exe -m ruff check .`.
- API local: `.venv/Scripts/python.exe -m trama_platform api --host 127.0.0.1 --port 8090`.
- MCP local: `.venv/Scripts/python.exe -m trama_platform mcp --api-url http://127.0.0.1:8090`.

## Límites de Hermes

- Usar el servidor MCP `trama` solamente desde el perfil local del repositorio.
- Mantener aprobaciones manuales; no activar YOLO ni automatizaciones desatendidas.
- Enviar tareas con `organization_id`, `project_id`, repositorio, worktree y criterios de aceptación explícitos.
- Capturar memoria solo con evidencia verificable. Una captura no es conocimiento canónico.
- No exponer ni leer `.env`, credenciales, claves, tokens o archivos de otros proyectos.
- La promoción de conocimiento requiere revisión humana y no es una herramienta MCP.

## Cambios

Conservar los contratos versionados y los límites por organización/proyecto.
Actualizar pruebas y esquemas cuando cambie una interfaz pública. Mantener la
API ligada a `127.0.0.1` durante la fase local.
