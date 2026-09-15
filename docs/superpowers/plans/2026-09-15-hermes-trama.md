# Hermes local para TRAMA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Conectar Hermes Agent localmente a TRAMA mediante un MCP `stdio`, reforzar el aislamiento de organizaciones/proyectos y mantener la API HTTP como fuente única de estado.

**Architecture:** `trama mcp` será un servidor MCP sin estado propio que usa `TramaApiClient` contra la API local. El runtime validará ownership por organización/proyecto antes de delegar a los puertos existentes. Hermes recibirá solo las herramientas MCP declaradas mediante una plantilla de configuración.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, MCP Python SDK 2.x, httpx, pytest, Ruff, uv.

**Spec:** `docs/superpowers/specs/2026-09-15-hermes-trama-design.md`

## Global Constraints

- Hermes corre localmente, de forma interactiva y supervisada.
- MCP usa `stdio`; no se añade gateway, cron, mensajería ni ejecución remota.
- La API HTTP de TRAMA es la fuente de estado; el proceso MCP no crea estado de negocio paralelo.
- El MCP no expone promoción canónica.
- Los secretos no aparecen en manifiestos, contratos, plantillas ni logs.
- Las escrituras quedan limitadas a contratos y operaciones explícitas de TRAMA.
- Ejecutar pruebas con `.\.venv\Scripts\python.exe -m pytest` y Ruff con `.\.venv\Scripts\python.exe -m ruff check .`.

---

### Task 1: Aislamiento de dominio y configuración tipada

**Files:**
- Create: `src/trama_platform/settings.py`
- Modify: `src/trama_platform/namespaces.py`
- Modify: `src/trama_platform/runtime.py`
- Modify: `src/trama_platform/ports.py`
- Modify: `src/trama_platform/api.py`
- Modify: `.env.example`
- Test: `tests/test_runtime.py`
- Test: `tests/test_contracts.py`
- Test: `tests/test_api.py`

**Interfaces:**
- `TramaSettings.from_env() -> TramaSettings` devuelve host, puerto, URL, ejecutable CCCC y timeout.
- `ContextMemoryPort.search(organization_id: str, project_id: str, query: str) -> Sequence[MemoryCandidate]` aplica ambos namespaces.
- `TramaRuntime.search_memory(organization_id: str, project_id: str, query: str) -> Sequence[MemoryCandidate]` expone la búsqueda validada.
- `POST /v1/memory/search` acepta `{organization_id, project_id, query}` y devuelve candidatos visibles.

- [ ] **Step 1: Write the failing tests**

Añadir pruebas que demuestren que una tarea o candidato con organización distinta al manifiesto se rechaza, que una memoria compartida no cruza organizaciones y que la API expone la búsqueda con el namespace correcto.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_runtime.py tests/test_api.py -q`

Expected: FAIL porque el runtime todavía no valida la organización en todas las operaciones y no existe `POST /v1/memory/search`.

- [ ] **Step 3: Write minimal implementation**

Crear `TramaSettings` con parseo estricto de enteros y valores por defecto; cambiar `can_read_candidate` y `can_promote` para exigir organización y proyecto; guardar las tareas aceptadas en `TramaRuntime`; validar el manifiesto al enviar tareas, capturar memoria y promover; añadir el modelo de búsqueda y el endpoint.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_runtime.py tests/test_api.py tests/test_contracts.py -q`

Expected: PASS for the focused suite.

- [ ] **Step 5: Commit**

```powershell
git add src tests .env.example
git commit -m "refactor: enforce project ownership boundaries"
```

### Task 2: Cliente HTTP y servidor MCP `stdio`

**Files:**
- Create: `src/trama_platform/mcp_server.py`
- Modify: `src/trama_platform/cli.py`
- Modify: `src/trama_platform/__init__.py`
- Modify: `pyproject.toml`
- Test: `tests/test_mcp.py`

**Interfaces:**
- `TramaApiClient(base_url: str)` encapsula las llamadas HTTP a proyectos, búsqueda, tareas, resultados y memoria.
- `create_mcp_server(client: TramaApiClient) -> MCPServer` devuelve un servidor con cinco herramientas declaradas.
- `run_mcp(api_url: str) -> None` inicia `MCPServer.run(transport="stdio")`.
- `trama mcp --api-url URL` inicia el proceso MCP.

- [ ] **Step 1: Write the failing tests**

Crear pruebas que llamen al cliente HTTP contra una aplicación FastAPI de prueba y una prueba async que use `mcp.Client` contra el servidor en memoria para verificar los nombres y respuestas de las cinco herramientas.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_mcp.py -q`

Expected: FAIL porque no existe el cliente MCP ni el subcomando `mcp`.

- [ ] **Step 3: Write minimal implementation**

Añadir `mcp>=2,<3` y `httpx>=0.28,<1` como dependencias de ejecución. Implementar el cliente con `httpx.Client`, convertir modelos a JSON antes de enviarlos, transformar errores HTTP a una excepción de integración y construir el servidor con el SDK oficial. El bloque de ejecución debe estar bajo `if __name__ == "__main__"` y no usar `print()` en stdout.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_mcp.py -q`

Expected: PASS, incluyendo la prueba de llamada en memoria del servidor MCP.

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml src tests
git commit -m "feat: expose trama tools through local mcp"
```

### Task 3: Perfil Hermes, contexto del proyecto y documentación operativa

**Files:**
- Create: `AGENTS.md`
- Create: `examples/hermes-config.yaml`
- Modify: `README.md`
- Modify: `docs/ARQUITECTURA.md`
- Modify: `contracts/README.md`
- Test: `tests/test_project.py`

**Interfaces:**
- `examples/hermes-config.yaml` configura un servidor `trama` por `stdio`, filtra las cinco herramientas y mantiene aprobaciones manuales.
- `AGENTS.md` documenta los límites de Hermes y los comandos de verificación reales del proyecto.
- La documentación define el arranque de la API y del MCP en terminales separadas.

- [ ] **Step 1: Write the failing test**

Añadir una prueba que valide que la plantilla de Hermes es YAML válido, referencia `trama mcp`, usa `stdio`, no activa YOLO y solo permite los nombres de herramientas declarados.

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_project.py -q`

Expected: FAIL porque la plantilla y `AGENTS.md` aún no existen.

- [ ] **Step 3: Write minimal implementation**

Crear la plantilla sin claves ni rutas de credenciales, explicar `TRAMA_API_URL`, el arranque de `trama api` y `trama mcp`, y documentar que la promoción requiere una llamada supervisada fuera del conjunto MCP.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_project.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add AGENTS.md examples README.md docs contracts tests
git commit -m "docs: configure hermes project profile"
```

### Task 4: Verificación completa y entrega del worktree

**Files:**
- Modify: any files required by verification findings only

- [ ] **Step 1: Export schemas and run quality checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m trama_platform export-schemas contracts
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
git diff --check
```

Expected: all commands exit with code 0; generated schemas are unchanged unless the new search contract is intentionally public.

- [ ] **Step 2: Run an MCP smoke check**

Start the API in one terminal with `.\.venv\Scripts\python.exe -m trama_platform api --host 127.0.0.1 --port 8090`, then start `.\.venv\Scripts\python.exe -m trama_platform mcp --api-url http://127.0.0.1:8090` and inspect the tool list through the MCP Inspector or official client. Stop both processes after the check.

- [ ] **Step 3: Review worktree state**

Run `git status --short`, `git log --oneline -5`, and `git diff --stat feat/multi-project-platform...HEAD` from the worktree. Report the branch, commits, tests, lint, generated artifacts and any limitations without claiming Hermes itself is installed unless it was verified.
