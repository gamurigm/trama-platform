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

### Servicios nativos configurados

Usa `trama services status --json` para consultar los servicios nativos configurados.
Semantica requiere `TRAMA_SEMANTICA_ENABLED`; Utopia se incorpora cuando
`TRAMA_UTOPIA_MCP_URL` está definido.

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
El piloto local con Minikube y Ansible está documentado en
[deploy/ansible/README.md](deploy/ansible/README.md).

#### CCCC del host Windows desde el worker Docker

Para conectar el worker Docker con CCCC en Windows, configura
`TRAMA_COORDINATION_BACKEND=cccc-bridge`. Consulta la IP de `vEthernet (WSL)`:

```powershell
Get-NetIPAddress -InterfaceAlias "vEthernet (WSL)" -AddressFamily IPv4
```

En la terminal PowerShell que ejecutará el puente, configura el actor aprobado,
el destinatario de resultados y un token compartido con Compose. El token se
solicita sin mostrarlo ni escribirlo en el historial:

```powershell
$env:TRAMA_CCCC_ALLOWED_ACTORS = "<actor-CCCC-aprobado>"
$env:TRAMA_CCCC_RESULT_RECIPIENT = "foreman"
$secure = Read-Host "Token local del puente" -AsSecureString
$env:TRAMA_CCCC_BRIDGE_TOKEN = [System.Net.NetworkCredential]::new("", $secure).Password
Remove-Variable secure
trama cccc-bridge --host <IP-de-vEthernet-WSL> --port 8091
```

El comando rechaza tareas de actores no aprobados y exige el token compartido.

En WSL, configura el mismo backend, URL y token antes de recrear los servicios:

```bash
export TRAMA_COORDINATION_BACKEND=cccc-bridge
export TRAMA_CCCC_BRIDGE_URL=http://<IP-de-vEthernet-WSL>:8091
read -r -s -p 'Token local del puente: ' TRAMA_CCCC_BRIDGE_TOKEN
printf '\n'
export TRAMA_CCCC_BRIDGE_TOKEN
docker compose -f deploy/docker-compose.gateway.yml up -d --build control-plane python-worker
```

Limita el firewall de Windows al adaptador WSL y a su origen. Detén el puente
con `Ctrl+C` y CCCC con `cccc daemon stop` al terminar.

## Desarrollo

Requiere Python 3.12 o superior y `uv`:

```bash
uv sync --extra dev
uv run trama --help
uv run pytest
```
