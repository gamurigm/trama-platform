# Hermes local para TRAMA

## Objetivo

Conectar Hermes Agent de forma local, interactiva y supervisada a TRAMA sin convertirlo en la fuente de verdad de tareas, evidencias o conocimiento canónico.

## Límites

- TRAMA conserva contratos, políticas, aislamiento, estado de la API y promoción de conocimiento.
- CCCC conserva la coordinación entre actores y handoffs.
- Hermes aporta conversación, selección de modelo, herramientas y memoria operativa privada.
- Hermes se conecta a un único servidor MCP local por `stdio`.
- El MCP no expondrá una herramienta de promoción canónica.
- Gateway, cron, mensajería, ejecución remota y contenedorización de Hermes quedan fuera de esta fase.

## Arquitectura

```text
Hermes (proceso local supervisado)
        |
        | MCP stdio: herramientas explícitas
        v
trama mcp --api-url http://127.0.0.1:8090
        |
        | HTTP local
        v
TRAMA API -> TramaRuntime -> puertos/adaptadores -> CCCC y memoria
```

El servidor MCP será un proceso ligero sin estado propio. Cada herramienta llamará a la API de TRAMA, evitando que Hermes y el proceso HTTP mantengan runtimes en memoria divergentes. El bind predeterminado de la API continúa limitado a `127.0.0.1`.

## Herramientas MCP iniciales

1. `trama_register_project`: registra o valida un manifiesto de proyecto.
2. `trama_search_context`: busca candidatos de memoria visibles dentro de la organización y proyecto solicitados.
3. `trama_submit_task`: envía una tarea al runtime y CCCC según el adaptador configurado.
4. `trama_record_result`: registra un resultado para una tarea existente.
5. `trama_capture_memory`: guarda un candidato con evidencia; no lo publica en Utopia.

Cada herramienta valida sus argumentos con los contratos Pydantic antes de hacer la llamada HTTP. Las respuestas serán objetos JSON serializables y los errores del API se devolverán como errores controlados de herramienta.

## Aislamiento y seguridad

- Un proyecto solo puede usar la organización declarada por su manifiesto.
- Una tarea debe coincidir con la organización y el repositorio del proyecto registrado.
- Un candidato debe coincidir con la organización y proyecto registrados.
- Una búsqueda compartida solo puede devolver datos de la misma organización.
- Una promoción debe coincidir con el candidato y proyecto correctos, estar aprobada y no tener conflictos.
- El MCP no tendrá acceso a `.env`, credenciales ni archivos arbitrarios.
- Hermes se configurará con aprobaciones manuales y sin modo YOLO.
- El perfil Hermes limitará las herramientas MCP a las cinco herramientas TRAMA declaradas.

## Configuración

TRAMA añadirá configuración tipada desde variables de entorno, con estos valores iniciales:

- `TRAMA_API_HOST=127.0.0.1`
- `TRAMA_API_PORT=8090`
- `TRAMA_API_URL=http://127.0.0.1:8090`
- `TRAMA_CCCC_EXECUTABLE=cccc`
- `TRAMA_CCCC_TIMEOUT_SECONDS=30`

El repositorio incluirá una plantilla de configuración MCP/Hermes y un `AGENTS.md` conciso con los comandos seguros del proyecto. Las plantillas no incluirán claves.

## Verificación

- Pruebas existentes sin regresión.
- Pruebas de rechazo por organización cruzada y proyecto inexistente.
- Pruebas de búsqueda compartida entre organizaciones.
- Pruebas del cliente HTTP MCP con una API FastAPI de prueba.
- Prueba del servidor MCP en memoria mediante el cliente oficial.
- Lint de Ruff y exportación de esquemas JSON.
- Smoke test de arranque del servidor MCP sin escribir datos en stdout fuera del protocolo.
