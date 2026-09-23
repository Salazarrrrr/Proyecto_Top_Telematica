from particionar import dividir_archivo

for posicion, contenido in dividir_archivo("archivo_prueba.txt"):
    print(f"Bloque {posicion}: {len(contenido)} bytes")