
# DFSha: Sistema de Archivos Distribuido

## 1. Descripción del proyecto

DFSha es un sistema de archivos distribuido que permite almacenar, consultar, recuperar y administrar archivos mediante una arquitectura cliente-servidor distribuida.

El sistema utiliza un Gateway como punto de entrada para los clientes y un clúster de nodos de almacenamiento que se comunican mediante gRPC. Los archivos se gestionan a través de una interfaz de comandos y los usuarios deben autenticarse para acceder a sus recursos.

El proyecto implementa mecanismos de distribución de archivos, comunicación entre componentes, persistencia de metadatos y control de acceso por usuario.

## 2. Arquitectura del sistema

La arquitectura está compuesta por los siguientes elementos:

- Cliente: permite registrar usuarios, iniciar sesión y ejecutar operaciones sobre los archivos y directorios.
- Gateway: recibe las solicitudes de los clientes, gestiona las operaciones y coordina la comunicación con los nodos de almacenamiento.
- Clúster de almacenamiento: está compuesto por tres nodos Java que reciben y procesan las solicitudes de almacenamiento y recuperación mediante gRPC.
- Metadatos: permiten identificar los archivos almacenados y gestionar su información, ubicación y propietario.
- Seguridad: contempla autenticación de usuarios, validación de acceso a los archivos y comunicación HTTPS entre el cliente y el Gateway.

### Flujo general

```
              CLIENTE
                 |
                 | HTTPS
                 v
              GATEWAY
                 |
                 | gRPC
        +--------+--------+
        |        |        |
        v        v        v
     NODO 1   NODO 2   NODO 3
     Java     Java     Java
        |        |        |
        +--------+--------+
                 |
          Almacenamiento
          distribuido
```

El cliente se comunica con el Gateway mediante HTTPS. El Gateway coordina las operaciones con los nodos de almacenamiento a través de gRPC.

## 3. Tecnologías utilizadas

- Python: implementación del cliente y del Gateway.
- Java: implementación de los nodos de almacenamiento.
- gRPC: comunicación entre el Gateway y los nodos.
- HTTPS/TLS: protección de la comunicación entre el cliente y el Gateway.
- Docker y Docker Compose: construcción y ejecución de los servicios.
- Amazon EC2: infraestructura utilizada para el despliegue en AWS.
- AWS VPC: red que permite la comunicación entre la instancia pública del Gateway y los nodos privados.

## 4. Requisitos previos

Para ejecutar el proyecto localmente se requiere:

- Python instalado.
- Java y las herramientas de compilación requeridas por el proyecto.
- Docker y Docker Compose.
- Git, si se desea clonar el repositorio.
- Certificados TLS y variables de entorno configurados según el entorno de ejecución.

Para utilizar el despliegue en AWS también se necesita acceso a la instancia del Gateway y conectividad con los nodos privados.

## 5. Estructura del proyecto

La estructura principal del proyecto se organiza en los siguientes componentes:

```
Proyecto_Top_Telematica/
├── Client/
│   └── client.py
├── Gateway/
│   ├── app.py
│   └── cluster_comunication/
│       └── cluster_core.py
├── Deploy/
│   ├── compose.yaml
│   ├── compose.gateway.aws.yaml
│   └── certs/
├── README.md
└── ...
```

La estructura anterior representa los componentes principales. Pueden existir otros archivos y directorios relacionados con los nodos Java, los servicios, los modelos de datos, las pruebas y la configuración.

## 6. Configuración del cliente

Antes de utilizar el cliente, es necesario configurar la dirección del Gateway y el certificado de la autoridad certificadora.

En PowerShell, desde el directorio del proyecto, se pueden definir las variables de entorno de la siguiente manera:

```
$env:DFS_GATEWAY_URL = "https://52.71.140.30:8443"
$env:DFS_GATEWAY_TLS_CA = "C:\Users\aceve\Desktop\Telematica_proyecto\Proyecto_Top_Telematica\Deploy\certs\ca.crt"
```

Importante: la dirección IP y la ruta del certificado corresponden a un entorno específico de despliegue. Deben reemplazarse si cambian la infraestructura, el certificado o la ubicación del proyecto.

Para ejecutar los comandos de Python se recomienda activar el entorno virtual del proyecto, si está configurado:

```
.\.venv\Scripts\Activate.ps1
```

## 7. Registro e inicio de sesión

El sistema permite registrar usuarios e iniciar sesión desde el cliente.

### Registrar un usuario

```
python -m Client.client register Sustentacion
```

El programa solicitará una contraseña y su confirmación. Si el registro es exitoso, mostrará un mensaje de confirmación.

### Iniciar sesión

```
python -m Client.client login Sustentacion
```

Después de iniciar sesión, el usuario podrá abrir la interfaz de comandos.

Nota: se debe iniciar sesión con el usuario correspondiente antes de realizar operaciones. La autenticación permite asociar las operaciones al usuario que está utilizando el sistema.

## 8. Interfaz de comandos

Para abrir la interfaz interactiva se ejecuta:

```
python -m Client.client shell
```

Desde la interfaz se pueden realizar operaciones sobre directorios y archivos.

### Comandos principales

| Comando                      | Descripción                                                  |
| ---------------------------- | ------------------------------------------------------------ |
| `mkdir <directorio>`         | Crea un directorio.                                          |
| `cd <directorio>`            | Cambia al directorio indicado.                               |
| `pwd`                        | Muestra la ruta del directorio actual.                       |
| `list`                       | Lista los elementos disponibles en el directorio actual.     |
| `store <ruta_archivo>`       | Almacena un archivo en el sistema distribuido.               |
| `get <nombre_o_id> [salida]` | Recupera un archivo y permite especificar su ruta de salida. |
| `exit`                       | Finaliza la interfaz interactiva.                            |

