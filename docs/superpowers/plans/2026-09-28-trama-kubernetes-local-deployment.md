# Plan de implementación: despliegue local de TRAMA en Kubernetes

> Para ejecutar este plan, seguirlo tarea por tarea y revisar cada diff antes de continuar. La ejecución nativa requiere `superpowers:executing-plans`; la ejecución por subagentes requiere `superpowers:subagent-driven-development`.

**Objetivo:** desplegar el stack distribuido de TRAMA en Minikube dentro de WSL usando Ansible, Helm e imágenes construidas localmente.

**Arquitectura:** Ansible valida que el destino sea el perfil Minikube local, construye y carga las imágenes de gateway, outbox y Python, prepara los Secrets de aplicación y autenticación PostgreSQL a partir de Ansible Vault y aplica releases Helm para PostgreSQL, NATS JetStream, Redis y el chart de TRAMA. La API Python y el worker comparten el PVC SQLite existente; todos los Deployments de TRAMA quedan en una réplica.

**Stack:** WSL Ubuntu, Minikube, kubectl, Helm 4.3.0, Ansible, Docker, charts Helm upstream.

**Especificación:** [docs/superpowers/specs/2026-09-28-trama-kubernetes-local-design.md](../specs/2026-09-28-trama-kubernetes-local-design.md)

## Global Constraints

- Ejecutar kubectl, Helm, Ansible y Docker desde WSL; el clúster destino es Minikube de un nodo.
- Ansible falla antes de mutar el clúster si el contexto actual no es `minikube` o el perfil está detenido.
- Usar el namespace `trama`; no crear Ingress.
- Mantener una réplica fija por Deployment de TRAMA y desactivar HPA y PDB en los values locales.
- API y worker comparten el PVC `ReadWriteOnce` de SQLite montado en `/data`; el estado usa `/data/state`. No escalar ni programar estos Pods en nodos distintos.
- PostgreSQL y JetStream conservan datos en PVCs. Redis es efímero en este piloto.
- Los Services de aplicación y dependencias son internos. Solo se accede desde el host al gateway con port-forward ligado a localhost.
- Imágenes de TRAMA: `trama-gateway:local`, `trama-outbox:local` y `trama-platform:local`; cargarlas en el mismo perfil Minikube y usar `imagePullPolicy: Never`.
- Guardar credenciales en `~/.config/trama/ansible-vault.yml` cifrado y fuera de Git. No incluir secretos en Helm values ni en argumentos de comandos; marcar tareas que procesan secretos con `no_log: true`.
- No borrar el namespace ni PVCs en un despliegue normal.
- No instalar Harbor, Keycloak, Prometheus ni Grafana. No cambiar la coordinación del worker con CCCC ni afirmar que el piloto valida ese flujo productivo.
- Mantener intactos los cambios preexistentes del árbol de trabajo; agregar a Git únicamente rutas de la tarea que se está confirmando.

## Review Focus

1. **Contexto equivocado o Minikube detenido:** el preflight debe fallar antes de crear namespace, Secrets o releases.
2. **Vault ausente o con claves incompletas:** validar las nueve variables requeridas y detener el playbook antes de desplegar, sin imprimir valores sensibles.
3. **DNS de Services o URLs con credenciales mal codificadas:** construir URLs con los nombres de Service declarados y guardar las URLs ya codificadas en el Vault; comprobar que los Pods pasan readiness.
4. **Imagen local inexistente o tag distinto del values local:** construir y cargar cada tag exacto antes del Helm upgrade; detenerse ante `ImagePullBackOff`.
5. **PVC SQLite, JetStream o worker:** confirmar que API y worker montan el mismo claim, PostgreSQL y JetStream conservan PVCs, y separar salud de Kubernetes del flujo worker→CCCC aún no conectado.

## Estructura de archivos

- `deploy/helm/trama-gateway/values-local.yaml`: overrides solo locales.
- `deploy/helm/trama-gateway/templates/python-api-deployment.yaml` y `python-api-service.yaml`: API Python interno.
- `deploy/ansible/site.yml`: entrada de Ansible y orden de importación de tareas.
- `deploy/ansible/inventory/local.yml`: conexión local y contexto Minikube.
- `deploy/ansible/vars/local.yml`: namespace, nombres de releases, imágenes, referencias y versiones de charts.
- `deploy/ansible/tasks/`: preflight, imágenes, Secret, dependencias y aplicación.
- `deploy/ansible/values/`: configuración no sensible de PostgreSQL, NATS y Redis.
- `deploy/ansible/README.md`: preparación de WSL, Vault, despliegue y acceso local.

## Task 1: ampliar el chart de TRAMA para la API Python

**Files:**

