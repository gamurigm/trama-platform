# Integraciones nativas de IA para TRAMA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Conectar Hermes con TRAMA, Semantica y Utopia mediante sus transportes nativos y dejar Ollama/Qwen3 como perfil de tool-calling y Colibri/OLMoE como perfil local de análisis.

**Architecture:** TRAMA añadirá un catálogo de servicios read-only que inspecciona endpoints y ejecutables sin duplicar estado externo. `HermesAdapter` generará un perfil con un proveedor OpenAI-compatible predeterminado y MCPs opcionales configurados por entorno; la API y el CLI expondrán el mismo inventario.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, httpx, PyYAML, pytest, Ruff, Hermes Agent, Ollama, Colibri, Semantica MCP y Utopia Streamable HTTP MCP.

**Spec:** `docs/superpowers/specs/2026-09-15-native-ai-integrations.md`

## Global Constraints

- `qwen3:8b` servido por Ollama es el modelo operativo predeterminado de Hermes.
- `OLMoE-1B-7B-0125-Instruct` servido por Colibri queda como perfil local de conversación y análisis.
- TRAMA conserva la fuente de verdad de proyectos, tareas, resultados, eventos y promoción.
- Todos los defaults de red son loopback.
- El estado no imprime valores de variables terminadas en `_TOKEN`, `_KEY`, `_SECRET` ni cabeceras.
- Las aprobaciones Hermes siguen en `manual` y los modos `cron`, `single_query` y `unattended` siguen en `deny`.
- Semantica y Utopia se exponen con sus herramientas nativas; TRAMA no las convierte en operaciones de escritura implícitas.
- Ejecutar pruebas con `\.venv\Scripts\python.exe -m pytest` y Ruff con `\.venv\Scripts\python.exe -m ruff check .`.

---

### Task 1: Catálogo local de servicios y configuración tipada

**Files:**
- Create: `src/trama_platform/services.py`
- Modify: `src/trama_platform/settings.py`
- Modify: `.env.example`
- Test: `tests/test_services.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- `ServiceStatus` es un `TypedDict` o estructura serializable con `id`, `status`, `kind`, `endpoint`/`executable`, `model` opcional y `message`.
- `collect_service_status(settings: TramaSettings) -> dict[str, object]` devuelve `{"status": ..., "services": [...]}` sin secretos.
- `TramaSettings.from_env()` añade los valores exactos de la sección Contratos de la spec.

- [ ] **Step 1: Write the failing tests**

Añadir pruebas para que `from_env()` lea URL/modelo/flags; `collect_service_status()` marque un servicio HTTP como `ready` con un servidor local de prueba; marque Ollama/Colibri como `unavailable` sin lanzar excepción; y nunca incluya `UTOPIA_API_TOKEN`, `Authorization` o un campo de cabecera en el JSON resultante.

- [ ] **Step 2: Run tests to verify they fail**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_services.py tests/test_settings.py -q`

Expected: FAIL porque no existe el catálogo ni los campos de configuración.

- [ ] **Step 3: Write minimal implementation**

Crear dataclasses pequeñas para especificaciones y resultados; usar `httpx.Client(timeout=2)` solo para GET de health/listado; capturar `HTTPError`, `OSError` y timeout como estados serializables; detectar ejecutables con `shutil.which`; y omitir Semantica cuando `TRAMA_SEMANTICA_ENABLED` sea falso. No leer `.env`, tokens ni archivos externos.

- [ ] **Step 4: Run tests to verify they pass**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_services.py tests/test_settings.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/trama_platform/services.py src/trama_platform/settings.py .env.example tests/test_services.py tests/test_settings.py
git commit -m "feat: add local native service catalog"
```

### Task 2: Perfil Hermes con Ollama, Colibri y MCPs nativos

**Files:**
- Modify: `src/trama_platform/hermes.py`
- Modify: `src/trama_platform/settings.py`
- Modify: `tests/test_hermes.py`

**Interfaces:**
- `HermesAdapter.render_config(api_url: str, *, settings: TramaSettings | None = None, include_native_services: bool = False) -> dict[str, Any]` conserva la llamada simple existente.
- `HermesAdapter.write_config(path, api_url, *, settings=None, include_native_services=False) -> Path` conserva la llamada simple existente.
- El perfil predeterminado usa `model.default=qwen3:8b`, `model.provider=custom`, `model.base_url=http://127.0.0.1:11434/v1`, `model.api_key=local` y un `custom_providers` seleccionable para Colibri/OLMoE.

- [ ] **Step 1: Write the failing tests**

Añadir una prueba que invoque `render_config(..., settings=..., include_native_services=True)` y compruebe el modelo Qwen3, los dos proveedores locales, `trama`, Semantica `stdio` con el ejecutable configurado y Utopia `streamable-http` con la URL configurada. Comprobar que la configuración no contiene un token ni habilita YOLO.

- [ ] **Step 2: Run test to verify it fails**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_hermes.py -q`

Expected: FAIL porque el adaptador solo conoce el MCP `trama`.

- [ ] **Step 3: Write minimal implementation**

Mantener `TRAMA_TOOLS` sin cambios; construir `model` y `custom_providers` con URLs `/v1`; añadir `semantica` solo si el flag está activo y `utopia` solo si `utopia_mcp_url` no está vacío; representar el token Utopia como `${UTOPIA_API_TOKEN}` únicamente en la plantilla/configuración local, sin resolverlo ni imprimirlo desde TRAMA.

- [ ] **Step 4: Run test to verify it passes**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_hermes.py tests/test_project.py -q`