La sintaxis exacta de los comandos depende de la implementación disponible en el cliente.

## 9. Ejemplo de uso

A continuación, se presenta un flujo de prueba para demostrar las funcionalidades principales del sistema.

### Paso 1. Crear un directorio

Dentro de la interfaz interactiva:

```
mkdir demostracion
```

### Paso 2. Acceder al directorio

```
cd demostracion
```

### Paso 3. Verificar la ubicación actual

```
pwd
```

### Paso 4. Almacenar un archivo

Se puede almacenar un archivo de prueba indicando su ruta completa:

```
store "C:\Users\aceve\Desktop\Sustentacion Telematica\Parte1.mp4"
```

Si la operación se completa correctamente, el sistema devuelve un identificador del archivo. Este identificador debe conservarse para realizar operaciones posteriores.

### Paso 5. Consultar los archivos

```
list
```

Este comando permite verificar los elementos disponibles en el directorio actual.

### Paso 6. Recuperar un archivo

Para recuperar el archivo, se utiliza el identificador obtenido durante el almacenamiento:

```
get <ID_DEL_ARCHIVO> "C:\Users\aceve\Desktop\Sustentacion Telematica\recuperado_Parte1.mp4"
```

Se debe reemplazar `<ID_DEL_ARCHIVO>` por el identificador real generado por el sistema, sin escribir los símbolos `<` y `>`.

### Paso 7. Finalizar la sesión interactiva

```
exit
```

Este flujo permite comprobar el registro, la autenticación, la creación de directorios, el almacenamiento, la consulta y la recuperación de archivos.

## 10. Despliegue en AWS

El proyecto cuenta con una configuración de despliegue en AWS mediante instancias EC2 y Docker Compose.

La arquitectura desplegada utiliza:

- Una instancia pública para ejecutar el Gateway.
- Tres instancias privadas para los nodos de almacenamiento.
- Una VPC para organizar la red.
- Un grupo de seguridad para controlar el tráfico permitido.
- HTTPS para el acceso de los clientes.
- gRPC para la comunicación entre el Gateway y los nodos.

### Configuración del Gateway

En el entorno desplegado, el archivo de variables de entorno se encuentra en:

```
/home/ec2-user/gateway.env
```

Desde el directorio raíz del proyecto en la instancia del Gateway, se puede reconstruir y levantar el servicio con:

```
sudo docker compose --env-file /home/ec2-user/gateway.env -f Deploy/compose.gateway.aws.yaml up -d --build --force-recreate gateway
```

Para consultar el estado de los contenedores:

```
sudo docker compose --env-file /home/ec2-user/gateway.env -f Deploy/compose.gateway.aws.yaml ps
```

Para consultar los registros del Gateway:

```
sudo docker logs deploy-gateway-1
```

Estos comandos corresponden a la configuración de despliegue utilizada en el proyecto. Si se modifican los nombres de los servicios o contenedores, deben ajustarse los comandos.

### Seguridad de la red

La instancia del Gateway funciona como punto de entrada público. Los nodos de almacenamiento se encuentran en subredes privadas y deben permitir el tráfico gRPC únicamente desde el grupo de seguridad autorizado del Gateway.

No se recomienda exponer directamente los puertos de los nodos de almacenamiento a Internet.

## 11. Seguridad y control de acceso

El sistema contempla los siguientes mecanismos:

- Registro e inicio de sesión de usuarios.
- Identificación del propietario de los archivos mediante metadatos.
- Validación de permisos al acceder a los archivos.
- Comunicación HTTPS entre el cliente y el Gateway.
- Comunicación gRPC entre el Gateway y los nodos.
- Restricción del acceso de red a los nodos privados mediante grupos de seguridad de AWS.

Las credenciales y los certificados deben manejarse de forma segura. Los archivos de configuración que contengan secretos no deben publicarse en repositorios públicos.

## 12. Pruebas funcionales

Para validar el funcionamiento del sistema se recomienda realizar las siguientes pruebas:

1. Registrar un usuario nuevo.
2. Iniciar sesión con el usuario registrado.
3. Crear un directorio.
4. Almacenar un archivo de prueba.
5. Consultar el listado de archivos.
6. Recuperar el archivo mediante su identificador.
7. Comprobar que el archivo recuperado se pueda abrir y que su contenido coincida con el original.
8. Verificar que un usuario no pueda acceder a archivos pertenecientes a otro usuario.
9. Comprobar la comunicación entre el Gateway y los nodos de almacenamiento.
10. Revisar los registros de los servicios cuando se presenten errores.

Las pruebas deben ejecutarse en el entorno correspondiente, ya sea local o desplegado en AWS.

## 13. Limitaciones y consideraciones

El comportamiento del sistema depende de la disponibilidad del Gateway, de los nodos y de la conectividad entre los componentes.

En particular:

- Si el Gateway no puede comunicarse con los nodos necesarios, algunas operaciones de almacenamiento o recuperación pueden fallar.
- La recuperación de archivos requiere utilizar un identificador válido o un nombre reconocido por el sistema.
- La configuración de certificados y variables de entorno debe coincidir con el entorno utilizado.
- Las pruebas de disponibilidad y consistencia deben realizarse para verificar el comportamiento ante la caída de uno o más nodos.
- Las características de replicación, tolerancia a fallos y recuperación automática deben evaluarse de acuerdo con la implementación efectiva del proyecto.

## 14. Autores

Proyecto desarrollado como parte de la asignatura de Telemática.

Proyecto: DFSha, sistema de archivos distribuido.
Emilton Mena Acevedo 
Mariana Hincapie Henao
Estaban Zalasar 