- Create: `deploy/helm/trama-gateway/values-local.yaml`
- Create: `deploy/helm/trama-gateway/templates/python-api-deployment.yaml`
- Create: `deploy/helm/trama-gateway/templates/python-api-service.yaml`
- Modify: `deploy/helm/trama-gateway/values.yaml`
- Modify: `deploy/helm/trama-gateway/templates/python-worker-pvc.yaml`
- Modify: `deploy/helm/trama-gateway/README.md`

**Interfaces:**

- Consume la imagen Python definida por `.Values.pythonWorker.image` y el PVC existente `<release>-python-state`.
- Produce un Service ClusterIP para la API en el puerto 8090 y un Deployment que hereda el comando de API de `deploy/Dockerfile`.
- API y worker usan `TRAMA_STATE_DIR=/data/state` y montan el mismo claim en `/data`.
- La API recibe `TRAMA_API_HOST=0.0.0.0`, `TRAMA_API_PORT=8090` y `TRAMA_API_TOKEN` desde `trama-gateway-secrets`.
- El endpoint de API queda solo interno. El único port-forward documentado apunta al Service del gateway.

**Steps:**

- [ ] Añadir valores `pythonApi.enabled`, `replicaCount`, `service.port=8090`, `stateDir=/data/state` y recursos; añadir `secrets.pythonApiTokenKey`. Mantener defaults productivos del chart y dejar los overrides del piloto en el archivo local.
- [ ] Crear `python-api-deployment.yaml` con la imagen compartida, variables del API, token desde Secret, mount del claim Python y probes TCP al puerto 8090.
- [ ] Crear `python-api-service.yaml` como ClusterIP con selector `app.kubernetes.io/component: python-api`.
- [ ] Ajustar la etiqueta del PVC a un componente compartido de estado; mantener su nombre y acceso `ReadWriteOnce` para que worker y API referencien el mismo claim.
- [ ] En `values-local.yaml`, fijar gateway, outbox, API y worker en una réplica; desactivar HPA/PDB; configurar los tres repositorios de imágenes locales, tag `local` y pull policy `Never`.
- [ ] Actualizar el README del chart con el límite de un nodo, el PVC compartido y el alcance local.
- [ ] Revisar el render: `helm lint --strict ./deploy/helm/trama-gateway -f ./deploy/helm/trama-gateway/values-local.yaml`; después `helm template trama-gateway ./deploy/helm/trama-gateway --namespace trama -f ./deploy/helm/trama-gateway/values-local.yaml`. Confirmar dos workloads Python con el mismo claim y Services internos.
- [ ] Commit de las rutas de esta tarea: `feat(helm): add Python API to local chart`.

## Task 2: preparar Ansible, preflight, imágenes y Secrets

**Files:**

- Create: `deploy/ansible/site.yml`
- Create: `deploy/ansible/inventory/local.yml`
- Create: `deploy/ansible/vars/local.yml`
- Create: `deploy/ansible/tasks/preflight.yml`
- Create: `deploy/ansible/tasks/images.yml`
- Create: `deploy/ansible/tasks/secrets.yml`

**Interfaces:**

- Inventario local: `localhost`, conexión local, contexto `minikube`, namespace `trama`.
- El Vault externo define las URLs ya codificadas `database_url`, `redis_url`, `nats_url`, y las variables `gateway_service_account_token`, `gateway_organization_id`, `python_api_token`, `postgresql_username`, `postgresql_password` y `postgresql_admin_password`. El usuario y la contraseña de `database_url` deben coincidir con las credenciales de la aplicación PostgreSQL.
- `site.yml` carga preflight, imágenes y Secrets antes de las tareas Helm de Task 3.
- Usar solo módulos `ansible.builtin` y los CLIs ya instalados; no introducir una colección adicional.

**Steps:**

- [ ] Crear inventario y variables para `repo_root`, namespace, contexto, releases, charts y tags de imagen.
- [ ] Añadir preflight que compruebe en WSL `ansible-playbook`, `docker`, `minikube`, `kubectl` y `helm`; comprobar también `kubectl config current-context == minikube` y `minikube status -p minikube`. En Windows, consultar `Get-Command` antes de instalar una utilidad; en WSL confirmar disponibilidad con `command -v`. Instalar Ansible solo dentro de WSL si falta.
- [ ] Cargar `~/.config/trama/ansible-vault.yml` mediante `include_vars`; fallar si falta cualquiera de las nueve variables requeridas. No crear ni versionar el archivo cifrado.
- [ ] Construir desde la raíz del repositorio: `gateway/Dockerfile` con `TRAMA_BINARY=trama-gateway`, el mismo Dockerfile con `TRAMA_BINARY=trama-outbox`, y `deploy/Dockerfile` para `trama-platform`. Cargar cada tag exacto con `minikube image load`.
- [ ] Aplicar `trama-gateway-secrets` por stdin con `kubectl apply -f -` y `stringData` para las credenciales de aplicación; usar `no_log: true` y no interpolar secretos en argv.
- [ ] Aplicar `trama-postgresql-auth` por stdin con las claves de autenticación que exige la versión fijada del chart, usando las credenciales PostgreSQL de Vault; usar `no_log: true` y hacer que Helm consuma el Secret por referencia.
- [ ] Comprobar sintaxis con `ansible-playbook -i deploy/ansible/inventory/local.yml --syntax-check deploy/ansible/site.yml --ask-vault-pass`.
- [ ] Commit de las rutas de esta tarea: `feat(ansible): add local preflight and image setup`.

