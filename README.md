# DFSha

Prototipo de sistema de archivos distribuido con acceso Cliente/Servidor por REST/JSON y almacenamiento en nodos gRPC. El Gateway divide archivos en bloques, asigna réplicas por hashing consistente y registra metadatos de control; los nodos guardan el contenido y verifican su checksum SHA-256.

## Componentes

- `Client`: CLI con operaciones de archivos y directorios y shell remoto.
- `Gateway`: API Flask, catálogo de archivos, asignación de nodos, quórums y operaciones de membresía.
- `Node`: servicio gRPC de bloques con escritura atómica y verificación de integridad.
- `Proto`: contrato gRPC compartido.
- `Cluster`: implementación Java de referencia para el anillo hash; el Gateway Python es el coordinador que usa el prototipo actual.

## Requisitos y ejecución local

Instala las dependencias Python en un entorno virtual con `pip install -r requirements.txt`. Ejecuta desde la raíz del repositorio.

Para ejecutar las pruebas automáticas:

```powershell
.\.venv\Scripts\python.exe -m unittest Gateway.test_archivos Gateway.test_cluster Gateway.test_auth Client.test_client_security -v
```

Para una demostración reproducible con contenedores, ejecuta `Deploy/configurar_entorno.ps1`, que genera secretos locales ignorados por Git y certificados de laboratorio. Luego inicia el clúster con `docker compose --env-file Deploy/.env -f Deploy/compose.yaml up --build -d`. El Gateway queda en `https://localhost:8443`; configura el cliente con `DFS_GATEWAY_URL=https://localhost:8443` y `DFS_GATEWAY_TLS_CA=<ruta absoluta a Deploy/certs/ca.crt>`. El certificado/CA generado es solo para el laboratorio. No subas `Deploy/.env` ni `Deploy/certs` al repositorio.

Prueba el despliegue Compose desde PowerShell. Docker Desktop debe estar iniciado. En una terminal, arranca el clúster:

```powershell
docker compose --env-file Deploy/.env -f Deploy/compose.yaml up --build -d
```

En otra terminal, configura el cliente e inicia sesión. Si creaste el entorno con `configurar_entorno.ps1`, usa las contraseñas que el script mostró al finalizar:

```powershell
$env:DFS_GATEWAY_URL = "https://localhost:8443"
$env:DFS_GATEWAY_TLS_CA = (Resolve-Path Deploy/certs/ca.crt).Path
$env:DFS_DEFAULT_USER = "demo"
$python = ".\.venv\Scripts\python.exe"

& $python -m Client.client login demo

Set-Content -NoNewline -Path .\prueba.txt -Value "prueba DFSha"
& $python -m Client.client store .\prueba.txt
& $python -m Client.client list
& $python -m Client.client get prueba.txt --salida .\copia.txt
Get-FileHash .\prueba.txt -Algorithm SHA256
Get-FileHash .\copia.txt -Algorithm SHA256
& $python -m Client.client delete prueba.txt
& $python -m Client.client logout
docker compose --env-file Deploy/.env -f Deploy/compose.yaml down
```

Genera una llave AES-256 para cada nodo y consérvala fuera del repositorio. En cada terminal de nodo, antes de iniciarlo:

```powershell
$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$env:DFS_STORAGE_KEY = [Convert]::ToBase64String($bytes)
```

Abre tres terminales para nodos. Cambia puerto y directorio en cada una:

```powershell
$env:DFS_NODE_PORT = "50051"
$env:DFS_NODE_STORAGE = "almacenamiento_bloques\nodo1"
python -m Node.server
```

En otra terminal registra las direcciones y arranca el Gateway:

