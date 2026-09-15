# Arquitectura de TRAMA

TRAMA es un entorno de coordinación y conocimiento independiente de los
proyectos que conecta. El proyecto conectado conserva su código, dependencias,
pruebas, secretos y ciclo de despliegue.

## Separación de responsabilidades

```text
Usuario
  |
  v
trama CLI gateway / TUI
  |
  v
TRAMA Control Plane + API local
  |
  +--> Cola acotada local: backpressure y dispatch concurrente
  |
  +--> SQLite local: estado, eventos y auditoria
  |
  +--> CCCC: tareas, actores, estados, mensajes y handoffs
  |
  +--> Codex / OpenCode / otros agentes
  |
  +--> GET /v1/services: catálogo read-only
  |
  +--> Hermes local -- MCP stdio --> TRAMA API
  |
  +--> Hermes -- MCP stdio --> Semantica
  |
  +--> Hermes -- MCP HTTP --> Utopia
  |
  +--> Hermes -- OpenAI-compatible --> Ollama: Qwen3 8B, tool-calling
  |
  +--> Hermes -- OpenAI-compatible --> Colibri: OLMoE 7B, análisis local
  |
  +--> MCP: herramientas y servicios
```

## Aislamiento

Toda tarea, memoria, artefacto y conocimiento lleva `organization_id` y
`project_id`. El acceso cruzado está prohibido por defecto. El conocimiento
compartido requiere una promoción explícita y evidencia verificable.

## Integración de un proyecto

Un proyecto se registra con un manifiesto `ProjectManifestV1`. El manifiesto
declara capacidades y comandos seguros, pero nunca credenciales. TRAMA no
instala sus dependencias ni modifica su código.

El primer adaptador es `generador-diccionario-entidades`, que conservará la
extracción code-first y la auditoría Oracle como fuentes de evidencia. Su
linaje `tabla -> trigger -> DML -> tabla auditiva` podrá convertirse en un
`MemoryCandidate` y, tras validación, en una promoción a Utopia.

Hermes es un proceso externo supervisado de TRAMA. Puede consultar contexto,
enviar tareas, registrar resultados y capturar candidatos con evidencia a
través de MCP `stdio`. Su TUI de conversación, modelos, skills y memoria
propia no se duplican en TRAMA. No publica conocimiento canónico y no
sustituye a CCCC para coordinar actores. El perfil nativo añade directamente
los MCP de Semantica y Utopia y los proveedores OpenAI-compatible de Ollama y
Colibri. Qwen3 es el modelo primario para llamadas a herramientas; OLMoE se
reserva para análisis local porque Colibri no lo declara compatible con
tool-calling nativo.

El catálogo `GET /v1/services` y `trama services status --json` solo hacen
comprobaciones de salud y presencia del modelo configurado. No lanzan procesos,
no leen tokens y no exponen URLs con credenciales. La caída de un servicio
opcional se reporta como `unavailable`.

La TUI de TRAMA consume los mismos servicios que la CLI: estado, proyectos,
tareas, agentes derivados, eventos de auditoría y candidatos visibles. No crea
estado paralelo ni acciones que no existan en el gateway.

La cola de tareas es acotada al proceso para proteger el control plane local:
`TRAMA_QUEUE_CAPACITY` limita las tareas pendientes y
`TRAMA_MAX_CONCURRENCY` los despachos simultáneos. Cuando se alcanza la
capacidad admitida, la API responde `429 queue_full`; no se introduce un broker
compartido en esta fase.

## Política de fallos

- La ausencia de Semantica no detiene una tarea.
- La ausencia de Utopia no invalida una evidencia local.
- La ausencia de Ollama o Colibri no detiene TRAMA; solo impide usar ese perfil
  de modelo.
- Un error de MCP se devuelve como resultado fallido de la herramienta.
- Un error de Model Gateway se registra en el `AgentResult`.
- Un conflicto de conocimiento bloquea la promoción canónica.
- DDL, credenciales y secretos nunca entran en la memoria compartida.
- El servidor MCP local solo registra las herramientas declaradas en la
  plantilla de Hermes y no expone recursos ni prompts adicionales.