## Task 3: desplegar dependencias y TRAMA en orden

**Files:**

- Create: `deploy/ansible/tasks/dependencies.yml`
- Create: `deploy/ansible/tasks/application.yml`
- Create: `deploy/ansible/values/postgresql.yml`
- Create: `deploy/ansible/values/nats.yml`
- Create: `deploy/ansible/values/redis.yml`
- Modify: `deploy/ansible/site.yml`
- Modify: `deploy/ansible/vars/local.yml`

**Interfaces:**

- Usar PostgreSQL y Redis de los charts OCI de Bitnami y NATS del chart oficial `nats/nats`; registrar referencias y versiones exactas en `vars/local.yml`.
- Nombres de release: `trama-postgresql`, `trama-nats`, `trama-redis` y `trama-gateway`.
- `database_url`, `redis_url` y `nats_url` apuntan a Services internos del namespace `trama`. PostgreSQL consume `trama-postgresql-auth` mediante `auth.existingSecret`; los values guardan nombres de Secrets y parámetros no sensibles, nunca contraseñas.
- El playbook usa `helm upgrade --install` con `--wait`; Helm renderizado y Service DNS deben coincidir antes de habilitar el release de TRAMA.

**Steps:**

- [ ] Fijar versiones de los charts upstream y versiones de PostgreSQL, NATS y Redis compatibles con los servicios actuales de Compose (majors 16, 2.11 y 7.4). No usar `latest` ni rangos; mantener los números en `vars/local.yml`.
- [ ] Crear values de PostgreSQL con una réplica, PVC persistente y `auth.existingSecret: trama-postgresql-auth`, usando las claves de Secret que documente la versión fijada del chart; NATS con JetStream habilitado y PVC; Redis en modo standalone y sin PVC.
- [ ] Añadir tareas `helm upgrade --install` idempotentes para PostgreSQL, NATS y Redis en namespace `trama`; esperar a que cada release esté listo.
- [ ] Confirmar los nombres DNS de Service que producen los charts y hacer que coincidan con las URLs guardadas en Vault.
- [ ] Añadir instalación de `trama-gateway` desde `./deploy/helm/trama-gateway` con `values-local.yaml`, `--namespace trama`, `--wait` y timeout explícito.
- [ ] Añadir `kubectl rollout status` para gateway, outbox, API y worker; verificar PVCs de Python, PostgreSQL y JetStream sin ejecutar tareas de borrado.
- [ ] Añadir las tareas al orden `preflight → images → secrets → dependencies → application` en `site.yml`.
- [ ] Ejecutar `ansible-playbook -i deploy/ansible/inventory/local.yml deploy/ansible/site.yml --ask-vault-pass` solo al iniciar la implementación aprobada; el playbook debe poder repetirse sin duplicar releases ni eliminar PVCs.
- [ ] Commit de las rutas de esta tarea: `feat(ansible): deploy local trama helm releases`.

## Task 4: documentar el flujo local

**Files:**

- Create: `deploy/ansible/README.md`
- Modify: `deploy/helm/trama-gateway/README.md`

**Steps:**

- [ ] Documentar requisitos WSL, instalación de Ansible si no está presente, perfil Minikube, creación externa del Vault cifrado y nombres requeridos de sus variables.
- [ ] Documentar instalación de dependencias de Ansible si se detectan ausentes, sin crear Secrets en archivos versionados.
- [ ] Documentar el comando de despliegue y acceso con `kubectl port-forward -n trama svc/trama-gateway 8080:8080`; dejar claro que la API Python no se publica en el host.
- [ ] Documentar inspección operativa con `kubectl get pods,services,pvc -n trama` y el límite SQLite/CCCC.
- [ ] Commit de las rutas de esta tarea: `docs: document local Kubernetes deployment`.

## Validación operativa de aceptación

- `helm lint` y `helm template` renderizan el chart local sin errores.
- `ansible-playbook --syntax-check` completa y el preflight rechaza un contexto distinto de Minikube antes de crear recursos.
- Una aplicación normal deja cuatro Deployments de TRAMA listos con una réplica; PostgreSQL, NATS JetStream y Redis tienen Services internos.
- API y worker montan el mismo PVC; PostgreSQL y JetStream mantienen sus PVCs tras un upgrade.
- Solo el gateway se alcanza desde Windows por el port-forward a `127.0.0.1`; la API Python no tiene Ingress ni port-forward.
- El estado saludable de Kubernetes no se confunde con la validación productiva de worker→CCCC.
