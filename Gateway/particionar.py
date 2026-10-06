import os


BLOCK_SIZE = int(os.getenv("DFS_BLOCK_SIZE", str(64 * 1024 * 1024)))
if BLOCK_SIZE <= 0:
    raise ValueError("DFS_BLOCK_SIZE debe ser mayor que cero")

def dividir_archivo(ruta_archivo):
    with open(ruta_archivo, "rb") as archivo:
        posicion = 0
        while True:
            contenido = archivo.read(BLOCK_SIZE)
            if not contenido:
                break
            yield posicion, contenido
            posicion += 1
