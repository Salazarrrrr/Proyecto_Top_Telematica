BLOCL_SIZE = 1024 * 1024 * 200  # 200 MB

def dividir_archivo(ruta_archivo):
    with open(ruta_archivo, "rb") as archivo:   #Creo que el rb sirve para que lea cualquir archivo 
         posicion = 0
         while True:
            contenido = archivo.read(BLOCL_SIZE)
            if not contenido:
                break
            yield posicion, contenido
            posicion += 1
