# TRAMA gateway Helm chart

El chart despliega el gateway Go, el outbox, la API Python y el consumidor
Python. PostgreSQL, Redis y NATS se instalan como releases separados del chart.

Antes de instalar, crea el Secret referenciado por `secrets.existingSecret`
con `database-url`, `redis-url`, `nats-url` y `python-api-token`. En producción configura además
OIDC (`oidc-issuer` y `oidc-audience`) o una cuenta de servicio, y conserva
`auth.required=true`.

```bash
helm upgrade --install trama-gateway ./deploy/helm/trama-gateway \
  --namespace trama --create-namespace
```

La API Python solo tiene un Service `ClusterIP`; el chart no crea Ingress ni
publica ese puerto en el host. API y worker montan el mismo PVC `ReadWriteOnce`
con `TRAMA_STATE_DIR=/data/state`. El perfil local está pensado para Minikube
de un nodo, una réplica por workload, imágenes ya cargadas y sin HPA/PDB:

```bash
helm lint --strict ./deploy/helm/trama-gateway \
  -f ./deploy/helm/trama-gateway/values-local.yaml
helm template trama-gateway ./deploy/helm/trama-gateway \
  --namespace trama -f ./deploy/helm/trama-gateway/values-local.yaml
```

El worker conserva SQLite en el PVC. La disponibilidad de Kubernetes no valida
la coordinación productiva worker→CCCC; esa integración requiere una prueba
separada contra el servicio CCCC.
