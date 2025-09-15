from datetime import datetime
from zoneinfo import ZoneInfo
from queue import Queue, Empty
import pandas as pd
import exportar_datos
import requests
import json
import time
import sys
import os

ACCESS_TOKEN = os.environ["TOKEN_A"]
ACCOUNT_ID_A1 = os.environ["ID_A"]
ACCOUNT_ID_A2 = os.environ["ID_A2"]
OANDA_URL = 'https://api-fxpractice.oanda.com/v3'  # práctica = demo

HEADERS = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {ACCESS_TOKEN}'
}


sys.stdout.reconfigure(line_buffering=True)

# Datos SMA
velas_SMA = 11
periodo_SMA = 10
temporalidad_SMA = "M10"

# Gestión 3P
paso_ratio_A1 = 0 # No modificar
paso_ratio_A2 = 0 # No modificar
ciclo_A1 = 0 # No modificar
ciclo_A2 = 0 # No modificar
ratios = ["1.640396559963", "1.640396559963", "1.640396559963", "1.640396559963", "1.640396559963", "1.640396559963", "1.640396559963", "1.640396559963", "0.95", "0.9", "0.85"]
porcentajes = ["0.000617884409", "0.001013575458", "0.001662665695", "0.002727431087", "0.004474068572", "0.007339246695", "0.012039275031", "0.019749185346", "0.018761726079", "0.016885553471", "0.01435272045"]
indices_ratios = [-8, -7, -6, -5, -4, -3, -2, -1, 0, 1, 2]
serie_ratios = pd.Series(ratios, index=indices_ratios)
serie_porcentajes = pd.Series(porcentajes, index=indices_ratios)
ratio_A1 = float(serie_ratios[paso_ratio_A1])
ratio_A2 = float(serie_ratios[paso_ratio_A2])
porcentaje_A1 = float(serie_porcentajes[paso_ratio_A1])
porcentaje_A2 = float(serie_porcentajes[paso_ratio_A2])

def restriccion(momento):
    hora_franja = datetime.now(ZoneInfo("America/Bogota"))
    dia = hora_franja.weekday()     # Lunes=0, ..., Domingo=6
    hora_num = hora_franja.hour
    if momento == "abiertos":
        if dia == 4 and hora_num > 15:
            return False
    elif momento == "nuevos":
        if dia == 4 and hora_num > 11:
            return False
    # Todo el sábado
    if dia == 5:
        return False
    # Domingo antes de las 16:00
    if dia == 6 and hora_num < 16:
        return False
    # En cualquier otro caso, sí puede operar
    return True

def hora_colombia_formateada():
    hora = datetime.now(ZoneInfo("America/Bogota"))
    return hora.strftime("%Y-%m-%d %H:%M:%S")

def obtener_balance(cuenta):
    if cuenta == "A1":
        ACCOUNT_ID = ACCOUNT_ID_A1
    else:
        ACCOUNT_ID = ACCOUNT_ID_A2
    url = f"{OANDA_URL}/accounts/{ACCOUNT_ID}/summary"
    balance = None
    while balance is None:
        try:
            response = requests.get(url, headers=HEADERS, timeout=(5, 5))
            if response.status_code == 200:
                data = response.json()
                balance = data["account"]["balance"]
            else:
                print("Error al obtener balance:")
                print(response.status_code, response.text)
                time.sleep(5)
        except requests.exceptions.RequestException as e:
            print("Excepción al intentar obtener balance:", e)
            time.sleep(5)
    return float(balance)

def decodificar_id(id_str):
    partes = id_str.split("_")    
    nombres = [
        "ciclo",
        "paso_ratio",
        "tamaño_cuenta_ciclo",
        "tipo",
        "precio_entrada",
        "ratio",
        "tp_price",
        "sl_price",
        "hora",
        "cuenta_actual",
        "tp_pips"
    ]
    
    datos = {}
    for i, valor in enumerate(partes):
        clave = nombres[i]
        if clave == "tipo" or clave == "hora":  # estos se dejan como string
            datos[clave] = valor
        else:
            try:
                datos[clave] = float(valor) if "." in valor else int(valor)
            except:
                datos[clave] = valor  # fallback a string si no se puede convertir
    return datos

