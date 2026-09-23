from dataclasses import dataclass

#Aqui estamos definiendo la clase Bloque que representa un bloque de datos en el sistema de almacenamiento distribuido.
# Cada bloque tiene un identificador único (block_id), un identificador del archivo al que pertenece (file_id), una posición dentro del archivo (posicion), el contenido del bloque en bytes (contenido)
#  y un checksum para verificar la integridad de los datos (checksum).

@dataclass
class Bloque:
    block_id: str
    file_id: str
    posicion: int
    contenido: bytes
    checksum: str

