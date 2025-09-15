import os
import json
import time
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime

# 1. Obtener credenciales desde la variable de entorno

# Convierte el string JSON a un diccionario
GOOGLE_CREDENTIALS = os.environ["GOOGLE_CREDENTIALS"]
try:
    creds_dict = json.loads(GOOGLE_CREDENTIALS)
except json.JSONDecodeError as e:
    raise ValueError(f"El formato de GOOGLE_CREDENTIALS no es válido: {e}")

# 2. Autenticación con Google Sheets
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SPREADSHEET_ID = "1awPSoUKQYPicbG2pHZuBb3Rscc2QEyhtUpqQ_sNF3bM"  
RANGO_A = "P3A!A:C"  # Rango donde se escribirán los datos
RANGO_B = "P3B!A:C"

def autenticar_google():
    """Crea el servicio de Google Sheets usando credenciales desde variable."""
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    service = build('sheets', 'v4', credentials=creds)
    return service

# 3. Función para añadir datos a la hoja
def agregar_datos(cuenta, tipo, precio_entrada, tp, sl, tp_pips, ciclo, ratio, paso_ratio, resultado, hora, hora_actual, ganancia, cuenta_actual):
    aprobacion = None
    if cuenta == "A":
        range = RANGO_A
    else:
        range = RANGO_B
    while not aprobacion:
        try:
            datos = [
                tipo,
                precio_entrada,
                tp,
                sl,
                tp_pips,
                ciclo,
                ratio,
                paso_ratio,
                resultado,
                hora,
                hora_actual,
                ganancia,
                cuenta_actual
            ]
            """Añade una fila con nuevos datos a la hoja."""
            service = autenticar_google()
            body = {"values": [datos]}
            result = service.spreadsheets().values().append(
                range,
                spreadsheetId=SPREADSHEET_ID,
                valueInputOption="USER_ENTERED",
                body=body
            ).execute()
    
            # Validar que se insertaron filas correctamente
            if result.get("updates", {}).get("updatedRows", 0) > 0:
                aprobacion = "ok"
                return result
            else:
                raise Exception("La respuesta fue exitosa pero no se insertó ninguna fila.")
                time.sleep(5)
    
        except Exception as e:
            print("Error al agregar datos a la hoja:", e)
            time.sleep(5)
        