def trades_abiertos(cuenta):
    if cuenta == "A1":
        ACCOUNT_ID = ACCOUNT_ID_A1
    else:
        ACCOUNT_ID = ACCOUNT_ID_A2
    url = f"{OANDA_URL}/accounts/{ACCOUNT_ID}/openTrades"
    datos = None
    try:
        response = requests.get(url, headers=HEADERS, timeout=(5, 5))
        trades = response.json().get("trades", [])
        for trade in trades:
            client_ext = trade.get("clientExtensions", {})
            id_str = client_ext.get("id")
            if id_str:
               datos = decodificar_id(id_str)
            else:
               datos = None
        if datos:
            return datos, len(trades) > 0
        else:
            return None, None
    except Exception as e:     
        print("Error al consultar trades:", str(e))
        return None, "Alto ahí"

def obtener_precio_actual(instrumento):
    url = f"{OANDA_URL}/accounts/{ACCOUNT_ID_A1}/pricing?instruments={instrumento}"
    prices = None
    while prices is None:
        try:
            response = requests.get(url, headers=HEADERS, timeout=(5, 5))    
            if response.status_code == 200:
                data = response.json()
                prices = data.get("prices", [])
                if prices:
                    bid_price = float(prices[0]["bids"][0]["price"])  # Vender
                    ask_price = float(prices[0]["asks"][0]["price"])  # Comprar
                    mid_price = (bid_price + ask_price) / 2 
            else:
                print("Error al obtener el precio actual")
                print(response.json())
                time.sleep(5)
        except requests.exceptions.RequestException as e:
            print("Excepción al intentar obtener precio actual:", e)
            time.sleep(5)
    return bid_price, ask_price, mid_price

def calcular_units_por_valor_pip(valor_deseado_por_pip, precio):
    if not precio:
        print("No precio actual, units")
        return None
    units = round((valor_deseado_por_pip * precio) / 1.05, 5) / 0.0001                               # CORRECCIÓN DE UNIDADES
    return int(units)  

def abrir_operacion(cuenta, unidades, tp_price, sl_price, ciclo, paso_ratio, tamaño_cuenta_ciclo, ratio, cuenta_actual, tp_pips, ACCOUNT_ID):
    if tp_price > sl_price:
            tipo = "buy"
    elif tp_price < sl_price:
            tipo = "sell"
    else:
        exportación = exportar_datos.agregar_datos_A(["Error: No se pudo determinar el tipo (abrir operación)", "Cuenta: ", cuenta, tp_price, sl_price])
        print("Error: No se pudo determinar el tipo (abrir operación)", cuenta, tp_price, sl_price)
        return None, None, None, None, None, True, None
    hora = hora_colombia_formateada()
    try:
        orden = {
            "order": {
                "instrument": instrumento,
                "units": str(unidades),
                "type": "MARKET",
                "positionFill": "DEFAULT",
                "stopLossOnFill": {
                    "price": str(sl_price)
                },
                "takeProfitOnFill": {
                    "price": str(tp_price)
                },
                "tradeClientExtensions": {
                    "id": f"{ciclo}_{paso_ratio}_{tamaño_cuenta_ciclo}_{tipo}_{precio_entrada}_{ratio}_{tp_price}_{sl_price}_{hora}_{cuenta_actual}_{tp_pips}"
                }
            }
        }
    except Exception as e:
        exportación = exportar_datos.agregar_datos_A(["Cuenta: ", cuenta, str(e)])
        return None, None, None, None, None, True, None

    try: 
        response = requests.post(
            f"{OANDA_URL}/accounts/{ACCOUNT_ID}/orders",
            headers=HEADERS,
            data=json.dumps(orden),
            timeout=(5, 5)
        )
        data = response.json()
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset = response.headers.get("X-RateLimit-Reset")
    except Exception as e:
        print("Error al enviar orden", "Cuenta: ", cuenta, e)
        print(response.json())
        exportación = exportar_datos.agregar_datos_A(["Cuenta: ", cuenta, str(e)])
        return None, None, None, None, None, True, None
    if "orderFillTransaction" in data:
        print("Orden ejecutada con éxito. Cuenta:", cuenta)
        fill = data.get("orderFillTransaction", {})
        trade_id = fill.get('tradeOpened', {}).get('tradeID')
        print(f"Instrumento: {fill.get('instrument')}")
        print(f"Unidades: {fill.get('units')}")
        print("Tipo:", tipo)
        print(f"Precio de entrada: {fill.get('price')}")
        print(f"SL: {sl_price}")
        print(f"TP: {tp_price}")
        print(f"Trade ID: {trade_id}")
        print("Hora:", hora)
        print(f"Solicitudes restantes: {remaining}")
        print(f"Tiempo hasta reinicio del límite (s): {reset}")
        print(f"Control ciclo: {fill.get('tradeOpened', {}).get('clientExtensions', {}).get('id')}")
        return trade_id, tipo, tp_price, sl_price, hora, None, True
    elif "orderCancelTransaction" in data:
        razon = data["orderCancelTransaction"].get("reason", "Desconocida")
        print("Orden cancelada (cuenta {}). Razón: {}".format(cuenta, razon))
        if razon == "INSUFFICIENT_MARGIN":
            print("unidades:", unidades)
            return "margen", None, None, None, None, True, None
    elif "orderRejectTransaction" in data:
        print("Orden rechazada (cuenta {}). Razón: {}".format(cuenta, data["orderRejectTransaction"].get("reason", "Desconocida")))
        print("Mensaje de error:", data["orderRejectTransaction"].get("errorMessage", "No proporcionado"))
    elif "errorMessage" in data:
        print("Error del servidor o de validación (cuenta {}): {}".format(cuenta, data.get("errorMessage")))
        print("Código de error:", data.get("errorCode", "Sin código"))
    else:
        print("Cuenta {}: {}".format(cuenta, json.dumps(data, indent=2)))
    return None, None, None, None, None, True, None

