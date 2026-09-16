# TUI TypeScript de TRAMA — Diseño

## Objetivo

Construir una TUI TypeScript independiente para TRAMA usando Bun, OpenTUI y
el reconciler de React. La nueva TUI será un cliente de la API Python local y
replicará inicialmente la consola operativa existente sin trasladar lógica de
negocio al frontend.

La migración será incremental: `trama tui` continuará ejecutando la TUI Python
como fallback mientras la nueva TUI alcanza paridad funcional.

## Alcance del primer incremento

Incluye:

- Dashboard de solo lectura.
- Estado general de TRAMA.
- Fases con progreso y conteos.
- Especialistas CCCC y sus conteos.
- Cola de tareas con estado, objetivo, agente y origen.
- Polling automático cada dos segundos.
- Atajos `r` para actualizar y `q` para salir.
- Estados visibles de conexión, carga, vacío y error.
- Layout vertical automático para terminales estrechas.

No incluye acciones sobre tareas (`approve`, `retry`, `cancel`), navegación a
detalles ni sustitución del comando `trama tui`; quedan para una segunda fase.

## Arquitectura

La TUI se ubicará en un paquete independiente bajo `tui/`:

```text
tui/
├─ package.json
├─ tsconfig.json
└─ src/
   ├─ index.tsx
   ├─ App.tsx
   ├─ api/
   │  ├─ client.ts
   │  └─ types.ts
   └─ components/
      ├─ StatusBar.tsx
      ├─ PhasePanel.tsx
      ├─ AgentsPanel.tsx
      └─ TaskTable.tsx
```

El arranque seguirá el patrón de OpenTUI con `bunx create-tui@latest -t react`.
La aplicación se ejecutará con `bun run --cwd tui start`. El backend Python
seguirá siendo la autoridad de estado, contratos y reglas de negocio.

Flujo de datos:

```text
Bun/OpenTUI → cliente HTTP → API Python → runtime TRAMA
```

La integración con `trama tui` no cambiará en esta fase. Cuando la nueva TUI
sea estable, podrá añadirse un comando separado o un selector explícito sin
romper el fallback existente.

## Interfaz

La pantalla conservará la jerarquía de la TUI Python:

- Barra superior con estado, número de proyectos, profundidad de cola y
  dispatches activos.
- Columna izquierda con fases y especialistas CCCC.
- Columna derecha con la tabla de tareas.
- Disposición vertical cuando el ancho de terminal no permita dos columnas.

La semántica visual conservará los estados actuales: ejecutando, bloqueado,
exitoso y pendiente. Los errores de API se mostrarán dentro de la pantalla y
la interfaz seguirá pudiendo cerrarse limpiamente.

## Cliente y datos

`src/api/types.ts` definirá los DTOs mínimos del MVP:

- `Status`
- `Overview`
- `Phase`
- `Agent`
- `Task`

`src/api/client.ts` usará `fetch` de Bun, con timeout y errores tipados. La
fuente principal será `/v1/overview` junto con `/v1/status`. Si el overview no
incluye la cola, el cliente consultará `/v1/tasks`, siguiendo el comportamiento
de la TUI Python. No se inventarán datos ante errores o respuestas inválidas.

La URL base será configurable, con `http://127.0.0.1:8090` como valor local
por defecto, sin ampliar el binding de la API.

## Pruebas y verificación

La TUI usará `bun:test` y `@opentui/react/test-utils` para pruebas headless:

- Render inicial con datos representativos.
- Estados de carga, vacío y error.
- Actualización disparada por `r`.
- Snapshot del layout a 80×24.
- Layout en terminal estrecha.
- Limpieza del renderer después de cada prueba.

La verificación del primer incremento incluirá las pruebas Python existentes,
las pruebas Bun de `tui/` y una ejecución manual con la API local activa.
Los cambios TypeScript no requieren compilación nativa de OpenTUI; Bun ejecuta
TypeScript directamente. No se usará `process.exit()` para cerrar la TUI:
debe utilizarse `renderer.destroy()`.

## Criterios de aceptación

1. `bun install` y `bun run --cwd tui start` funcionan desde la raíz del
   repositorio con la API local disponible.
2. La pantalla muestra correctamente estado, fases, agentes y cola a partir de
   datos reales de la API.
3. `r` actualiza los datos y `q` sale sin dejar el terminal en modo raw.
4. Un fallo de API produce un estado de error visible y recuperable mediante
   actualización.
5. El layout sigue siendo legible en una terminal estrecha.
6. Las pruebas Bun cubren los estados y snapshots definidos.
7. `trama tui` continúa ejecutando la implementación Python existente.

## Fuera de alcance

- Migración de la lógica de negocio Python.
- Cambios en contratos versionados de la API.
- WebSocket o streaming en tiempo real.
- Acciones mutantes sobre tareas.
- Eliminación de Textual o del comando Python existente.
