import streamlit as st
import pandas as pd
import datetime  # Importación necesaria para manejar fechas
import io  # Importación necesaria para manejar datos en memoria para Excel
from utils.db import leer_ventas, guardar_transaccion, leer_transacciones, leer_clientes


# Helper function to convert DataFrame to Excel
def to_excel(df):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Datos')  # 'Datos' es el nombre de la hoja en Excel
    writer.close()  # Importante cerrar el escritor para guardar el contenido
    processed_data = output.getvalue()
    return processed_data


# Función de callback para el selectbox de cliente
def on_cliente_change():
    """Esta función se llama cuando el cliente en el selectbox cambia."""
    # Al cambiar de cliente, aseguramos que las opciones de manejo de excedentes/anticipos se oculten.
    if "mostrar_opciones_excedente" in st.session_state:
        del st.session_state["mostrar_opciones_excedente"]
    if "pago_excedente_info" in st.session_state:
        del st.session_state["pago_excedente_info"]
    if "mostrar_opciones_anticipo" in st.session_state:
        del st.session_state["mostrar_opciones_anticipo"]
    if "pago_anticipo_info" in st.session_state:
        del st.session_state["pago_anticipo_info"]

    # Cuando el cliente cambia, queremos que el campo de monto a abonar se actualice
    # con el nuevo saldo pendiente. Reiniciamos la clave de session_state para el monto.
    if "cobranza_monto_input" in st.session_state:
        del st.session_state["cobranza_monto_input"]

    st.rerun()


