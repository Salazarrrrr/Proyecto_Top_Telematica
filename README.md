DFSha
DFSha es un prototipo de sistema de archivos distribuido. Permite
autenticarse desde una CLI, crear directorios virtuales, subir archivos,
consultar el catálogo y recuperar archivos mediante un Gateway
REST/HTTPS y un clúster de almacenamiento distribuido con gRPC.
Esta documentación describe el proyecto y el flujo de demostración
utilizado. Los nombres de archivos, comandos y rutas deben coincidir
con la versión desplegada en el repositorio.

Arquitectura
- Client: CLI de Python para autenticación, navegación de
  directorios y transferencia de archivos.
- Gateway: API REST basada en Flask. Autentica usuarios, aplica
  permisos, mantiene el catálogo de metadatos y coordina lecturas y
  escrituras.
- Cluster Java: nodos de almacenamiento que se comunican mediante
  gRPC, intercambian heartbeats y replican bloques entre pares.
- Proto: contrato compartido para las operaciones gRPC.
- Deploy: archivos de configuración y despliegue de contenedores.
El Gateway coordina las operaciones del cliente. Los bloques se
distribuyen entre los nodos responsables y las lecturas/escrituras
aplican quórums configurados. El catálogo de archivos y directorios se
conserva en el almacenamiento de metadatos del Gateway.
Requisitos
- Python y las dependencias de requirements.txt.
- Un entorno virtual Python.
- Docker y Docker Compose para ejecutar el despliegue en contenedores.
- Acceso de red al Gateway.
- Para el despliegue de laboratorio con TLS propio, el certificado CA
  correspondiente.
- Para el despliegue en AWS, las credenciales de usuario de DFSha y la
  URL HTTPS del Gateway.
Instala las dependencias desde la raíz del repositorio:
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Configurar el cliente
Despliegue AWS
Configura la URL pública HTTPS del Gateway y, si el despliegue utiliza
el certificado del laboratorio, la ruta al certificado CA
correspondiente. En el entorno utilizado para la demostración:
$env:DFS_GATEWAY_URL = "https://52.71.140.30:8443"
$env:DFS_GATEWAY_TLS_CA = "C:\Users\aceve\Desktop\Telematica_proyecto\Proyecto_Top_Telematica\Deploy\certs\ca.crt"
La IP y las rutas anteriores son específicas del entorno de
demostración. Si cambia la IP, el dominio, el equipo o el certificado,
actualiza estos valores. No publiques claves privadas, tokens ni
archivos de secretos.
Ejecución del cliente
Desde la raíz del repositorio, con el entorno virtual activado:
python -m Client.client
Para ejecutar un subcomando directamente, utiliza
python -m Client.client <comando>.
Registro, inicio de sesión y shell
Registra un usuario normal:
python -m Client.client register <usuario>
La CLI solicitará la contraseña y su confirmación. El registro público
asigna el rol de usuario normal.

Inicia sesión explícitamente con esa cuenta:
python -m Client.client login <usuario>
Después, abre el shell interactivo:
python -m Client.client shell
Dentro del shell puedes comprobar la identidad y el espacio remoto con
los comandos disponibles. Para cerrar el shell, ejecuta exit.

Importante: registra la cuenta y luego inicia sesión con esa misma
cuenta antes de realizar la demostración. No asumas que registrar un
usuario inicia automáticamente una sesión autenticada.
Comandos del shell
  Comando                             Función
  help                              Muestra los comandos disponibles.

  pwd                               Muestra la ruta remota actual.

  ls [ruta]                         Lista directorios y archivos de una
                                      ruta.

  list                              Lista archivos del directorio
                                      actual.

  cd <ruta>                         Cambia el directorio remoto actual.

  mkdir <ruta>                      Crea un directorio remoto.

  rmdir <ruta>                      Elimina un directorio remoto vacío.

  store <archivo_local>             Sube un archivo local al directorio
                                      remoto actual.

  get <nombre_o_id> [salida]        Descarga un archivo a la ruta local
                                      indicada.

  rm <nombre_o_id>                  Elimina un archivo.
  exit                              Cierra el shell.
