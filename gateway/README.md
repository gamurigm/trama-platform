# Gateway Go de TRAMA

El módulo es independiente del runtime Python y contiene dos procesos:

- `trama-gateway`: admisión HTTP, idempotencia por organización, proyección
  read-your-write, rate limit Redis y auth OIDC/cuentas de servicio.
- `trama-outbox`: reclama el outbox de PostgreSQL con leases y publica en NATS
  JetStream con `Nats-Msg-Id`.

Desarrollo integrado:

```powershell
docker compose -f deploy/docker-compose.gateway.yml up --build
```

Variables mínimas del gateway: `TRAMA_DATABASE_URL`; para despliegue
multi-réplica configura también `TRAMA_REDIS_URL`. Las migraciones están en
`migrations/000001_gateway.sql`, `migrations/000002_control_plane.sql` y
`migrations/000003_namespace_keys.sql`. El módulo se prueba desde este
directorio con `go test -race ./...`.

En producción, configura `TRAMA_ENV=prod`, autenticación obligatoria,
`TRAMA_CONTROL_PLANE_URL` y `TRAMA_CONTROL_PLANE_INTERNAL_TOKEN`. El gateway
es el único borde público: las rutas `/v1/*` que no son admisión se reenvían al
control plane Python privado.
