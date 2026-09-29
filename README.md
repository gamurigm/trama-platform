![TRAMA](docs/banner-trama.png)

# TRAMA

TRAMA coordina agentes de IA y proyectos independientes. Centraliza proyectos,
tareas, resultados y memoria, mientras cada proyecto conserva su código,
dependencias y reglas.

## Herramientas

- **Python**: API, estado y coordinación.
- **CCCC**: ejecución y seguimiento de tareas.
- **MCP y Hermes**: conexión con herramientas y agente local supervisado.
- **Gateway Go**: admisión durable de tareas en modo distribuido.
- **PostgreSQL, NATS y Redis**: persistencia, eventos y límites compartidos en
  modo distribuido.
- **Semantica y Utopia**: integraciones opcionales de memoria y conocimiento.

La API conserva el estado y las aprobaciones humanas. La arquitectura general
está en [docs/arquitectura-trama.svg](docs/arquitectura-trama.svg).

## Despliegue local

Desde WSL, en la raíz del repositorio:

```bash
docker compose -f deploy/docker-compose.yml up --build
```

La API queda disponible solo en la máquina local, en `http://127.0.0.1:8090`.
Para detenerla:

```bash
docker compose -f deploy/docker-compose.yml down
```

## Modo distribuido

Desde WSL, inicia el gateway con PostgreSQL, NATS JetStream, Redis y los
workers:

```bash
docker compose -f deploy/docker-compose.gateway.yml up --build
```

Para Kubernetes, usa el chart `deploy/helm/trama-gateway` y configura los
secretos en un Secret del clúster. No publiques la API Python fuera de la red
interna; el acceso público debe pasar por el gateway.

## Desarrollo

Requiere Python 3.12 o superior y `uv`:

```bash
uv sync --extra dev
uv run trama --help
uv run pytest
```
