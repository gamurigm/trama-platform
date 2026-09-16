# TRAMA gateway Helm chart

El chart despliega el gateway Go, el control plane Python privado, dos réplicas
del outbox y dos consumidores Python. PostgreSQL, Redis y NATS no se instalan
dentro del chart: deben ser servicios gestionados o releases separados. Un Job
pre-install/pre-upgrade aplica las migraciones de gateway, control plane y
ownership durable de tareas.

Antes de instalar, crea el Secret referenciado por `secrets.existingSecret`
con `database-url`, `redis-url`, `nats-url` y `control-plane-internal-token`.
En producción configura además OIDC (`oidc-issuer` y `oidc-audience`) o una
cuenta de servicio, y conserva `auth.required=true`.

```bash
helm upgrade --install trama-gateway ./deploy/helm/trama-gateway \
  --namespace trama --create-namespace
```

El control plane y los workers usan PostgreSQL compartido; no existe PVC de
estado Python. La inbox `trama.consumed_events` coordina redeliveries de
JetStream entre réplicas y `trama.task_leases` coordina el ownership de
ejecución por tarea. El servicio del control plane es `ClusterIP` y solo el
gateway debe exponerse hacia clientes.