Expected: PASS y compatibilidad con las llamadas existentes de `write_config(path, api_url)`.

- [ ] **Step 5: Commit**

```powershell
git add src/trama_platform/hermes.py src/trama_platform/settings.py tests/test_hermes.py
git commit -m "feat: configure hermes native model and mcp profiles"
```

### Task 3: CLI/API gateway y plantilla operativa

**Files:**
- Modify: `src/trama_platform/cli.py`
- Modify: `src/trama_platform/api.py`
- Create: `examples/hermes-native-config.yaml`
- Modify: `README.md`
- Modify: `docs/ARQUITECTURA.md`
- Test: `tests/test_cli_gateway.py`
- Test: `tests/test_api.py`
- Test: `tests/test_project.py`

**Interfaces:**
- `GET /v1/services` devuelve el mismo shape que `collect_service_status(TramaSettings.from_env())`.
- `trama services status [--json]` imprime el catálogo sin fallar porque un servicio opcional esté apagado.
- `trama hermes configure --all` escribe el perfil completo usando `TramaSettings`.
- `examples/hermes-native-config.yaml` es YAML válido y no contiene secretos reales.

- [ ] **Step 1: Write the failing tests**

Probar el endpoint `/v1/services`, el subcomando `services status --json` con un catálogo sustituido por uno controlado, y `hermes configure --all` con un fake que reciba `include_native_services=True`. Validar la plantilla nueva, sus tres servidores MCP y `model.default`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_cli_gateway.py tests/test_api.py tests/test_project.py -q`

Expected: FAIL porque no existe el endpoint/comando, el flag `--all` ni la plantilla.

- [ ] **Step 3: Write minimal implementation**

Conectar el endpoint al catálogo read-only; añadir `services status`; ampliar `hermes configure` con `--all`; preservar la salida/firmas anteriores para los comandos existentes; y documentar instalación separada de cada servicio, orden de arranque y la diferencia entre Qwen3 tool-calling y OLMoE análisis.

- [ ] **Step 4: Run tests to verify they pass**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_cli_gateway.py tests/test_api.py tests/test_project.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/trama_platform/cli.py src/trama_platform/api.py examples/hermes-native-config.yaml README.md docs/ARQUITECTURA.md tests
git commit -m "feat: expose native integrations through cli gateway"
```

### Task 4: Instalación local supervisada y smoke checks

**Files:**
- Modify: `README.md` only if los comandos verificados difieren de la documentación.
- Do not add: clones, modelos, tokens, bases de datos o `.env` al repositorio.

- [ ] **Step 1: Verify host prerequisites**

Ejecutar `Get-Command ollama,docker,hermes,uv,git`; comprobar `docker info`; y registrar por separado lo instalado, lo ausente y lo que requiere una acción manual.

- [ ] **Step 2: Install/start the tool-calling path**

Si Ollama no existe, instalarlo con el instalador soportado del host; iniciar el servicio; ejecutar `ollama pull qwen3:8b`; y verificar `GET http://127.0.0.1:11434/api/tags` y una llamada mínima con tools sin exponer la respuesta como secreto.

- [ ] **Step 3: Prepare Colibri/OLMoE**

Obtener el release o checkout de Colibri fuera del repo, construir/validar `coli`, convertir `allenai/OLMoE-1B-7B-0125-Instruct` con `c/tools/convert_olmoe_merged.py` en un directorio de datos externo y dejar el endpoint en `127.0.0.1:8020`; no descargar modelos de cientos de GB ni iniciar el perfil como tool-calling.

- [ ] **Step 4: Prepare Semantica y Utopia**

Instalar Semantica en un entorno aislado y validar `python -m semantica.mcp_server`. Si Docker Desktop está disponible, clonar Utopia fuera del repo y usar su compose documentado; comprobar la UI/health local. Detenerse antes de crear credenciales o KB IDs: esa creación requiere la decisión del usuario.

- [ ] **Step 5: Generate and verify Hermes profile**

Con la API local arriba, ejecutar `trama services status --json`, `trama hermes configure --all --json`, validar el YAML generado y ejecutar `trama hermes check --json`. Verificar que el perfil tiene los tres MCP solo cuando estén configurados y que el default sigue siendo Qwen3.

- [ ] **Step 6: Commit documentation-only corrections**

```powershell
git add README.md
git commit -m "docs: record native integration smoke checks"
```

### Task 5: Verificación completa y revisión de entrega

**Files:**
- Modify: only files implicated by a failing verification.

- [ ] **Step 1: Run quality gates**

```powershell
\.venv\Scripts\python.exe -m trama_platform export-schemas contracts
\.venv\Scripts\python.exe -m pytest
\.venv\Scripts\python.exe -m ruff check .
git diff --check
```

- [ ] **Step 2: Inspect the generated profile and public status**

Ejecutar el CLI con `--json`, revisar que no aparezcan tokens/cabeceras y confirmar que servicios apagados producen `unavailable`/`disabled`, no una excepción.

- [ ] **Step 3: Review worktree state**

Ejecutar `git status --short`, `git log --oneline -8` y `git diff --stat main...HEAD`. No agregar `AGENTS.md`, `refact1.md`, `.env`, clones, modelos ni artefactos externos del checkout principal.
