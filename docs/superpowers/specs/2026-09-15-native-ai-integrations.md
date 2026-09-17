# Integraciones nativas de IA para TRAMA

## Objetivo

Convertir el CLI gateway de TRAMA en el punto de operación de la plataforma:
Hermes debe poder usar las herramientas de TRAMA, Semantica y Utopia desde un
solo perfil local supervisado, mientras que el gateway de modelos debe ofrecer
un perfil estable para tool-calling y otro perfil de análisis local con
Colibri/OLMoE.

## Decisión de modelos

- `qwen3:8b` servido por Ollama es el modelo operativo predeterminado de
  Hermes. Se elige por su soporte de tool-calling y su coste razonable en una
  máquina CPU/RAM de escritorio.
- `OLMoE-1B-7B-0125-Instruct` servido por Colibri queda como perfil local de
  conversación y análisis. Colibri documenta que OLMoE no admite declaraciones
  activas de herramientas; por eso Hermes no lo usará como modelo predeterminado
  para operaciones con tools.
- Los dos perfiles usan el protocolo OpenAI-compatible. El cambio de modelo no
  cambia el acceso a las herramientas MCP.

## Arquitectura

```text
                         +-----------------------------+
                         | Hermes Agent                 |
                         | aprobaciones manuales        |
                         | default: Qwen3 8B / Ollama  |
                         +---------------+-------------+
                                         |
              +--------------------------+--------------------------+
              |                          |                          |
              | MCP stdio                | MCP stdio                | MCP HTTP
              v                          v                          v
       TRAMA API/MCP              Semantica MCP             Utopia KB MCP
       127.0.0.1:8090             proceso aislado            127.0.0.1:1516
              |                          |                          |
       estado y políticas          grafo/proveniencia         episodios/KG

       Hermes model gateway: Ollama /v1 (tools) <-> Colibri /v1 (OLMoE)
```

TRAMA conserva la fuente de verdad de proyectos, tareas, resultados, eventos y
promoción. Los servidores externos conservan sus modelos de datos y exponen
sus capacidades nativas a Hermes; no se crea una falsa implementación local de
Semantica o Utopia.

## Alcance

### Incluido

1. Configuración tipada de endpoints, ejecutables y nombres de modelo sin leer
   tokens ni incluir secretos en salidas de estado.
2. Registro de servicios local con health checks cortos y tolerantes a servicios
   apagados.
3. `trama services status --json` como inventario operativo único.
4. `trama hermes configure --all` para generar el perfil Hermes con:
   - MCP `trama` por `stdio` y sus cinco herramientas acotadas.
   - MCP `semantica` por `stdio` cuando se configura su ejecutable.
   - MCP `utopia` por `streamable-http` cuando se configura una URL MCP de KB.
   - Ollama como modelo predeterminado de tool-calling.
   - Colibri/OLMoE como proveedor seleccionable adicional.
5. Una plantilla segura y documentación de instalación/arranque para Windows.

### Fuera de alcance

- Meter Semantica, Utopia, Colibri u Ollama como dependencias obligatorias del
  wheel de TRAMA.
- Copiar o reimplementar sus motores internos.
- Crear cuentas, contraseñas, tokens o KB IDs por el usuario.
- Publicar automáticamente conocimiento canónico desde Hermes.
- Activar YOLO, cron, mensajería, ejecución remota o automatizaciones sin
  aprobación.
- Levantar Docker Desktop o dejar procesos pesados ejecutándose como parte de
  una prueba automatizada.

## Contratos operativos

Variables nuevas y valores locales predeterminados:

```text
TRAMA_OLLAMA_URL=http://127.0.0.1:11434
TRAMA_OLLAMA_MODEL=qwen3:8b
TRAMA_COLIBRI_URL=http://127.0.0.1:8020
TRAMA_COLIBRI_MODEL=olmoe-1b-7b-0125-instruct
TRAMA_COLIBRI_EXECUTABLE=coli
TRAMA_SEMANTICA_ENABLED=false
TRAMA_SEMANTICA_EXECUTABLE=semantica-mcp
TRAMA_UTOPIA_URL=http://127.0.0.1:1516
TRAMA_UTOPIA_MCP_URL=
```

`TramaSettings.from_env()` conserva `127.0.0.1` como bind de TRAMA y valida
que los URLs sean HTTP(S) con host. `TRAMA_UTOPIA_MCP_URL` es una URL completa
porque Utopia necesita el KB ID en la ruta; el token se aporta únicamente en
el entorno local que lee Hermes y jamás se muestra por `config get` o
`services status`.

El inventario de servicios devuelve, como mínimo, `id`, `status`, `kind`,
`endpoint`/`executable`, `model` cuando aplique y un mensaje corto. Los estados
permitidos son `ready`, `missing`, `unavailable`, `disabled` y `error`.

## Seguridad

- Todos los defaults de red son loopback.
- El estado no imprime valores de variables terminadas en `_TOKEN`, `_KEY`,
  `_SECRET` ni cabeceras.
- La plantilla de repositorio contiene solo referencias de entorno y el valor
  no secreto `local` requerido por clientes OpenAI-compatible locales.
- Las aprobaciones Hermes siguen en `manual` y los modos `cron`, `single_query`
  y `unattended` siguen en `deny`.
- Semantica y Utopia se exponen con sus herramientas nativas; TRAMA no las
  convierte en operaciones de escritura implícitas.

## Verificación

- Pruebas de parseo de settings, redacción de secretos, health checks y salida
  de `services status` con endpoints simulados.
- Pruebas de configuración Hermes para ambos perfiles de modelo y los tres MCP
  con URL/ejecutable parametrizados.
- Suite completa de pytest, Ruff, `git diff --check` y exportación de esquemas.
- Smoke real: `trama services status --json`, `ollama list`, `coli info`/health,
  importación de Semantica y apertura del endpoint MCP de Utopia si el usuario
  ya creó el KB/token.
