import threading
import sys
import Operaciones_3pA_demo 
import Operaciones_3pB_demo
from queue import Queue, Empty
import logs
import exportar_datos
import pandas as pd
import requests
import json
import time

print("Código desde inicio")
señal_A = Queue()
señal_B = Queue()

# Crear hilo para ejecutar a.main()
hilo_a = threading.Thread(target=Operaciones_3pA_demo.main, args=(señal_A, señal_B))
hilo_b = threading.Thread(target=Operaciones_3pB_demo.main, args=(señal_A, señal_B))
hilo_c = threading.Thread(target=logs.main)
# Crear hilo para ejecutar b.main()

# Iniciar ambos hilos
hilo_a.start()
hilo_b.start()
hilo_c.start()

# Esperar a que ambos terminen (esto nunca pasará si los bucles son infinitos)
hilo_a.join()
hilo_b.join()

print("Programa terminado")
sys.exit()



