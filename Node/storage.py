import hashlib # Investigue y esta libreria es para generar un hash de los datos que se almacenan en el nodo
#Y creo que es útil para verificar la integridad de los datos y asegurarse de que no han sido alterados.

from pathlib import Path
from Node.models import Bloque #Aqui llamamos a la clase Bloque que definimos en el archivo models.py
#para poder usarla en este archivo para el almacenamiento de los bloques de datos en el nodo.

#debemos pensar en la clase para el almacenamiento de los bloques de datos en el nodo.
# La clase debe tener métodos para almacenar, recuperar y eliminar bloques de datos

class Almacenamiento:
