import logs
import Gestion_3p_inversa

print ("Código desde inicio")

hilo_a = threading.Thread(target=Gestion_3p_inversa.main)
hilo_b = threading.Thread(target=logs.main)

hilo_a.start()
hilo_b.start()

hilo_a.join()
hilo_b.join()

print("Programa terminado")
sys.exit()
