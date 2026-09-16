# Integración real de Semantica y Utopia

TRAMA integrará Semantica como memoria/contexto de agentes mediante un adaptador Python opcional y Utopia como conocimiento gobernado mediante un adaptador MCP opcional. Los contratos de TRAMA seguirán siendo la frontera estable: organización, proyecto, agente, tarea y evidencia se conservarán en cada operación.

Semantica recibirá hechos y decisiones con metadatos de procedencia, incluyendo `organization_id`, `project_id`, `agent_id` y `task_id`, y devolverá resultados normalizados a `MemoryCandidate`. Utopia recibirá candidatos aprobados como contenido propuesto a través de una herramienta MCP configurable; las lecturas usarán sus herramientas MCP de búsqueda y el control de permisos quedará en la base de conocimiento de Utopia.

La integración será opcional y tendrá fallback local explícito. No se asumirán endpoints `/v1/memory/candidates` ni `/v1/knowledge/promotions` que los repositorios externos no documentan. Las pruebas usarán dobles de transporte/cliente para verificar payloads, scopes y errores sin requerir servicios externos.