```powershell
$env:DFS_NODES = "localhost:50051,localhost:50052,localhost:50053"
$env:DFS_REPLICATION_FACTOR = "3"
$env:DFS_READ_QUORUM = "2"
$env:DFS_WRITE_QUORUM = "2"
$env:DFS_BLOCK_SIZE = "67108864"
$env:DFS_USER_PASSWORDS = '{"admin":"CAMBIAR_PASSWORD_ADMIN","ana":"CAMBIAR_PASSWORD_ANA"}'
$env:DFS_USER_ROLES = '{"admin":"admin","ana":"usuario"}'
$env:DFS_ADMIN_TOKEN = "token-administrador-secreto"
python -m Gateway.app
```

`DFS_USERS` mantiene compatibilidad con tokens fijos. El flujo recomendado usa `DFS_USER_PASSWORDS`: el Gateway crea inicialmente `admin` (rol administrador) y `demo` (rol usuario), guarda las contraseñas con PBKDF2 y emite sesiones temporales. `configurar_entorno.ps1` genera contraseñas aleatorias y las muestra una sola vez. El archivo `metadata/usuarios.json` queda en el volumen del Gateway y no se sube a Git.

Para usar sesiones desde la CLI:

```powershell
$env:DFS_GATEWAY_URL = "https://localhost:8443"
$env:DFS_GATEWAY_TLS_CA = (Resolve-Path Deploy/certs/ca.crt).Path
$env:DFS_DEFAULT_USER = "demo"
& .\.venv\Scripts\python.exe -m Client.client login demo
& .\.venv\Scripts\python.exe -m Client.client whoami
& .\.venv\Scripts\python.exe -m Client.client create-user ana --rol usuario
& .\.venv\Scripts\python.exe -m Client.client shell
& .\.venv\Scripts\python.exe -m Client.client logout
```

Solo una sesión con rol `admin` puede crear usuarios mediante `POST /auth/users`; los usuarios normales únicamente acceden a sus propios archivos. `POST /auth/login`, `POST /auth/logout` y `GET /auth/me` completan el ciclo de sesión.

Los nodos escuchan solo en `127.0.0.1` por defecto. Las rutas de diagnóstico `/blocks` están desactivadas si no configuras `DFS_ADMIN_TOKEN` y requieren ese token aparte. `GET /health` no requiere autenticación y permite que Docker o un balanceador comprueben la disponibilidad del Gateway.

Los nodos cifran los bloques en disco con AES-GCM y requieren `DFS_STORAGE_KEY`; usa una llave distinta por nodo y protégela con un gestor de secretos. Para red remota configura además `DFS_NODE_BIND=0.0.0.0`, `DFS_NODE_TLS_CERT` y `DFS_NODE_TLS_KEY` en cada nodo, `DFS_NODE_TLS_CA` y `DFS_NODE_TLS_REQUIRED=1` en el Gateway, y un `DFS_NODE_TOKEN` compartido. Se puede habilitar autenticación mutua TLS con `DFS_NODE_CLIENT_CA` en el nodo y certificado/llave de cliente en el Gateway. Para exponer REST, configura `DFS_GATEWAY_BIND`, `DFS_GATEWAY_TLS_CERT`, `DFS_GATEWAY_TLS_KEY` y usuarios mediante `DFS_USER_PASSWORDS` o `DFS_USERS`; en el cliente define `DFS_GATEWAY_URL=https://...`.

Para compatibilidad, la CLI aún admite un token individual configurado en `DFS_USER_TOKEN`; el flujo de sesión es el recomendado.

```powershell
$env:DFS_DEFAULT_USER = "ana"
$env:DFS_USER_TOKEN = "token-largo-ana"
python -m Client.client store .\archivo.pdf --usuario ana
python -m Client.client list --usuario ana
python -m Client.client get archivo.pdf --salida .\copia.pdf --usuario ana
python -m Client.client delete archivo.pdf --usuario ana
```