def render():
    st.title("💰 Módulo de cobranza")

    # Cargar datos frescos en cada render para asegurar la actualización
    st.session_state.ventas_data = leer_ventas()
    st.session_state.transacciones_data = leer_transacciones()
    st.session_state.clientes = leer_clientes()

    ventas_df = st.session_state.ventas_data
    transacciones_df = st.session_state.transacciones_data
    clientes_df = st.session_state.clientes

    # --- Preprocesamiento y cálculo de saldos ---

    # Asegurar que las columnas numéricas sean float y manejar NaNs
    numeric_cols_ventas = ["Monto Crédito", "Monto Contado", "Anticipo Aplicado", "Total"]
    for col in numeric_cols_ventas:
        if col not in ventas_df.columns:
            ventas_df[col] = 0.0
        ventas_df[col] = pd.to_numeric(ventas_df[col], errors='coerce').fillna(0.0)

    numeric_cols_transacciones = ["Monto"]
    for col in numeric_cols_transacciones:
        if col not in transacciones_df.columns:
            transacciones_df[col] = 0.0
        transacciones_df[col] = pd.to_numeric(transacciones_df[col], errors='coerce').fillna(0.0)

    # 1. Calcular el total de crédito otorgado por cliente
    # Asegurarse de que 'Tipo de venta' sea string para la comparación
    ventas_df["Tipo de venta"] = ventas_df["Tipo de venta"].astype(str)
    credito_otorgado = ventas_df[
        ventas_df["Tipo de venta"].isin(["Crédito", "Mixta"])
    ].groupby("Cliente")["Monto Crédito"].sum().reset_index()
    credito_otorgado.rename(columns={"Monto Crédito": "Crédito Otorgado"}, inplace=True)

    # 2. Calcular el total de pagos de cobranza (efectivos) por cliente
    pagos_cobranza = transacciones_df[
        transacciones_df["Categoría"].astype(str) == "Cobranza"
        ].groupby("Cliente")["Monto"].sum().reset_index()
    pagos_cobranza.rename(columns={"Monto": "Pagos Cobranza"}, inplace=True)

    # 3. Calcular el total de anticipos DISPONIBLES (saldo a favor del cliente)
    # Esto es: Anticipos Cliente - Anticipos Aplicados
    anticipos_cliente_recibidos = transacciones_df[
        transacciones_df["Categoría"].astype(str) == "Anticipo Cliente"
        ].groupby("Cliente")["Monto"].sum().reset_index()
    anticipos_cliente_recibidos.rename(columns={"Monto": "Anticipos Recibidos"}, inplace=True)

    # Necesitamos `anticipos_aplicados` para el cálculo del Saldo Anticipos
    anticipos_aplicados_para_saldo_anticipos = transacciones_df[
        transacciones_df["Categoría"].astype(str) == "Anticipo Aplicado"
        ].groupby("Cliente")["Monto"].sum().reset_index()
    anticipos_aplicados_para_saldo_anticipos.rename(columns={"Monto": "Anticipos Aplicados"}, inplace=True)

    saldo_anticipos = anticipos_cliente_recibidos.merge(anticipos_aplicados_para_saldo_anticipos, on="Cliente",
                                                        how="left").fillna(0)
    saldo_anticipos["Saldo Anticipos"] = saldo_anticipos["Anticipos Recibidos"] - saldo_anticipos["Anticipos Aplicados"]
    # Nos interesan solo los anticipos disponibles (positivos)
    saldo_anticipos = saldo_anticipos[saldo_anticipos["Saldo Anticipos"] > 0]

    # Unir solo el crédito otorgado y los pagos de cobranza directos
    saldos_final = pd.merge(credito_otorgado, pagos_cobranza, on="Cliente", how="left").fillna(0)

    # El "Total Pagos y Aplicaciones" para el calculo de deuda solo debe incluir Cobranza
    saldos_final["Total Pagos y Aplicaciones"] = saldos_final["Pagos Cobranza"]

    # Calcular el Saldo Pendiente
    saldos_final["Saldo Pendiente"] = saldos_final["Crédito Otorgado"] - saldos_final["Total Pagos y Aplicaciones"]

    # Añadir clientes que solo tienen anticipos (sin deuda actual)
    # Identificar clientes que tienen anticipos pero no aparecen en saldos_final (no tienen deuda)
    clientes_solo_anticipos = saldo_anticipos[~saldo_anticipos['Cliente'].isin(saldos_final['Cliente'])]

    if not clientes_solo_anticipos.empty:
        # Crear un DataFrame con la estructura de saldos_final para estos clientes
        df_solo_anticipos = pd.DataFrame({
            "Cliente": clientes_solo_anticipos["Cliente"],
            "Crédito Otorgado": 0.0,
            "Pagos Cobranza": 0.0,
            "Anticipos Aplicados": 0.0,
            "Total Pagos y Aplicaciones": 0.0,
            "Saldo Pendiente": 0.0  # Su saldo pendiente es 0, su "saldo" es el anticipo a favor
        })
        saldos_final = pd.concat([saldos_final, df_solo_anticipos], ignore_index=True)

    # Merge final para mostrar el saldo de anticipos junto con el saldo pendiente de deuda
    saldos_completos = pd.merge(saldos_final, saldo_anticipos[['Cliente', 'Saldo Anticipos']], on="Cliente",
                                how="left").fillna(0)

    # Asegurarse de que el "Saldo Pendiente" no sea negativo (si es 0 o negativo, significa que se cubrió la deuda)
    saldos_completos["Saldo Pendiente Display"] = saldos_completos["Saldo Pendiente"].apply(lambda x: max(0, x))

    # --- Fin preprocesamiento y cálculo de saldos ---

    st.subheader("📋 Saldos por cliente")

    cliente_opciones = clientes_df["Nombre"].tolist() if not clientes_df.empty else []

    if not cliente_opciones:
        st.info("No hay clientes registrados. Por favor, agregue clientes en el módulo 'Clientes'.")
        st.stop() # Detener la ejecución si no hay clientes


    # Filtro para la tabla de saldos
    filtro_cliente_saldos = st.selectbox(
        "Filtrar saldos por cliente (opcional)",
        ["Todos los clientes"] + cliente_opciones,
        key="filtro_saldos_cliente_tabla"
    )

    saldos_display = saldos_completos.copy()
    saldos_display["Saldo Pendiente Display"] = saldos_display.apply(
        lambda row: 0.0 if row["Total Pagos y Aplicaciones"] >= row["Crédito Otorgado"] else row["Saldo Pendiente"],
        axis=1
    )

    if filtro_cliente_saldos != "Todos los clientes":
        df_to_display_export_saldos = saldos_display[saldos_display["Cliente"] == filtro_cliente_saldos].copy()
    else:
        df_to_display_export_saldos = saldos_display.copy()

    df_to_display_export_saldos = df_to_display_export_saldos[[
        "Cliente", "Crédito Otorgado", "Total Pagos y Aplicaciones", "Saldo Pendiente Display", "Saldo Anticipos"
    ]].rename(columns={
        "Crédito Otorgado": "Crédito Otorgado",
        "Total Pagos y Aplicaciones": "Pagos y Aplicaciones",
        "Saldo Pendiente Display": "Saldo Pendiente",
        "Saldo Anticipos": "Anticipo a Favor"
    })

    st.dataframe(df_to_display_export_saldos, use_container_width=True)

    if not df_to_display_export_saldos.empty:
        file_name_suffix = ""
        if filtro_cliente_saldos != "Todos los clientes":
            file_name_suffix = f"_{filtro_cliente_saldos.replace(' ', '_')}"
            label_text = f"Exportar Saldo de {filtro_cliente_saldos} a Excel"
        else:
            label_text = "Exportar todos los Saldos a Excel"

        st.download_button(
            label=label_text,
            data=to_excel(df_to_display_export_saldos),
            file_name=f"saldos_clientes{file_name_suffix}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("No hay saldos pendientes para mostrar según el filtro seleccionado.")

    st.divider()
    st.subheader("🧾 Registrar nuevo pago")

    # --- INICIALIZACIÓN ADECUADA DEL SELECTBOX DE CLIENTE PARA REGISTRAR PAGO ---
    # Calculamos el índice por defecto de forma segura.
    default_index_for_cobranza_select = 0 # Valor predeterminado si no se encuentra o no hay opciones
    if "cobranza_cliente_select_form" in st.session_state and \
       st.session_state.cobranza_cliente_select_form in cliente_opciones:
        # Si la clave ya existe en session_state (porque el selectbox ya se renderizó antes)
        # y el valor guardado está en las opciones actuales, usa su índice.
        default_index_for_cobranza_select = cliente_opciones.index(st.session_state.cobranza_cliente_select_form)
    # Si no hay clientes, el `st.stop()` de arriba ya detuvo la ejecución.
    # Si hay clientes pero la clave no está en session_state, default_index_for_cobranza_select será 0 (primer cliente).

    cliente_seleccionado = st.selectbox(
        "Cliente",
        cliente_opciones,
        index=default_index_for_cobranza_select,
        key="cobranza_cliente_select_form", # Esta key es crucial para Streamlit
        on_change=on_cliente_change
    )

    # Recalcular saldo_cliente_actual de forma precisa (usando el cliente_seleccionado actual)
    saldo_cliente_actual_para_pago = 0.0
    anticipo_a_favor_actual = 0.0

    if cliente_seleccionado and not saldos_completos.empty and cliente_seleccionado in saldos_completos["Cliente"].tolist():
        cliente_data = saldos_completos[saldos_completos["Cliente"] == cliente_seleccionado].iloc[0]
        # Usamos "Saldo Pendiente Display" porque ese ya es el valor ajustado a 0 si la deuda está cubierta
        saldo_cliente_actual_para_pago = cliente_data["Saldo Pendiente Display"]
        anticipo_a_favor_actual = cliente_data["Saldo Anticipos"]

    monto_sugerido_input = float(saldo_cliente_actual_para_pago)
    if monto_sugerido_input == 0 and anticipo_a_favor_actual > 0:
        st.info(f"El cliente {cliente_seleccionado} tiene un anticipo a favor de ${anticipo_a_favor_actual:,.2f}.")

    # Si la clave "cobranza_monto_input" no existe o fue eliminada por el on_change,
    # se inicializa con el monto sugerido.
    if "cobranza_monto_input" not in st.session_state:
        st.session_state["cobranza_monto_input"] = monto_sugerido_input

    monto = st.number_input(
        "Monto a abonar",
        min_value=0.0,
        value=st.session_state["cobranza_monto_input"],
        format="%.2f",
        key="cobranza_monto_input"
    )

    metodo_pago = st.selectbox("Método de pago", ["Efectivo", "Transferencia", "Tarjeta"], key="cobranza_metodo_pago")
    fecha = st.date_input("Fecha de pago", key="cobranza_fecha", value=datetime.date.today()) # Valor predeterminado a hoy
    descripcion = st.text_input("Referencia del pago (opcional)", key="cobranza_descripcion")

    if st.button("Procesar Pago", key="cobranza_procesar_pago_btn_main"):
        # Vuelve a cargar datos frescos justo antes de procesar
        st.session_state.transacciones_data = leer_transacciones()
        st.session_state.ventas_data = leer_ventas()

        monto_f = float(monto)

        if monto_f <= 0:
            st.error("❌ El monto a abonar debe ser mayor que cero.")
            st.stop()  # Detener la ejecución si el monto es inválido

        # Recalcular el saldo pendiente y anticipo a favor para el cliente seleccionado
        # Usamos los DataFrames actualizados de session_state
        current_ventas_df = st.session_state.ventas_data
        current_transacciones_df = st.session_state.transacciones_data

        credito_otorgado_current = current_ventas_df[
            (current_ventas_df["Tipo de venta"].isin(["Crédito", "Mixta"])) &
            (current_ventas_df["Cliente"] == cliente_seleccionado)
            ]["Monto Crédito"].sum()

        pagos_cobranza_current = current_transacciones_df[
            (current_transacciones_df["Categoría"].astype(str) == "Cobranza") &
            (current_transacciones_df["Cliente"] == cliente_seleccionado)
            ]["Monto"].sum()

        anticipos_aplicados_current = current_transacciones_df[
            (current_transacciones_df["Categoría"].astype(str) == "Anticipo Aplicado") &
            (current_transacciones_df["Cliente"] == cliente_seleccionado)
            ]["Monto"].sum()

        anticipos_recibidos_current = current_transacciones_df[
            (current_transacciones_df["Categoría"].astype(str) == "Anticipo Cliente") &
            (current_transacciones_df["Cliente"] == cliente_seleccionado)
            ]["Monto"].sum()

        total_pagos_aplicaciones_current = pagos_cobranza_current
        saldo_pendiente_current = credito_otorgado_current - total_pagos_aplicaciones_current
        saldo_anticipo_a_favor_current = anticipos_recibidos_current - anticipos_aplicados_current

        # --- Lógica de procesamiento de pago ---

        # Caso 1: Tiene saldo pendiente (deuda)
        # Aquí usamos saldo_pendiente_current directamente, que es el valor real (puede ser negativo)
        if saldo_pendiente_current > 0:
            # Si el pago cubre toda o parte de la deuda
            if monto_f <= saldo_pendiente_current:
                pago_dict = {
                    "Fecha": fecha.isoformat(),
                    "Descripción": descripcion or f"Abono de crédito por parte de {cliente_seleccionado}",
                    "Categoría": "Cobranza",
                    "Tipo": "Ingreso",
                    "Monto": monto_f,
                    "Cliente": cliente_seleccionado,
                    "Método de pago": metodo_pago
                }
                guardar_transaccion(pago_dict)
                st.success(
                    f"✅ Pago de ${monto_f:.2f} registrado para {cliente_seleccionado}. Saldo restante: ${max(0, saldo_pendiente_current - monto_f):,.2f}")
            # Si el pago excede la deuda
            else:
                excedente = monto_f - saldo_pendiente_current
                st.warning(
                    f"⚠️ El abono de ${monto_f:.2f} excede el saldo pendiente de ${saldo_pendiente_current:.2f} para {cliente_seleccionado}. Excedente: ${excedente:.2f}")

                st.session_state["pago_excedente_info"] = {
                    "cliente": cliente_seleccionado,
                    "monto_original": monto_f,
                    "saldo_pendiente": saldo_pendiente_current,
                    "excedente": excedente,
                    "metodo_pago": metodo_pago,
                    "fecha": fecha,
                    "descripcion": descripcion
                }
                st.session_state["mostrar_opciones_excedente"] = True

        # Caso 2: No tiene saldo pendiente (o ya es 0 o negativo por pagos previos)
        elif saldo_pendiente_current <= 0:  # Si ya no hay deuda o es negativa (sobrepagado)
            st.warning(
                f"⚠️ El cliente {cliente_seleccionado} no tiene saldo pendiente. ¿Desea registrar ${monto_f:.2f} como anticipo?")

            st.session_state["pago_anticipo_info"] = {
                "cliente": cliente_seleccionado,
                "monto": monto_f,
                "metodo_pago": metodo_pago,
                "fecha": fecha,
                "descripcion": descripcion
            }
            st.session_state["mostrar_opciones_anticipo"] = True

        # Una vez que la transacción inicial se procesa o se establecen las banderas
        st.session_state.transacciones_data = leer_transacciones()  # Recargar datos después de guardar
        st.session_state.ventas_data = leer_ventas()

        # Después de procesar el pago, borra el valor de session_state para que se recalcule
        # en el siguiente render o al cambiar de cliente.
        if "cobranza_monto_input" in st.session_state:
            del st.session_state["cobranza_monto_input"]
        st.rerun()

    # --- Bloque para mostrar opciones de excedente (solo si se necesita) ---
    if st.session_state.get("mostrar_opciones_excedente", False):
        info = st.session_state["pago_excedente_info"]
        with st.form("form_opciones_excedente"):
            st.write(
                f"Para el cliente **{info['cliente']}**:")
            st.write(f"- Monto ingresado: **${info['monto_original']:.2f}**")
            st.write(f"- Saldo pendiente: **${info['saldo_pendiente']:.2f}**")
            st.write(f"- Excedente: **${info['excedente']:.2f}**")

            opcion_excedente = st.radio(
                "¿Qué deseas hacer con el excedente?",
                ["Generar anticipo con el excedente", "Abonar solo el saldo pendiente (el resto se ignora)",
                 "Cancelar operación"],
                key="radio_excedente_form"
            )
            col1, col2 = st.columns(2)
            with col1:
                confirmar_excedente = st.form_submit_button("Confirmar Opción")
            with col2:
                cancelar_opcion_excedente = st.form_submit_button("Cancelar")

        if confirmar_excedente:
            if opcion_excedente == "Generar anticipo con el excedente":
                # Primero, registrar el pago que cubre el saldo pendiente
                pago_cobranza_dict = {
                    "Fecha": info["fecha"].isoformat(),
                    "Descripción": f"Abono de crédito para {info['cliente']} (cubre deuda).",
                    "Categoría": "Cobranza",
                    "Tipo": "Ingreso",
                    "Monto": float(info["saldo_pendiente"]),  # Solo el monto de la deuda
                    "Cliente": info["cliente"],
                    "Método de pago": info["metodo_pago"]
                }
                guardar_transaccion(pago_cobranza_dict)

                # Luego, registrar el excedente como un anticipo
                anticipo_excedente_dict = {
                    "Fecha": info["fecha"].isoformat(),
                    "Descripción": info[
                                       "descripcion"] or f"Anticipo generado por excedente de pago para {info['cliente']}",
                    "Categoría": "Anticipo Cliente",
                    "Tipo": "Ingreso",
                    "Monto": float(info["excedente"]),
                    "Cliente": info["cliente"],
                    "Método de pago": info["metodo_pago"]
                }
                guardar_transaccion(anticipo_excedente_dict)

                st.success(
                    f"✅ Pago de ${info['saldo_pendiente']:.2f} y anticipo de ${info['excedente']:.2f} registrados para {info['cliente']}.")

            elif opcion_excedente == "Abonar solo el saldo pendiente (el resto se ignora)":
                pago_dict = {
                    "Fecha": info["fecha"].isoformat(),
                    "Descripción": f"Abono exacto al saldo pendiente para {info['cliente']}. Excedente ignorado.",
                    "Categoría": "Cobranza",
                    "Tipo": "Ingreso",
                    "Monto": float(info["saldo_pendiente"]),
                    "Cliente": info["cliente"],
                    "Método de pago": info["metodo_pago"]
                }
                guardar_transaccion(pago_dict)
                st.success(
                    f"✅ Solo se registró el saldo pendiente de ${info['saldo_pendiente']:.2f} para {info['cliente']}. El excedente fue ignorado.")

            elif opcion_excedente == "Cancelar operación":
                st.info("Operación de pago cancelada por el usuario.")

            # Limpiar banderas y recargar para refrescar la UI
            st.session_state["mostrar_opciones_excedente"] = False
            st.session_state["pago_excedente_info"] = {}
            st.session_state.transacciones_data = leer_transacciones()
            st.session_state.ventas_data = leer_ventas()
            st.rerun()
        elif cancelar_opcion_excedente:
            st.info("Operación de pago cancelada por el usuario.")
            st.session_state["mostrar_opciones_excedente"] = False
            st.session_state["pago_excedente_info"] = {}
            st.rerun()

    # --- Bloque para mostrar opciones de anticipo (solo si se necesita) ---
    if st.session_state.get("mostrar_opciones_anticipo", False):
        info = st.session_state["pago_anticipo_info"]
        with st.form("form_opciones_anticipo"):
            st.write(
                f"El cliente **{info['cliente']}** no tiene saldo pendiente. Monto a registrar: **${info['monto']:.2f}**.")
            opcion_anticipo = st.radio(
                "¿Desea registrar este monto como anticipo?",
                ["Sí, registrar como anticipo", "No, cancelar"],
                key="radio_anticipo_form"
            )
            col1, col2 = st.columns(2)
            with col1:
                confirmar_anticipo = st.form_submit_button("Confirmar Opción")
            with col2:
                cancelar_opcion_anticipo = st.form_submit_button("Cancelar")

        if confirmar_anticipo:
            if opcion_anticipo == "Sí, registrar como anticipo":
                pago_dict = {
                    "Fecha": info["fecha"].isoformat(),
                    "Descripción": info["descripcion"] or f"Anticipo registrado para {info['cliente']}",
                    "Categoría": "Anticipo Cliente",
                    "Tipo": "Ingreso",
                    "Monto": float(info["monto"]),
                    "Cliente": info["cliente"],
                    "Método de pago": info["metodo_pago"]
                }
                guardar_transaccion(pago_dict)
                st.success(f"✅ Anticipo de ${info['monto']:.2f} registrado para {info['cliente']}")
            else:  # "No, cancelar"
                st.info("Operación de pago cancelada por el usuario.")

            # Limpiar banderas y recargar
            st.session_state["mostrar_opciones_anticipo"] = False
            st.session_state["pago_anticipo_info"] = {}
            st.session_state.transacciones_data = leer_transacciones()
            st.session_state.ventas_data = leer_ventas()
            st.rerun()
        elif cancelar_opcion_anticipo:
            st.info("Operación de pago cancelada por el usuario.")
            st.session_state["mostrar_opciones_anticipo"] = False
            st.session_state["pago_anticipo_info"] = {}
            st.rerun()

    st.divider()
    st.subheader("📑 Historial de pagos y anticipos")

    # --- Selectores de fecha para el historial ---
    col_hist1, col_hist2 = st.columns(2)
    with col_hist1:
        # Asegúrate de que las fechas por defecto sean datetime.date.today()
        # y que se maneje el caso de DataFrame vacío.
        default_start_date_hist = datetime.date.today() # Valor por defecto a hoy
        if not st.session_state.transacciones_data.empty and "Fecha" in st.session_state.transacciones_data.columns:
            # Convertir a datetime antes de buscar min
            # Crear una copia para evitar SettingWithCopyWarning
            temp_df_for_dates = st.session_state.transacciones_data.copy()
            temp_df_for_dates["Fecha_dt"] = pd.to_datetime(temp_df_for_dates["Fecha"], errors='coerce')
            # Filtrar NaT antes de encontrar el mínimo, o establecer una fecha predeterminada
            valid_dates = temp_df_for_dates["Fecha_dt"].dropna()
            if not valid_dates.empty:
                default_start_date_hist = valid_dates.min().date()

        start_date_hist = st.date_input("Fecha de inicio (historial)", value=default_start_date_hist)

    with col_hist2:
        default_end_date_hist = datetime.date.today() # Valor por defecto a hoy
        if not st.session_state.transacciones_data.empty and "Fecha" in st.session_state.transacciones_data.columns:
            temp_df_for_dates = st.session_state.transacciones_data.copy()
            temp_df_for_dates["Fecha_dt"] = pd.to_datetime(temp_df_for_dates["Fecha"], errors='coerce')
            valid_dates = temp_df_for_dates["Fecha_dt"].dropna()
            if not valid_dates.empty:
                default_end_date_hist = valid_dates.max().date()

        end_date_hist = st.date_input("Fecha de fin (historial)", value=default_end_date_hist)


    historial_transacciones = st.session_state.transacciones_data[
        st.session_state.transacciones_data["Categoría"].astype(str).isin(
            ["Cobranza", "Anticipo Cliente", "Anticipo Aplicado"])
    ].copy() if not st.session_state.transacciones_data.empty else pd.DataFrame()

    if not historial_transacciones.empty:
        # Asegurarse de que la columna 'Fecha' sea datetime para el filtrado
        # Crear una copia para evitar SettingWithCopyWarning
        historial_transacciones["Fecha_dt"] = pd.to_datetime(historial_transacciones["Fecha"], errors='coerce')

        # Eliminar filas con fechas inválidas (NaT) antes de filtrar
        historial_transacciones.dropna(subset=['Fecha_dt'], inplace=True)


        # Aplicar filtro por fechas
        if start_date_hist:
            historial_transacciones = historial_transacciones[historial_transacciones["Fecha_dt"].dt.date >= start_date_hist]
        if end_date_hist:
            historial_transacciones = historial_transacciones[historial_transacciones["Fecha_dt"].dt.date <= end_date_hist]

        if all(col in historial_transacciones.columns for col in
               ["Fecha", "Cliente", "Descripción", "Monto", "Método de pago",
                "Categoría", "Tipo"]):
            df_historial_to_display_export = historial_transacciones[
                ["Fecha", "Cliente", "Descripción", "Monto", "Método de pago", "Categoría", "Tipo"]
            ].sort_values("Fecha", ascending=False)
            st.dataframe(df_historial_to_display_export, use_container_width=True)

            if not df_historial_to_display_export.empty:
                st.download_button(
                    label="Exportar historial a Excel",
                    data=to_excel(df_historial_to_display_export),
                    file_name="historial_pagos_anticipos.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.info("No hay pagos o anticipos en el rango de fechas seleccionado.")
        else:
            st.info("Columnas necesarias para el historial no encontradas. Asegúrese de que los datos sean correctos.")
    else:
        st.info("Aún no se han registrado pagos o anticipos.")