def nuevo_sma(tp_pips):
    velas = tp_pips + 1
    periodo = tp_pips
    if 10 <= tp_pips <= 14:
        temporalidad = "M10"
    elif 15 <= tp_pips <= 29:
        temporalidad = "M15"
    elif 30 <= tp_pips <= 59:
        temporalidad = "M30"
    return velas, periodo, temporalidad


# Datos operación
instrumento = "EUR_USD"
tp_pips_A1 = 10
sl_pips_A1 = round(tp_pips_A1 / ratio_A1)                                                                    #SL MODIFICADO
tamaño_cuenta_ciclo_A1 = obtener_balance("A1")
time.sleep(3)
tamaño_cuenta_ciclo_A2 = obtener_balance("A2")
time.sleep(3)

# Bucle operaciones
cuenta_actual_A1 = None
revision = None
trade_id_A1 = None
graficar_A1 = None
error_A1 = None
while ciclo_A1 or ciclo_A1 > -10:
    permiso = restriccion("abiertos")
    while not permiso:
        print("Franja restricción")
        time.sleep(3600)
        permiso = restriccion("abiertos")
    control_ciclo_A1, abiertos_A1 = trades_abiertos("A1")
    time.sleep(3)
    if not abiertos_A1:
        control_ciclo_A2, abiertos_A2 = trades_abiertos("A2")
    time.sleep(3)
    if abiertos_A1 or abiertos_A2:
        if not revision:
            if control_ciclo_A1 and control_ciclo_A2:
                ciclo_A1 = control_ciclo_A1["ciclo"]
                ciclo_A2 = control_ciclo_A2["ciclo"]
                paso_ratio_A1 = control_ciclo_A1["paso_ratio"]
                paso_ratio_A2 = control_ciclo_A2["paso_ratio"]
                tamaño_cuenta_ciclo_A1 = control_ciclo_A1["tamaño_cuenta_ciclo"]
                tamaño_cuenta_ciclo_A2 = control_ciclo_A2["tamaño_cuenta_ciclo"]
                cuenta_actual_A1 = control_ciclo_A1["cuenta_actual"]
                cuenta_actual_A2 = control_ciclo_A2["cuenta_actual"]
                tipo_A1 = control_ciclo_A1["tipo"]
                tipo_A2 = control_ciclo_A2["tipo"]
                precio_entrada_A1 = control_ciclo_A1["precio_entrada"]
                precio_entrada_A2 = control_ciclo_A2["precio_entrada"]
                ratio_A1 = control_ciclo_A1["ratio"]
                ratio_A2 = control_ciclo_A2["ratio"]
                tp_A1 = control_ciclo_A1["tp_price"]
                tp_A2 = control_ciclo_A2["tp_price"]
                sl_A1 = control_ciclo_A1["sl_price"]
                sl_A2 = control_ciclo_A2["sl_price"]
                hora_A1 = control_ciclo_A1["hora"]
                hora_A2 = control_ciclo_A2["hora"]
                tp_pips_A1 = control_ciclo_A1["tp_pips"]
                tp_pips_A2 = control_ciclo_A2["tp_pips"]
                graficar_A1 = True
                graficar_A2 = True
                revision = True
            else:
                print("No control ciclo")
        time.sleep(20)
            
    else:
        if graficar_A1:
                cuenta_previa_A1 = cuenta_actual_A1
                cuenta_previa_A2 = cuenta_actual_A2
                cuenta_actual_A1 = obtener_balance("A1")
                time.sleep(3)
                cuenta_actual_A2 = obtener_balance("A2")
                time.sleep(3)
                if cuenta_actual_A1 > cuenta_previa_A1:
                   paso_ratio_A1 += 1
                   resultado_A1 = "Ganada"
                elif cuenta_actual_A1 < cuenta_previa_A1:
                    paso_ratio_A1 -= 1
                    resultado_A1 = "Perdida"
                    
                if cuenta_actual_A2 > cuenta_previa_A2:
                   paso_ratio_A2 += 1
                   resultado_A2 = "Ganada"
                elif cuenta_actual_A2 < cuenta_previa_A2:
                    paso_ratio_A2 -= 1
                    resultado_A2 = "Perdida"
                    
                ganancia_A1 = cuenta_actual_A1 - cuenta_previa_A1
                ganancia_A2 = cuenta_actual_A2 - cuenta_previa_A2
                hora_actual = hora_colombia_formateada()
            
                try:
                    exportación = exportar_datos.agregar_datos("A", tipo_A1, precio_entrada_A1, tp_A1, sl_A1, tp_pips_A1, ciclo_A1, ratio_A1, paso_ratio_A1, resultado_A1, hora_A1, hora_actual, ganancia_A1, cuenta_actual_A1)
                    print(exportación)
                    time.sleep(3)
                    exportación = exportar_datos.agregar_datos("B", tipo_A2, precio_entrada_A2, tp_A2, sl_A2, tp_pips_A2, ciclo_A2, ratio_A2, paso_ratio_A2, resultado_A2, hora_A2, hora_actual, ganancia_A2, cuenta_actual_A2)
                    print(exportación)
                except Exception as e:
                    print("ERROR al enviar datos a Sheets:", e)
                time.sleep(3)
            
                # Reiniciar ciclo
                if paso_ratio_A1 > 2:
                    ciclo_A1 += 1
                    paso_ratio_A1 = 0
                    tamaño_cuenta_ciclo_A1 = cuenta_actual_A1
                elif paso_ratio_A1 < -8: 
                    ciclo_A1 -= 1
                    paso_ratio_A1 = 0
                    tamaño_cuenta_ciclo_A1 = cuenta_actual_A1
                if paso_ratio_A2 > 2:
                    ciclo_A2 += 1
                    paso_ratio_A2 = 0
                    tamaño_cuenta_ciclo_A2 = cuenta_actual_A2
                elif paso_ratio_A2 < -8: 
                    ciclo_A2 -= 1
                    paso_ratio_A2 = 0
                    tamaño_cuenta_ciclo_A2 = cuenta_actual_A2

                ratio_A1 = float(serie_ratios[paso_ratio_A1])
                ratio_A2 = float(serie_ratios[paso_ratio_A2])
                porcentaje_A1 = float(serie_porcentajes[paso_ratio_A1])
                porcentaje_A2 = float(serie_porcentajes[paso_ratio_A2])
        
        beneficio_A1 = (tamaño_cuenta_ciclo_A1) * porcentaje_A1                                                       # AJUSTE DE SALDO
        perdida_A2 = (tamaño_cuenta_ciclo_A2) * porcentaje_A2      
        valor_pip_A1 = round(beneficio_A1 / tp_pips_A1, 1) 
        valor_pip_A2 = round(perdida_A2 / tp_pips_A1, 1)
        cuenta_actual_A1 = tamaño_cuenta_ciclo_A1
        cuenta_actual_A2 = tamaño_cuenta_ciclo_A2
        velas_SMA, periodo_SMA, temporalidad_SMA = nuevo_sma(tp_pips_A1) #Recalcula 
        sma = SMA(instrumento, velas_SMA, periodo_SMA, temporalidad_SMA)
        time.sleep(3)
        bid_price, ask_price, mid_price = obtener_precio_actual(instrumento)
        units_A1_pre = calcular_units_por_valor_pip(valor_pip_A1, mid_price)
        units_A2_pre = calcular_units_por_valor_pip(valor_pip_A2, mid_price)            

        if mid_price > sma:
            units_A1 = int(units_A1_pre)
            units_A2 = int(-units_A2_pre)
            tp_price_A1 = round(mid_price + round(tp_pips_A1 / 10000, 5), 5)
            sl_price_A1 = round(mid_price - round(sl_pips_A1 / 10000, 5), 5)
            tp_price_A2 =  sl_price_A1
            sl_price_A2 =  tp_price_A1
        elif mid_price < sma:
            units_A1 = int(-units_A1_pre)
            units_A2 = int(units_A2_pre)
            tp_price_A1 = round(mid_price - round(tp_pips_A1 / 10000, 5), 5)
            sl_price_A1 = round(mid_price + round(sl_pips_A1 / 10000, 5), 5)
            tp_price_A2 =  sl_price_A1
            sl_price_A2 =  tp_price_A1
        else:
            units_A1 = None
            
        if units_A1:      
            permiso = restriccion("nuevos")
            while not permiso:
                print("Franja restricción")
                time.sleep(3600)
                permiso = restriccion("nuevos")
            if units_A1 > units_A2:       
                trade_id_A1, tipo_A1, tp_A1, sl_A1, hora, error_A1, graficar_A1 = abrir_operacion ("A1", units_A1, tp_price_A1, sl_price_A1, ciclo_A1, paso_ratio_A1, tamaño_cuenta_ciclo_A1, ratio_A1, cuenta_actual_A1, tp_pips_A1, ACCOUNT_ID_A1)
                if graficar_A1:
                    time.sleep(2)
                    while graficar_A2:
                        trade_id_A2, tipo_A2, tp_A2, sl_A1, hora, error_A2, graficar_A2 = abrir_operacion ("A2", units_A2, tp_price_A2, sl_price_A2, ciclo_A2, paso_ratio_A2, tamaño_cuenta_ciclo_A2, ratio_A2, cuenta_actual_A2, tp_pips_A1, ACCOUNT_ID_A2)
                        time.sleep(5)
            elif units_A1 < units_A2:
                trade_id_A2, tipo_A2, tp_A2, sl_A1, hora, error_A2, graficar_A2 = abrir_operacion ("A2", units_A2, tp_price_A2, sl_price_A2, ciclo_A2, paso_ratio_A2, tamaño_cuenta_ciclo_A2, ratio_A2, cuenta_actual_A2, tp_pips_A1, ACCOUNT_ID_A2)
                if graficar_A2:
                    time.sleep(2)
                    while graficar_A1:
                        trade_id_A1, tipo_A1, tp_A1, sl_A1, hora, error_A1, graficar_A1 = abrir_operacion ("A1", units_A1, tp_price_A1, sl_price_A1, ciclo_A1, paso_ratio_A1, tamaño_cuenta_ciclo_A1, ratio_A1, cuenta_actual_A1, tp_pips_A1, ACCOUNT_ID_A1)
                        time.sleep(5)
            else:
                if cuenta_actual_A1 > cuenta_actual_A2:
                    trade_id_A2, tipo_A2, tp_A2, sl_A1, hora, error_A2, graficar_A2 = abrir_operacion ("A2", units_A2, tp_price_A2, sl_price_A2, ciclo_A2, paso_ratio_A2, tamaño_cuenta_ciclo_A2, ratio_A2, cuenta_actual_A2, tp_pips_A1, ACCOUNT_ID_A2)
                    if graficar_A2:
                        time.sleep(2)
                        while graficar_A1:
                            trade_id_A1, tipo_A1, tp_A1, sl_A1, hora, error_A1, graficar_A1 = abrir_operacion ("A1", units_A1, tp_price_A1, sl_price_A1, ciclo_A1, paso_ratio_A1, tamaño_cuenta_ciclo_A1, ratio_A1, cuenta_actual_A1, tp_pips_A1, ACCOUNT_ID_A1)
                            time.sleep(5)
                else:
                    trade_id_A1, tipo_A1, tp_A1, sl_A1, hora, error_A1, graficar_A1 = abrir_operacion ("A1", units_A1, tp_price_A1, sl_price_A1, ciclo_A1, paso_ratio_A1, tamaño_cuenta_ciclo_A1, ratio_A1, cuenta_actual_A1, tp_pips_A1, ACCOUNT_ID_A1)
                    if graficar_A1:
                        time.sleep(2)
                        while graficar_A2:
                            trade_id_A2, tipo_A2, tp_A2, sl_A1, hora, error_A2, graficar_A2 = abrir_operacion ("A2", units_A2, tp_price_A2, sl_price_A2, ciclo_A2, paso_ratio_A2, tamaño_cuenta_ciclo_A2, ratio_A2, cuenta_actual_A2, tp_pips_A1, ACCOUNT_ID_A2)
                            time.sleep(5)
                    
            if trade_id_A1 or trade_id_A2 == "margen":
                tp_pips_A1 +=  1
                sl_pips_A1 = round((tp_pips_A1 / ratio_A1) / 1.1, 1)  #Recalcula                                  #SL MODIFICADO
                cuenta_actual_A1 == None
             
        revision = None
        time.sleep(20)

print("Programa terminado")
sys.exit()
