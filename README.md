# Nustro proyecto es una DFSha 
Un sistema de archivos distribuido que permite almacenar y acceder a archivos de manera eficiente en un entorno distribuido, basado en una arquitectura hibrida  **Cliente-Servidor** y **Peer-to-Peer (P2P)**.

## Descripción

DFSha es un sistema de archivos distribuido diseñado bajo una arquitectura híbrida. La comunicación externa con el sistema se realiza mediante un modelo **Cliente/Servidor**, mientras que el almacenamiento y distribución de los bloques se realizan mediante una red **P2P**.

El sistema utiliza **DHT** y **Consistent Hashing** para determinar la ubicación lógica de los bloques, además de mecanismos de **replicación**, **Heartbeat** y **Broadcast** para mantener la disponibilidad y gestionar cambios en la membresía del sistema.

## Arquitectura

El proyecto está organizado en los siguientes componentes:

- **Client:** interfaz utilizada por el usuario para realizar solicitudes al sistema.

- **Gateway:** punto de entrada Cliente/Servidor encargado de autenticación,           autorización, validación y coordinación.

- **Node:** nodos P2P encargados del almacenamiento y gestión de los bloques.

- **Proto:** definición de los contratos de comunicación mediante **gRPC**.
- **Deploy:** archivos necesarios para el despliegue de los diferentes componentes.

- **Docs:** documentación técnica y de diseño del sistema.

La comunicación principal sigue el siguiente esquema:

Cliente
   |
   | REST/JSON
   v
Gateway
   |
   | gRPC
   v
Nodo P2P
   |
   | gRPC
   v
Otros nodos P2P