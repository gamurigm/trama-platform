# Contratos TRAMA

Los contratos se definen en `src/trama_platform/contracts.py` con Pydantic y
se exportan como JSON Schema versionado mediante:

```powershell
.\.venv\Scripts\python.exe -m trama_platform export-schemas contracts
```

Los esquemas generados son artefactos públicos de interoperabilidad. Las
implementaciones de CCCC, Semantica, Utopia, MCP y Model Gateway no forman
parte de estos contratos.
