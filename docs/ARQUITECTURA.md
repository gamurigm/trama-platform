# Arquitectura de TRAMA

TRAMA es un entorno de coordinación y conocimiento independiente de los
proyectos que conecta. El proyecto conectado conserva su código, dependencias,
pruebas, secretos y ciclo de despliegue.

## Separación de responsabilidades

```text
Usuario
  |
  v
TRAMA Orchestrator
  |
  v
CCCC: tareas, actores, estados, mensajes y handoffs
  |
  +--> Codex / OpenCode / otros agentes
  |
  +--> Hermes local -- MCP stdio --> TRAMA API
  |
  +--> MCP: herramientas y servicios
  |
  +--> Model Gateway: proveedores de modelos
  |
  +--> Colibri: memoria local rápida
  |
  +--> Semantica: contexto y memoria episódica
              |
              +--> promoción validada --> Utopia: conocimiento canónico
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

Hermes es un consumidor supervisado de TRAMA. Puede consultar contexto,
enviar tareas, registrar resultados y capturar candidatos con evidencia. No
publica conocimiento canónico y no sustituye a CCCC para coordinar actores.

## Política de fallos

- La ausencia de Semantica no detiene una tarea.
- La ausencia de Utopia no invalida una evidencia local.
- Un error de MCP se devuelve como resultado fallido de la herramienta.
- Un error de Model Gateway se registra en el `AgentResult`.
- Un conflicto de conocimiento bloquea la promoción canónica.
- DDL, credenciales y secretos nunca entran en la memoria compartida.
- El servidor MCP local solo registra las herramientas declaradas en la
  plantilla de Hermes y no expone recursos ni prompts adicionales.
