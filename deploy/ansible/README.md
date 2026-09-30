# Despliegue local de TRAMA en Minikube

El piloto corre en un perfil Minikube de un solo nodo dentro de WSL. Docker,
`kubectl`, Helm y Minikube deben estar disponibles desde Ubuntu WSL, y el
contexto activo de `kubectl` debe ser `minikube`. El preflight se detiene antes
de crear recursos si detecta otro contexto o si el nodo no está ejecutándose.

## Preparación

Si Ansible no está instalado en WSL, instala `ansible-core` en un entorno del
usuario:

```bash
python3 -m venv "$HOME/.local/share/trama-ansible"
"$HOME/.local/share/trama-ansible/bin/pip" install --upgrade pip ansible-core
```

Instala o inicia Minikube con Docker como runtime y selecciona su contexto:

```bash
minikube start --profile minikube --driver=docker
kubectl config use-context minikube
docker info
```

Crea el archivo cifrado fuera del repositorio. Ansible abrirá un editor para
introducir las variables; cifra el archivo con `ansible-vault` y no guardes
credenciales en un archivo versionado:

```bash
mkdir -p "$HOME/.config/trama"
chmod 700 "$HOME/.config/trama"
"$HOME/.local/share/trama-ansible/bin/ansible-vault" create \
  "$HOME/.config/trama/vault.yml"
```

El Vault debe definir estas claves YAML:

```yaml
database_url: postgresql://trama:CONTRASENA@trama-postgresql:5432/trama?sslmode=disable
redis_url: redis://trama-redis-master:6379/0
nats_url: nats://trama-nats:4222
gateway_service_account_token: REEMPLAZAR
gateway_organization_id: REEMPLAZAR
control_plane_internal_token: REEMPLAZAR
postgresql_username: trama
postgresql_password: REEMPLAZAR
postgresql_admin_password: REEMPLAZAR
```

Usa el mismo nombre y contraseña de PostgreSQL en `database_url` y en las
variables PostgreSQL. El usuario de base de datos del chart local es `trama`.
Redis queda sin autenticación y temporal para este perfil de un nodo; NATS usa
JetStream con almacenamiento persistente. Los Services internos son
`trama-postgresql`, `trama-redis-master` y `trama-nats`.

## Validar y desplegar

Desde la raíz del repositorio, valida la sintaxis y ejecuta el playbook:

```bash
"$HOME/.local/share/trama-ansible/bin/ansible-playbook" \
  -i deploy/ansible/inventory/local.yml \
  --syntax-check deploy/ansible/site.yml

"$HOME/.local/share/trama-ansible/bin/ansible-playbook" \
  -i deploy/ansible/inventory/local.yml \
  deploy/ansible/site.yml --ask-vault-pass
```

El playbook construye y carga tres imágenes locales, aplica los Kubernetes
Secrets desde stdin sin mostrarlos en logs, instala PostgreSQL, NATS y Redis
con versiones fijadas, y después instala el chart de TRAMA. Es idempotente y
no contiene tareas que borren releases, PVCs o datos.

El estado operativo se consulta con:

```bash
kubectl get pods,services,pvc -n trama
```

Solo el gateway se expone al host. Mantén el siguiente comando en ejecución y
usa `http://127.0.0.1:8080` desde Windows:

```bash
kubectl port-forward --address 127.0.0.1 -n trama \
  svc/trama-gateway 8080:8080
```

El control plane escucha en un Service `ClusterIP` y no tiene Ingress ni
port-forward al host. El control plane y los workers usan PostgreSQL
compartido; JetStream conserva su PVC y Redis es temporal en este perfil. La
preparación local no valida la coordinación productiva del worker con CCCC.
