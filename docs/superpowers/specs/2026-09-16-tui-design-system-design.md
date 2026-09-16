# TUI Design System de TRAMA

## Estado

Diseño aprobado por el usuario para la TUI TypeScript en `tui/`. Esta
especificación precede a la implementación y no modifica la TUI Python.

## Objetivo

Convertir la TUI TypeScript actual, que muestra estado, fases, agentes y
tareas, en un centro operativo navegable para TRAMA. La interfaz debe hacer
visible el estado de proyectos, tareas, agentes, colas, workers, eventos,
memoria y salud del sistema sin mover lógica de negocio al cliente.

La API Python continúa siendo la fuente de verdad. La TUI Python iniciada por
`trama tui` permanece como fallback durante toda esta evolución.

## Alcance

Incluye:

- Shell de aplicación con navegación lateral, contenido principal y barra de
  shortcuts.
- Pantallas `Dashboard`, `Projects`, `Tasks`, `Agents`, `Queues`, `Workers`,
  `Events`, `Memory` y `System health`.
- Paneles reutilizables con bordes, títulos, tabs, split views y densidad
  apropiada para terminal.
- Navegación con flechas y `j/k`, foco visible, selección estable y retorno
  con `Esc`.
- Command palette con `/`, filtro local con `f` y selector de proyecto con
  `p`.
- Polling controlado, actualización manual con `r` y salida limpia con `q`.
- Estados explícitos de carga, vacío, actualizado, obsoleto, bloqueado, error,
  acción en progreso, éxito y rechazo.
- Confirmaciones antes de aprobar, cancelar o reintentar operaciones.
- Pruebas headless de interacción, renderizado, aislamiento y estados.

No incluye:

- Cambios a contratos backend existentes.
- WebSocket o streaming.
- Sustitución de Textual ni del comando `trama tui`.
- Datos inventados cuando un endpoint no entrega workers, salud detallada u
  otra métrica.

## Dirección visual

La metáfora visual es un radar de operaciones: información densa, silenciosa
y escaneable. La estructura se comunica mediante alineación y bordes, no por
decoración.

### Tokens base

| Token | Valor | Uso |
| --- | --- | --- |
| `void` | `#07111F` | Fondo general |
| `panel` | `#10253A` | Superficie de panel |
| `text` | `#E8F1F8` | Texto principal |
| `focus` | `#63E6E2` | Foco, selección y actividad |
| `cognitive` | `#B8A1FF` | Agentes, memoria y conocimiento |
| `attention` | `#FFB454` | Espera, cola y aprobación |

Los errores y bloqueos usarán rojo suave, acompañado siempre de símbolo y
texto. El color no será el único indicador del estado.

### Layout

En terminales amplias, la navegación ocupa una columna fija y el contenido
usa dos o tres paneles según la pantalla. El dashboard prioriza el flujo
operativo sobre KPIs grandes.

```text
┌ TRAMA · proyecto/demo · API ● · última actualización 2s ┐
├──────────────┬───────────────────────────────────────────┤
│ Dashboard    │ Dashboard operativo                       │
│ Projects     │ ┌ Projects ┐ ┌ Tasks ┐ ┌ Health ┐         │
│ Tasks        │ ├───────────────────────────────────────┤
│ Agents       │ │ fases / workers / colas                 │
│ Queues       │ ├───────────────────────────────────────┤
│ Workers      │ │ actividad reciente                      │
│ Events       │ └───────────────────────────────────────┘│
│ Memory       │                                           │
│ System health│                                           │
├──────────────┴───────────────────────────────────────────┤
│ ↑↓ navegar  Enter abrir  / comandos  r actualizar  q salir│
└───────────────────────────────────────────────────────────┘
```

En terminales estrechas, la navegación se convierte en una barra compacta y
los paneles se apilan sin ocultar sus títulos ni campos esenciales.

## Arquitectura

```text
API TRAMA
   ↓
TramaApiClient + DTOs tipados
   ↓
View model + reducer de navegación
   ↓
AppShell + pantallas OpenTUI React
```

La aplicación se dividirá en:

- `api`: transporte, timeout, parsing y contratos del cliente.
- `navigation`: ruta, proyecto activo, foco, selección y overlays como estado
  puro y testeable.
- `ui`: tokens, paneles, badges, ayudas de teclado, tablas y command palette.
- `screens`: una pantalla por dominio operativo.
- `AppShell`: composición global, polling, mensajes y lifecycle del renderer.

