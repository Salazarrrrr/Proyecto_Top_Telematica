# Despliegue distribuido en AWS

Este despliegue usa cuatro instancias EC2 dentro de la misma VPC: un Gateway público y tres nodos privados de almacenamiento. El Gateway se publica mediante Caddy y HTTPS; los nodos aceptan gRPC desde el Security Group del Gateway y entre miembros del Security Group de nodos para permitir la replicación directa.

## 1. Recursos en AWS

Usa Amazon Linux 2023 y crea estas instancias en la misma VPC:

| Nombre | Tipo sugerido | Disco | Security Group |
|---|---:|---:|---|
| `dfsha-gateway` | `t3.medium` | 30 GiB | `sg-dfsha-gateway` |
| `dfsha-node1` | `t3.small` | 20 GiB | `sg-dfsha-nodes` |
| `dfsha-node2` | `t3.small` | 20 GiB | `sg-dfsha-nodes` |
| `dfsha-node3` | `t3.small` | 20 GiB | `sg-dfsha-nodes` |

Asigna una Elastic IP al Gateway. Crea un registro A, por ejemplo `dfs.tudominio.com`, que apunte a esa IP.

Configura los Security Groups así:

| Security Group | Entrada | Origen |
|---|---|---|
| `sg-dfsha-gateway` | TCP 22 | IP pública de administración |
| `sg-dfsha-gateway` | TCP 80 y 443 | `0.0.0.0/0` |
| `sg-dfsha-nodes` | TCP 22 | IP pública de administración |
| `sg-dfsha-nodes` | TCP 50051 | `sg-dfsha-gateway` |
| `sg-dfsha-nodes` | TCP 50051 | `sg-dfsha-nodes` |

No abras TCP 50051 a Internet. Anota las tres IP privadas de los nodos y el dominio público del Gateway.

## 2. Preparar configuración local

Desde la raíz del proyecto en el computador de administración, genera secretos y certificados. Sustituye los valores de ejemplo:

```powershell
.\.venv\Scripts\python.exe Deploy/generar_config_aws.py `
  --public-host "dfs.tudominio.com" `
  --nodes "10.0.1.11,10.0.1.12,10.0.1.13"

.\.venv\Scripts\python.exe Deploy/generar_certificados.py `
  --gateway-host "dfs.tudominio.com" --force
```

El primer comando crea `Deploy/aws/gateway.env` y un archivo `nodeN.env` para cada nodo. Muestra las contraseñas iniciales de `admin` y `demo` una sola vez. Estos archivos están ignorados por Git.

## 3. Instalar dependencias en cada instancia

Conéctate por SSH a cada una de las cuatro instancias y ejecuta:

```bash
sudo dnf update -y
sudo dnf install -y git docker
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user
exit
```

Conéctate de nuevo y descarga el proyecto:

```bash
git clone https://github.com/Salazarrrrr/Proyecto_Top_Telematica.git
cd Proyecto_Top_Telematica
```

## 4. Distribuir secretos y certificados

Desde el computador de administración, copia `gateway.env` y `ca.crt` al Gateway. Copia cada archivo `nodeN.env`, junto con `ca.crt`, `nodes.crt` y `nodes.key`, al nodo correspondiente. Cada destino ya debe tener el repositorio clonado.

Ejemplo para Gateway:

```powershell
scp -i "C:\ruta\llave.pem" Deploy\aws\gateway.env ec2-user@IP_PUBLICA_GATEWAY:~/Proyecto_Top_Telematica/Deploy/.env
scp -i "C:\ruta\llave.pem" Deploy\certs\ca.crt ec2-user@IP_PUBLICA_GATEWAY:~/Proyecto_Top_Telematica/Deploy/certs/ca.crt
```

Ejemplo para `node1`:

```powershell
scp -i "C:\ruta\llave.pem" Deploy\aws\node1.env ec2-user@IP_PUBLICA_NODE1:~/Proyecto_Top_Telematica/Deploy/.env
scp -i "C:\ruta\llave.pem" Deploy\certs\ca.crt Deploy\certs\nodes.crt Deploy\certs\nodes.key ec2-user@IP_PUBLICA_NODE1:~/Proyecto_Top_Telematica/Deploy/certs/
```

Repite la copia para `node2` y `node3`, usando su archivo de configuración respectivo. No copies `ca.key`, `gateway.key` ni el directorio `Deploy/aws` a las instancias.

## 5. Iniciar los nodos

En cada nodo, desde la raíz del repositorio:

```bash
docker compose --env-file Deploy/.env -f Deploy/compose.node.aws.yaml up --build -d
docker compose --env-file Deploy/.env -f Deploy/compose.node.aws.yaml ps
```

Los tres nodos deben mostrar estado `healthy`.

## 6. Iniciar Gateway público

En la instancia Gateway:

```bash
docker compose --env-file Deploy/.env -f Deploy/compose.gateway.aws.yaml up --build -d
docker compose --env-file Deploy/.env -f Deploy/compose.gateway.aws.yaml ps
curl https://dfs.tudominio.com/health
```

El primer inicio de Caddy obtiene un certificado público. Para que funcione, el registro DNS debe apuntar a la Elastic IP y los puertos 80 y 443 deben estar abiertos.

## 7. Prueba remota

Desde otro computador:

```powershell
$env:DFS_GATEWAY_URL = "https://dfs.tudominio.com"
python -m Client.client login demo
python -m Client.client shell
```

No se configura `DFS_GATEWAY_TLS_CA`: el certificado público se valida automáticamente.

Con la cuenta `admin`, crea un usuario de prueba para el profesor:

```powershell
python -m Client.client login admin
python -m Client.client create-user profesor --rol usuario
```

## 8. Verificación de arquitectura

En la demostración, muestra el estado de los cuatro grupos de contenedores y explica que los clientes se conectan al Gateway por HTTPS. El Gateway coordina autenticación y metadatos; los tres nodos independientes almacenan y replican bloques por gRPC privado mediante sus IP privadas.