Las rutas locales de Windows deben escribirse entre comillas si
contienen espacios.
Flujo de demostración: subir y descargar un archivo
Este ejemplo utiliza el video Parte1.mp4. Asegúrate de que exista en
la ruta local indicada.
1. Configura el cliente y autentícate:
   $env:DFS_GATEWAY_URL = "https://52.71.140.30:8443"
   $env:DFS_GATEWAY_TLS_CA = "C:\Users\aceve\Desktop\Telematica_proyecto\Proyecto_Top_Telematica\Deploy\certs\ca.crt"
   python -m Client.client login Sustentacion
   python -m Client.client shell
2. En el shell de DFSha, crea y abre un directorio:
   mkdir demostracion
   cd demostracion
   pwd
3. Sube el archivo:
   store "C:\Users\aceve\Desktop\Sustentacion Telematica\Parte1.mp4"
   La respuesta de éxito incluye file_id, el nombre del archivo y el
   número de bloques. Guarda el file_id devuelto por esa operación;
   cada subida puede generar un identificador distinto.
4. Comprueba el catálogo del directorio:
   list
5. Descarga el archivo utilizando el identificador real devuelto por
   store:
   get <file_id> "C:\Users\aceve\Desktop\Sustentacion Telematica\recuperado_Parte1.mp4"
6. Comprueba que el archivo recuperado exista y pueda reproducirse.
   Después, cierra el shell:
   exit
El comando get utiliza la sintaxis get <nombre_o_id> [salida]; no es
necesario agregar --salida dentro del shell interactivo.
Seguridad y aislamiento de usuarios
- Cada solicitud autenticada debe utilizar el token de la sesión
  correspondiente.
- Después de register, ejecuta login con el usuario registrado
  antes de abrir el shell.
- Los usuarios normales deben acceder únicamente a sus propios
  archivos y directorios.
- No compartas contraseñas, tokens de sesión, gateway.env,
  Deploy/.env, llaves privadas ni secretos.
- Conserva el volumen y los archivos de metadatos del Gateway. Los
  metadatos identifican el propietario de cada archivo y permiten
  mantener el catálogo entre reinicios.
- Los nodos de almacenamiento no deben exponerse públicamente sin las
  reglas de red y la protección TLS previstas por el despliegue.
Despliegue
Los comandos de despliegue dependen del archivo Compose y del archivo de
entorno utilizados en cada entorno. Antes de ejecutar
docker compose up, confirma que la ruta del archivo de entorno exista
y que el archivo Compose corresponda al despliegue elegido.

Para el entorno AWS utilizado en esta demostración, se ha empleado el
archivo Compose del Gateway:

sudo docker compose --env-file /home/ec2-user/gateway.env \
  -f Deploy/compose.gateway.aws.yaml up -d --build gateway
El archivo de entorno de AWS está fuera del repositorio en ese entorno.

No lo crees de nuevo ni lo reemplaces por un archivo vacío: contiene
configuración sensible y necesaria para el servicio.

Para revisar el estado de los contenedores:
sudo docker ps
Para revisar los registros del Gateway:
sudo docker logs --since 10m deploy-gateway-1
Los nombres de los contenedores y las rutas anteriores corresponden al
despliegue de referencia y pueden variar en otro entorno.
Pruebas automáticas

Desde la raíz del repositorio, ejecuta las pruebas disponibles:
.\.venv\Scripts\python.exe -m unittest discover -s Tests/Gateway -p "test_*.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s Tests/Client -p "test_*.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s Tests/Node -p "test_*.py" -v

Limitaciones conocidas
DFSha es un prototipo con coordinación central en el Gateway y catálogo
de metadatos local al Gateway. La replicación de bloques no elimina el
punto central de coordinación ni proporciona por sí sola tolerancia a la
caída del Gateway. El sistema ofrece operaciones de transferencia y
gestión de directorios por CLI/API; no equivale a un sistema de archivos
montado de forma transparente en el sistema operativo.
