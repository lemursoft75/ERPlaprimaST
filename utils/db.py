import os
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
import json
import datetime
import base64
import pandas as pd
import logging

load_dotenv()
db = None

def inicializar_firebase():
    global db

    if firebase_admin._apps:
        return

    if "FIREBASE_PRIVATE_KEY_B64" in st.secrets:
        b64_str = st.secrets["FIREBASE_PRIVATE_KEY_B64"].replace('\n', '').replace('\r', '').strip()
        json_str = base64.b64decode(b64_str).decode("utf-8")
        cred_dict = json.loads(json_str)
        cred = credentials.Certificate(cred_dict)

    elif isinstance(st.secrets["SERVICE_ACCOUNT"], dict):
        cred = credentials.Certificate(st.secrets["SERVICE_ACCOUNT"])

    else:
        cred_dict = json.loads(st.secrets["SERVICE_ACCOUNT"])
        cred = credentials.Certificate(cred_dict)

    firebase_admin.initialize_app(cred)
    db = firestore.client()

def obtener_ruta_usuario():
    return db.collection("usuarios").document(st.session_state.uid)

# 🔻 Guardar datos
def guardar_venta(venta_dict):
    obtener_ruta_usuario().collection("ventas").add(venta_dict)
    logging.info("Venta guardada.")

def guardar_cliente(id_cliente, cliente_dict):
    obtener_ruta_usuario().collection("clientes").document(id_cliente).set(cliente_dict)
    logging.info(f"Cliente '{id_cliente}' guardado.")

def actualizar_cliente(id_cliente, datos_nuevos):
    obtener_ruta_usuario().collection("clientes").document(id_cliente).update(datos_nuevos)
    logging.info(f"Cliente '{id_cliente}' actualizado.")

def guardar_transaccion(transaccion_dict):
    obtener_ruta_usuario().collection("transacciones").add(transaccion_dict)
    logging.info("Transacción guardada.")

def registrar_pago_cobranza(cliente, monto, metodo_pago, fecha, descripcion=""):
    pago_dict = {
        "Fecha": fecha,
        "Descripción": descripcion or f"Abono de crédito por parte de {cliente}",
        "Categoría": "Cobranza",
        "Tipo": "Ingreso",
        "Monto": monto,
        "Cliente": cliente,
        "Método de pago": metodo_pago
    }
    obtener_ruta_usuario().collection("transacciones").add(pago_dict)
    logging.info("Pago de cobranza registrado.")

def guardar_producto(producto_dict):
    obtener_ruta_usuario().collection("productos").add(producto_dict)
    logging.info("Producto guardado.")

# 🔻 Leer datos
def leer_ventas():
    columnas = ["Fecha", "Cliente", "Producto", "Cantidad", "Precio Unitario", "Total",
                "Monto Crédito", "Monto Contado", "Anticipo Aplicado", "Método de pago", "Tipo de venta"]
    docs = obtener_ruta_usuario().collection("ventas").stream()
    ventas = [{col: doc.to_dict().get(col, None) for col in columnas} for doc in docs]
    df = pd.DataFrame(ventas or [], columns=columnas)
    for col in ["Cantidad", "Precio Unitario", "Total", "Monto Crédito", "Monto Contado", "Anticipo Aplicado"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
    return df

def leer_transacciones():
    columnas = ["Fecha", "Descripción", "Categoría", "Tipo", "Monto", "Cliente", "Método de pago"]
    docs = obtener_ruta_usuario().collection("transacciones").stream()
    transacciones = [{col: doc.to_dict().get(col, None) for col in columnas} for doc in docs]
    df = pd.DataFrame(transacciones or [], columns=columnas)
    if "Monto" in df.columns:
        df["Monto"] = pd.to_numeric(df["Monto"], errors='coerce').fillna(0.0)
    return df

def leer_cobranza():
    columnas = ["Fecha", "Cliente", "Descripción", "Monto", "Método de pago"]
    docs = obtener_ruta_usuario().collection("transacciones").where("Categoría", "==", "Cobranza").stream()
    cobranza = [{col: doc.to_dict().get(col, None) for col in columnas} for doc in docs]
    df = pd.DataFrame(cobranza or [], columns=columnas)
    if "Monto" in df.columns:
        df["Monto"] = pd.to_numeric(df["Monto"], errors='coerce').fillna(0.0)
    return df

def calcular_balance_contable():
    transacciones = leer_transacciones()
    ingresos = transacciones.query("Tipo == 'Ingreso'")["Monto"].sum()
    gastos = transacciones.query("Tipo == 'Egreso'")["Monto"].sum()
    return ingresos, gastos, ingresos - gastos

def leer_clientes():
    columnas = ["ID", "Nombre", "Correo", "Teléfono", "Empresa", "RFC", "Límite de crédito"]
    docs = obtener_ruta_usuario().collection("clientes").stream()
    clientes = []
    for doc in docs:
        data = doc.to_dict()
        data["ID"] = doc.id
        clientes.append({col: data.get(col, None) for col in columnas})
    df = pd.DataFrame(clientes or [], columns=columnas)
    if "Límite de crédito" in df.columns:
        df["Límite de crédito"] = pd.to_numeric(df["Límite de crédito"], errors='coerce').fillna(0.0)
    return df

def leer_productos():
    columnas = ["Clave", "Nombre", "Categoría", "Precio Unitario", "Costo Unitario", "Cantidad", "Descripción"]
    docs = obtener_ruta_usuario().collection("productos").stream()
    productos = [{col: doc.to_dict().get(col, None) for col in columnas} for doc in docs]
    df = pd.DataFrame(productos or [], columns=columnas)
    for col in ["Precio Unitario", "Costo Unitario", "Cantidad"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
    return df

# 🔻 Actualizar y eliminar por clave
def actualizar_producto_por_clave(clave, campos_actualizados):
    productos_ref = obtener_ruta_usuario().collection("productos")
    query = productos_ref.where("Clave", "==", clave).get()
    if query:
        doc_id = query[0].id
        productos_ref.document(doc_id).update(campos_actualizados)
        logging.info(f"Producto '{clave}' actualizado.")

def eliminar_producto_por_clave(clave):
    productos_ref = obtener_ruta_usuario().collection("productos")
    query = productos_ref.where("Clave", "==", clave).get()
    if query:
        doc_id = query[0].id
        productos_ref.document(doc_id).delete()
        logging.info(f"Producto '{clave}' eliminado.")

def registrar_ingreso_automatico(venta_dict):
    ingreso = {
        "Fecha": venta_dict.get("Fecha", datetime.date.today().isoformat()),
        "Descripción": f"Venta a {venta_dict.get('Cliente', 'Cliente desconocido')}",
        "Categoría": "Ventas",
        "Tipo": "Ingreso",
        "Monto": float(venta_dict.get("Total", 0.0))
    }
    obtener_ruta_usuario().collection("transacciones").add(ingreso)
    logging.info("Ingreso automático registrado para la venta.")

def obtener_id_producto(clave):
    query = obtener_ruta_usuario().collection("productos").where("Clave", "==", clave).get()
    return query[0].id if query else None