El cliente guarda el token de sesión en `.dfsha_session.json` dentro del perfil del usuario. El Gateway deriva el propietario de ese token y no confía en el usuario enviado como parámetro. Para archivos grandes, ajusta `DFS_MAX_UPLOAD_BYTES`; el tamaño de bloque se controla con `DFS_BLOCK_SIZE` (64 MiB por defecto). El Gateway guarda el catálogo en `metadata/archivos.json`; conserva esa carpeta para mantener los metadatos entre reinicios.

El factor de replicación se puede cambiar en ejecución mediante `PUT /cluster/replication`, pero esa operación exige `DFS_ADMIN_TOKEN`. El valor se guarda en `metadata/cluster.json` y se recupera al reiniciar el Gateway. El nuevo factor solo se confirma después de alcanzar el quórum de escritura; si hay nodos caídos, las limpiezas pendientes se reintentan durante los heartbeats.

## API principal

- `POST /files`: recibe el archivo como `multipart/form-data` en el campo `archivo` y el usuario en `usuario`.
- `GET /files?usuario=...`: lista los archivos del usuario autenticado.
- `GET /directories?path=...`: lista contenido del directorio virtual del usuario.
- `POST /directories` con `{"path":"/docs"}` y `DELETE /directories?path=/docs`: crea o elimina directorios vacíos.
- `GET /files/<file_id>?usuario=...`: reconstruye y entrega el archivo en streaming binario.
- `DELETE /files/<file_id>?usuario=...`: elimina los bloques y los metadatos.
- `GET /cluster`: informa nodos, estado de disponibilidad, N, R y W.
- `POST /cluster/rebalance`: registra un nodo, distribuye las réplicas según el anillo actualizado y reporta cualquier limpieza pendiente.
- `DELETE /cluster/nodes/<direccion>`: salida controlada; migra los bloques antes de retirar el nodo.
- `PUT /cluster/replication` con `{"factor": N}`: ajusta N y confirma primero las copias destino; reporta y reintenta la limpieza de excedentes si un nodo no está disponible.
- `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`: ciclo de vida de sesiones.
- `POST /auth/users` con `{"usuario":"...","password":"...","rol":"usuario|admin"}`: creación restringida a administradores.

El CLI transmite el archivo local al Gateway con multipart, por lo que el cliente y el servidor pueden estar en equipos distintos. Ofrece `store`, `get`, `list`, `ls`, `mkdir`, `rmdir` y un `shell` interactivo con `cd`, `pwd` y `rm`. Todas las solicitudes HTTP usan `Authorization: Bearer ...` cuando se configura autenticación.

## Estado y límites del prototipo

El clúster exige W mayoritario y R + W > N para asegurar intersección entre quórums. Una lectura solo acepta contenido que alcance R; si hay réplicas divergentes sin un valor con quórum, falla de forma segura en vez de escoger una copia arbitraria. Al agregar un nodo, valida las copias destino antes de limpiar las réplicas fuera del anillo. El metadato del archivo solo se publica después de completar todos sus bloques, y cada escritura de bloque usa reemplazo atómico para que una lectura no vea un archivo parcialmente escrito.

El Gateway hace heartbeats gRPC cada cinco segundos, actualiza la membresía y difunde su vista a los nodos. La capacidad libre se consulta en cada heartbeat. Al cambiar la membresía, el Gateway intenta recuperar las réplicas que aún cumplen R y W y limpia copias que quedaron fuera del anillo. Para despliegues remotos, activa TLS en gRPC y HTTPS en REST con certificados confiables.

Siguen pendientes la tolerancia a la caída del propio Gateway y la replicación del catálogo: esta versión usa coordinación central y un catálogo JSON local. Tampoco implementa acceso aleatorio con `open/read/write/lock` ni un montaje transparente como sistema de archivos del sistema operativo; ofrece transferencia de archivos y gestión de directorios por CLI/API.

La guía específica del Hito 3 no estaba entre los archivos disponibles. Las operaciones de salida/rebalanceo, cambio dinámico de N y concurrencia descritas aquí se implementaron con base en la arquitectura y especificaciones compartidas por el equipo.
