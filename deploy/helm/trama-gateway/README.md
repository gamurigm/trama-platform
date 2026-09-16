# TRAMA gateway Helm chart

El chart despliega el gateway Go, dos réplicas del outbox y el consumidor
Python. PostgreSQL, Redis y NATS no se instalan dentro del chart: deben ser
servicios gestionados o releases separados.

Antes de instalar, crea el Secret referenciado por `secrets.existingSecret`
con `database-url`, `redis-url` y `nats-url`. En producción configura además
OIDC (`oidc-issuer` y `oidc-audience`) o una cuenta de servicio, y conserva
`auth.required=true`.

```bash
helm upgrade --install trama-gateway ./deploy/helm/trama-gateway \
  --namespace trama --create-namespace
```

El worker Python usa un PVC `ReadWriteOnce` porque su inbox local es SQLite;
mantener una réplica evita que dos procesos escriban el mismo archivo. Si se
requiere escalar workers horizontalmente, el siguiente paso es conectar el
inbox y el estado Python a PostgreSQL compartido.
