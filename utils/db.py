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

db = None  # 👈 Variable global


def inicializar_firebase():
    global db

    if firebase_admin._apps:
        return

    if "FIREBASE_PRIVATE_KEY_B64" in st.secrets:
        # Carga desde base64 como antes
        b64_str = st.secrets["FIREBASE_PRIVATE_KEY_B64"].replace('\n', '').replace('\r', '').strip()
        json_str = base64.b64decode(b64_str).decode("utf-8")
        cred_dict = json.loads(json_str)
        cred = credentials.Certificate(cred_dict)

    elif isinstance(st.secrets["SERVICE_ACCOUNT"], dict):
        # Si ya es un dict (raro, pero posible)
        cred = credentials.Certificate(st.secrets["SERVICE_ACCOUNT"])

    else:
        # Si es string plano
        cred_dict = json.loads(st.secrets["SERVICE_ACCOUNT"])
        cred = credentials.Certificate(cred_dict)

    firebase_admin.initialize_app(cred)
    db = firestore.client()

# Funciones para guardar datos en Firestore

def guardar_venta(venta_dict):
    db.collection("ventas").add(venta_dict)
    logging.info("Venta guardada.")


def guardar_cliente(id_cliente, cliente_dict):
    db.collection("clientes").document(id_cliente).set(cliente_dict)
    logging.info(f"Cliente '{id_cliente}' guardado.")



def actualizar_cliente(id_cliente, datos_nuevos):
    db.collection("clientes").document(id_cliente).update(datos_nuevos)
    logging.info(f"Cliente '{id_cliente}' actualizado.")




def guardar_transaccion(transaccion_dict):
    db.collection("transacciones").add(transaccion_dict)
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
    db.collection("transacciones").add(pago_dict)
    logging.info("Pago de cobranza registrado.")


def guardar_producto(producto_dict):
    db.collection("productos").add(producto_dict)
    logging.info("Producto guardado.")


# Funciones para leer datos de Firestore y convertir a pandas DataFrame

def leer_ventas():
    columnas = [
        "Fecha", "Cliente", "Producto", "Cantidad", "Precio Unitario", "Total",
        "Monto Crédito", "Monto Contado", "Anticipo Aplicado",
        "Método de pago", "Tipo de venta"
    ]
    docs = db.collection("ventas").stream()
    ventas = []
    for doc in docs:
        data = doc.to_dict()
        venta_normalizada = {col: data.get(col, None) for col in columnas}
        ventas.append(venta_normalizada)

    if not ventas:
        return pd.DataFrame(columns=columnas)

    df = pd.DataFrame(ventas)
    for col in columnas:
        if col not in df.columns:
            df[col] = None

    numeric_cols = ["Cantidad", "Precio Unitario", "Total", "Monto Crédito", "Monto Contado", "Anticipo Aplicado"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    return df[columnas]


def leer_transacciones():
    columnas = ["Fecha", "Descripción", "Categoría", "Tipo", "Monto", "Cliente", "Método de pago"]
    docs = db.collection("transacciones").stream()
    transacciones = []
    for doc in docs:
        data = doc.to_dict()
        transaccion_normalizada = {col: data.get(col, None) for col in columnas}
        transacciones.append(transaccion_normalizada)

    if not transacciones:
        return pd.DataFrame(columns=columnas)

    df = pd.DataFrame(transacciones)
    for col in columnas:
        if col not in df.columns:
            df[col] = None

    if "Monto" in df.columns:
        df["Monto"] = pd.to_numeric(df["Monto"], errors='coerce').fillna(0.0)

    return df[columnas]


def leer_cobranza():
    columnas = ["Fecha", "Cliente", "Descripción", "Monto", "Método de pago"]
    docs = db.collection("transacciones").where("Categoría", "==", "Cobranza").stream()
    cobranza = []
    for doc in docs:
        data = doc.to_dict()
        registro = {col: data.get(col, None) for col in columnas}
        cobranza.append(registro)

    df = pd.DataFrame(cobranza)
    if "Monto" in df.columns:
        df["Monto"] = pd.to_numeric(df["Monto"], errors='coerce').fillna(0.0)

    return df


def calcular_balance_contable():
    transacciones = leer_transacciones()
    ingresos = transacciones.query("Tipo == 'Ingreso'")["Monto"].sum()
    gastos = transacciones.query("Tipo == 'Egreso'")["Monto"].sum()
    balance = ingresos - gastos
    return ingresos, gastos, balance


def leer_clientes():
    columnas = ["ID", "Nombre", "Correo", "Teléfono", "Empresa", "RFC", "Límite de crédito"]
    docs = db.collection("clientes").stream()
    clientes = []

    for doc in docs:
        data = doc.to_dict()
        data["ID"] = doc.id  # 🔥 ¡Aquí se guarda el ID del documento!
        cliente_normalizado = {col: data.get(col, None) for col in columnas}
        clientes.append(cliente_normalizado)

    if not clientes:
        return pd.DataFrame(columns=columnas)

    df = pd.DataFrame(clientes)

    # Asegurar que todas las columnas existan
    for col in columnas:
        if col not in df.columns:
            df[col] = None

    # Convertir "Límite de crédito" a numérico por si acaso
    if "Límite de crédito" in df.columns:
        df["Límite de crédito"] = pd.to_numeric(df["Límite de crédito"], errors='coerce').fillna(0.0)

    return df[columnas]



def leer_productos():
    columnas = ["Clave", "Nombre", "Categoría", "Precio Unitario", "Costo Unitario", "Cantidad", "Descripción"]
    docs = db.collection("productos").stream()
    productos = []
    for doc in docs:
        data = doc.to_dict()
        producto_normalizado = {col: data.get(col, None) for col in columnas}
        productos.append(producto_normalizado)

    if not productos:
        return pd.DataFrame(columns=columnas)

    df = pd.DataFrame(productos)
    for col in columnas:
        if col not in df.columns:
            df[col] = None

    numeric_cols = ["Precio Unitario", "Costo Unitario", "Cantidad"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    return df[columnas]


def actualizar_producto_por_clave(clave, campos_actualizados: dict):
    productos_ref = db.collection("productos")
    query = productos_ref.where("Clave", "==", clave).get()
    if query:
        doc_id = query[0].id
        productos_ref.document(doc_id).update(campos_actualizados)
        logging.info(f"Producto '{clave}' actualizado.")


def eliminar_producto_por_clave(clave):
    productos_ref = db.collection("productos")
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
    db.collection("transacciones").add(ingreso)
    logging.info("Ingreso automático registrado para la venta.")


def obtener_id_producto(clave):
    query = db.collection("productos").where("Clave", "==", clave).get()
    if query:
        return query[0].id
    return None