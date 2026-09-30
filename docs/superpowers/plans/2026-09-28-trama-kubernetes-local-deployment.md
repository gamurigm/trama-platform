# Plan de implementación: despliegue local de TRAMA en Kubernetes

**Objetivo:** desplegar el stack distribuido vigente de TRAMA en Minikube dentro de WSL usando Ansible, Helm e imágenes construidas localmente.

**Arquitectura:** gateway y workloads Python usan PostgreSQL compartido; el outbox publica en NATS JetStream y Redis comparte el rate limit. El chart actual ya contiene gateway, outbox, control plane, worker y migraciones. El piloto no añade una API duplicada ni un PVC SQLite.

**Stack:** WSL Ubuntu, Minikube, kubectl, Helm, Ansible, Docker y charts Helm upstream.

**Especificación:** [docs/superpowers/specs/2026-09-28-trama-kubernetes-local-design.md](../specs/2026-09-28-trama-kubernetes-local-design.md)

## Restricciones globales

- Ejecutar kubectl, Helm, Ansible y Docker desde WSL; el destino es el perfil Minikube de un nodo.
- Fallar antes de mutar el clúster si el contexto no es minikube o el perfil está detenido.
- Usar el namespace trama; no crear Ingress.
- Mantener una réplica por Deployment de TRAMA y desactivar HPA y PDB en values-local.yaml.
- PostgreSQL comparte el estado de gateway, control plane y worker. No añadir PVC SQLite para Python.
- PostgreSQL y JetStream conservan datos en PVCs. Redis es efímero en este piloto.
- Solo el gateway queda accesible desde el host mediante un port-forward ligado a 127.0.0.1.
- Guardar credenciales en ~/.config/trama/vault.yml cifrado y fuera de Git. No poner secretos en Helm values ni en argumentos; ocultar tareas secretas con no_log: true.
- No borrar el namespace ni PVCs en un despliegue normal.
- No instalar Harbor, Keycloak, Prometheus ni Grafana. No afirmar que el piloto valida el flujo worker→CCCC.

## Archivos principales

- deploy/helm/trama-gateway/values-local.yaml: imágenes locales y una réplica por workload.
- deploy/ansible/site.yml: orden de preflight, imágenes, Secrets, dependencias y workloads.
- deploy/ansible/tasks/: validaciones, construcción de imágenes, Secrets e instalación.
- deploy/ansible/values/: configuración no sensible de PostgreSQL, NATS y Redis.
- deploy/ansible/README.md: preparación de WSL, Vault, despliegue y acceso local.

## Tarea 1: configurar el chart existente para Minikube

**Archivos:** deploy/helm/trama-gateway/values-local.yaml y deploy/helm/trama-gateway/README.md.

**Interfaz:** fijar gateway, outbox, control plane y worker a una réplica; usar las imágenes locales trama-gateway:local, trama-outbox:local y trama-python:local con imagePullPolicy Never; desactivar autoscaling y PDB. Mantener el Service del control plane interno y la autenticación requerida del gateway.

**Pasos:**

- Mantener la estructura actual del chart y los nombres de los workloads existentes.
- Configurar natsStreamReplicas en uno para el NATS local de un nodo.
- Documentar que el estado compartido usa PostgreSQL y que el chart no monta un PVC SQLite.
- Documentar comandos de helm lint y helm template para el perfil local.

## Tarea 2: preparar Ansible, preflight, imágenes y Secrets

**Archivos:** inventario local, site.yml, variables, tareas de preflight/imágenes/Secrets y plantillas de Secret.

**Datos del Vault:** database_url, redis_url, nats_url, gateway_service_account_token, gateway_organization_id, control_plane_internal_token, postgresql_username, postgresql_password y postgresql_admin_password. Las URLs deben apuntar a Services del namespace trama y coincidir con las credenciales PostgreSQL.

**Pasos:**

- Comprobar en WSL Ansible, Docker, Minikube, kubectl y Helm.
- Exigir el contexto minikube y un perfil activo antes de aplicar recursos.
- Cargar el Vault cifrado externo y comprobar las nueve variables sin imprimir valores.
- Construir las imágenes del gateway, outbox y Python; cargar cada tag exacto en el mismo perfil Minikube.
- Aplicar los Secrets por stdin con no_log: true. El Secret de la aplicación contiene database-url, redis-url, nats-url, service-account-token, service-account-organization y control-plane-internal-token.
- No crear un token python-api ni publicar el control plane.

## Tarea 3: desplegar dependencias y TRAMA en orden

**Archivos:** tareas Ansible de dependencias y aplicación, values de PostgreSQL/NATS/Redis y site.yml.

**Pasos:**

- Fijar versiones de PostgreSQL, NATS y Redis compatibles con deploy/docker-compose.gateway.yml.
- Instalar PostgreSQL con trama-postgresql-auth, NATS con JetStream y PVC, y Redis standalone efímero.
- Aplicar el chart actual con values-local.yaml y esperar a gateway, outbox, control plane y worker.
- Esperar a que los PVCs de PostgreSQL y NATS queden Bound; no buscar ni montar un PVC de estado Python.
- Confirmar los nombres DNS de Services frente a las URLs del Vault.
- Mantener el orden preflight → imágenes → Secrets → dependencias → workloads. No incluir tareas que borren datos.

## Tarea 4: documentar el flujo local y el experimento

- Documentar WSL, Minikube, Vault, las nueve claves necesarias y el port-forward del gateway.
- Dejar claro que el control plane tiene un Service interno y usa autenticación interna desde el gateway.
- Documentar la consulta de Pods, Services y PVCs y el límite de la validación worker→CCCC.
- El runner de tesis usa el token de servicio del gateway y el token interno del control plane desde variables de entorno; no registra los valores.

## Criterios de aceptación

- El preflight rechaza un contexto distinto de Minikube antes de crear recursos.
- El playbook y el chart usan los workloads vigentes de main: gateway, outbox, control plane y worker.
- Los Secrets contienen las claves que consume el chart y no imprimen credenciales.
- Solo el gateway se expone con port-forward a 127.0.0.1; los datos de PostgreSQL y JetStream persisten.
- No se describe ni despliega un API Python duplicado ni un PVC SQLite compartido.
- La salud de Kubernetes no se presenta como prueba de ejecución de tareas en CCCC.
