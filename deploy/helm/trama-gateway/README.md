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

## Perfil local de Minikube

Para el piloto local, usa los overrides de values-local.yaml. Mantén una
réplica para cada workload y desactiva HPA y PDB. PostgreSQL conserva el estado
compartido del control plane y los workers; JetStream conserva sus mensajes en
su PVC. El chart no crea una API Python adicional ni un PVC SQLite.

~~~bash
helm lint --strict ./deploy/helm/trama-gateway \
  -f ./deploy/helm/trama-gateway/values-local.yaml
helm template trama-gateway ./deploy/helm/trama-gateway \
  --namespace trama -f ./deploy/helm/trama-gateway/values-local.yaml
~~~

Configura el Secret de la aplicación y los servicios PostgreSQL, Redis y NATS
antes de instalar. Solo el gateway se expone mediante port-forward a
127.0.0.1:8080; el control plane permanece en un Service interno.