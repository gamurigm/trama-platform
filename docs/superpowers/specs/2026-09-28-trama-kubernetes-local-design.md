# Diseño: piloto local de Kubernetes para TRAMA

**Fecha:** 2026-09-29
**Estado:** alineado con la arquitectura distribuida de main; pendiente de validación operativa
**Alcance:** despliegue local de desarrollo en Minikube dentro de WSL

## Objetivo

Desplegar en Minikube el stack distribuido vigente de TRAMA con Ansible y Helm. El piloto debe usar PostgreSQL como estado compartido del gateway, el control plane y el worker; NATS JetStream como transporte durable; y Redis para el rate limit del gateway. Solo el gateway queda accesible desde el host, ligado a localhost.

El piloto valida empaquetado y operación local. No declara que la plataforma esté lista para producción ni que el worker complete el flujo hacia CCCC.

## Diseño aprobado

- Minikube corre dentro de WSL con un solo nodo. Ansible también se ejecuta desde WSL y comprueba el contexto minikube antes de aplicar cambios.
- Un namespace trama contiene TRAMA y sus dependencias locales.
- Ansible instala PostgreSQL, NATS con JetStream y Redis como releases Helm separados y con versiones fijadas. PostgreSQL y JetStream conservan sus datos en PVCs; Redis es efímero en este perfil.
- El chart vigente ya despliega gateway Go, outbox, control plane Python y worker Python, además del Job de migraciones. El perfil local ajusta sus imágenes y réplicas; no añade una segunda API Python ni un PVC SQLite.
- Las imágenes de TRAMA se construyen localmente en WSL y se cargan en Minikube. No se requiere un registry externo.
- Cada Deployment de TRAMA usa una réplica fija; HPA y PDB quedan desactivados para el piloto.
- Gateway, control plane y worker usan PostgreSQL compartido. El outbox publica eventos a NATS JetStream y Redis gestiona el rate limit.
- Los Services son internos. El único acceso desde el host es un port-forward del gateway ligado a 127.0.0.1.
- Ansible carga desde un Vault cifrado las URLs de dependencias, la identidad de servicio del gateway, el token interno del control plane y las credenciales de PostgreSQL. Los Secret se aplican por stdin y se ocultan de los logs.

El flujo operativo queda así:

~~~mermaid
flowchart LR
    Dev[Desarrollador en WSL] --> Ansible
    Ansible --> Helm
    Helm --> Infra[PostgreSQL · NATS JetStream · Redis]
    Helm --> App[Gateway · Outbox · Control plane · Worker]
    App --> Infra
    Dev -->|port-forward en localhost| Gateway[Gateway Service]
~~~

## Límites y condiciones

El piloto usa un solo nodo y réplicas fijas. PostgreSQL conserva el estado compartido; no se monta un PVC SQLite entre Pods. El resultado no demuestra alta disponibilidad ni recuperación ante desastres.

La salud de Kubernetes y la visibilidad de eventos no demuestran que el worker haya ejecutado una tarea en CCCC. Esa integración requiere una prueba separada contra el servicio CCCC.

Ansible debe detenerse antes de desplegar si el contexto no es minikube, si el perfil está detenido o si faltan secretos. Un upgrade normal no elimina el namespace ni PVCs.

## Decisión sobre Harbor, Keycloak y Grafana

| Componente | Decisión para el piloto | Cuándo incorporarlo |
|---|---|---|
| Harbor | No instalar. Las imágenes locales se cargan directamente en Minikube. | Cuando se requiera un registry privado compartido. |
| Keycloak | No instalar. El gateway usa la autenticación de servicio configurada para el piloto. | Cuando se defina SSO o gestión centralizada de usuarios. |
| Grafana | No instalar. El chart no configura métricas Prometheus de aplicación. | Después de definir instrumentación, retención y objetivos de alertas. |

## Fuera de alcance

- Clúster de producción o de varios nodos, Ingress público, TLS externo y recuperación ante desastres.
- Cambios funcionales para completar la coordinación del worker con CCCC.
- Harbor, Keycloak, Prometheus y Grafana en el clúster local.
- Escalado horizontal de los Deployments de TRAMA.
- Cambios de producto, UI o contratos públicos de API.

## Criterios de aceptación

1. Ansible valida el contexto y el estado de Minikube antes de crear recursos.
2. El playbook instala o actualiza los releases y puede repetirse sin duplicarlos.
3. Gateway, outbox, control plane y worker quedan listos con una réplica cada uno.
4. PostgreSQL, NATS JetStream y Redis quedan accesibles mediante Services internos; los datos de PostgreSQL y JetStream conservan sus PVCs.
5. La autenticación del gateway y el token interno del control plane se suministran desde Secrets; no se guardan credenciales en Git ni en values.
6. Solo el gateway tiene un port-forward hacia 127.0.0.1; el control plane no se expone al host.
7. La documentación distingue la salud de Kubernetes de la validación funcional del worker hacia CCCC.

## Evidencia del repositorio

El chart vigente en deploy/helm/trama-gateway contiene gateway, outbox, control plane, worker y migraciones. El control plane y el worker usan PostgreSQL compartido; JetStream transporta los eventos. deploy/docker-compose.gateway.yml refleja esta arquitectura con PostgreSQL, NATS, Redis y los cuatro workloads de TRAMA.