OpenTUI será el único renderizador interactivo. Ink no se mezclará dentro del
árbol OpenTUI; `chalk`, `yoctocolors`, `ora` y `cli-table3` solo podrán usarse
en utilidades de consola no interactivas si una necesidad concreta lo
justifica.

## Pantallas y datos

El dashboard consultará `/v1/status` y `/v1/overview`. Las pantallas de
detalle cargarán sus datos al entrar y no forzarán una consulta completa del
dashboard en cada ciclo de polling.

El cliente incorporará métodos tipados para:

- proyectos y proyecto activo;
- tareas y sus acciones soportadas;
- agentes, colas y métricas de dispatch;
- eventos, logs y timelines;
- candidatos y búsquedas de memoria;
- salud de la API y estado del dispatcher.

Cada consulta dependiente de proyecto conservará `project_id`. La TUI no
combinará resultados de proyectos distintos. Si el backend no expone un dato,
la pantalla mostrará `no disponible` y mantendrá el resto de la vista útil.

## Interacción

| Tecla | Acción |
| --- | --- |
| `↑/↓`, `j/k` | Mover selección |
| `Enter` | Abrir detalle |
| `Esc` | Volver o cerrar overlay |
| `/` | Abrir command palette |
| `f` | Filtrar la vista actual |
| `p` | Cambiar proyecto |
| `r` | Actualizar datos |
| `?` | Mostrar ayuda |
| `q` | Salir limpiamente |

La selección se conservará después del polling mediante IDs estables. Si el
elemento seleccionado desaparece, el foco se moverá al vecino más cercano.

Aprobar, cancelar y reintentar requerirán una confirmación contextual. El
diálogo indicará el objeto, la consecuencia y la tecla de confirmación. Una
acción en progreso bloqueará su propio control, pero no congelará la
navegación global.

## Estados y errores

Los estados de datos y acciones serán independientes. Un fallo de refresco
conservará el último dato válido, marcará la vista como obsoleta y mostrará
una alerta recuperable. Un error no desmontará la aplicación ni dejará el
terminal en modo raw.

Los estados vacíos explicarán qué falta y qué acción puede realizar el
usuario. Las respuestas inválidas, timeouts y errores HTTP conservarán el
endpoint afectado en el mensaje técnico visible, sin mostrar tokens,
credenciales ni contenido de configuración sensible.

El polling se pausará mientras esté abierta la command palette o un diálogo.
La actualización manual reiniciará el ciclo y evitará solicitudes duplicadas.

## Verificación

Las pruebas cubrirán:

- reducer de rutas, foco, overlays y selección estable;
- parser del cliente y aislamiento por `project_id`;
- render de cada pantalla con datos, vacío y dato no disponible;
- estados de carga, obsoleto, error recuperable y acción en progreso;
- command palette, shortcuts y confirmaciones;
- snapshots a 100×30, 80×24 y 48×24;
- `renderer.destroy()` al salir y al terminar cada prueba.

La aceptación requiere que:

1. La TUI TypeScript conserve la conexión por defecto a `127.0.0.1` y no
   amplíe el binding de la API.
2. El dashboard muestre el contexto del proyecto activo y los dominios
   operativos disponibles.
3. La navegación funcione con teclado y mantenga el foco visible.
4. Las acciones destructivas o mutantes pidan confirmación antes de enviarse.
5. Los errores de API sean visibles, recuperables y no rompan el flujo.
6. Las pruebas headless y el typecheck pasen con el runtime soportado por el
   proyecto.
7. `trama tui` siga funcionando como implementación Python independiente.

## Mapa inicial de archivos

```text
tui/src/
├─ api/client.ts
├─ api/types.ts
├─ navigation/model.ts
├─ navigation/reducer.ts
├─ ui/tokens.ts
├─ ui/Panel.tsx
├─ ui/StatusBadge.tsx
├─ ui/KeyHints.tsx
├─ ui/CommandPalette.tsx
├─ screens/DashboardScreen.tsx
├─ screens/ProjectsScreen.tsx
├─ screens/TasksScreen.tsx
├─ screens/AgentsScreen.tsx
├─ screens/QueuesScreen.tsx
├─ screens/WorkersScreen.tsx
├─ screens/EventsScreen.tsx
├─ screens/MemoryScreen.tsx
├─ screens/HealthScreen.tsx
└─ App.tsx
```
