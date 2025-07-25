# modules/ventas.py

import streamlit as st
import pandas as pd
import plotly.express as px
from utils.db import guardar_venta, leer_ventas, leer_transacciones, guardar_transaccion, leer_clientes, leer_productos, \
    actualizar_producto_por_clave


def render():
    st.title("💸 Ventas")

    # --- Definir columnas numéricas al principio para asegurar su disponibilidad ---
    numeric_cols_ventas = ["Cantidad", "Precio Unitario", "Total", "Monto Crédito", "Monto Contado",
                           "Anticipo Aplicado"]

    # Validar clientes y productos cargados en sesión
    if "clientes" not in st.session_state or st.session_state.clientes.empty:
        st.session_state.clientes = leer_clientes()
        if st.session_state.clientes.empty:
            st.warning("⚠️ No hay clientes registrados. Agrega alguno en 'Clientes'.")
            st.stop()

    if "productos" not in st.session_state or st.session_state.productos.empty:
        st.session_state.productos = leer_productos()
        if st.session_state.productos.empty:
            st.warning("⚠️ No hay productos registrados. Agrega uno en 'Productos'.")
            st.stop()

    # Cargar ventas y transacciones si no están o recargarlas para asegurar tipos de datos
    # Mantenemos esto fuera del if submitted para que la UI siempre muestre datos frescos
    st.session_state.ventas = leer_ventas()
    for col in numeric_cols_ventas:
        if col in st.session_state.ventas.columns:
            st.session_state.ventas[col] = pd.to_numeric(st.session_state.ventas[col], errors='coerce').fillna(0.0)

    st.session_state.transacciones_data = leer_transacciones()
    if "Monto" in st.session_state.transacciones_data.columns:
        st.session_state.transacciones_data["Monto"] = pd.to_numeric(st.session_state.transacciones_data["Monto"],
                                                                     errors='coerce').fillna(0.0)

    st.subheader("Registrar nueva venta")

    # --- CAMPOS QUE DEBEN ACTUALIZARSE AL CAMBIAR SU VALOR (FUERA DEL FORM) ---
    fecha = st.date_input("Fecha", key="venta_fecha")
    cliente = st.selectbox("Cliente", st.session_state.clientes["Nombre"].tolist(), key="venta_cliente")

    # --- CAMBIOS AQUÍ para mostrar la existencia ---
    producto = st.selectbox("Producto/Servicio", st.session_state.productos["Nombre"].tolist(), key="venta_producto")

    existencia_actual = 0
    producto_info_selected = pd.DataFrame()  # Inicializar como DataFrame vacío
    if producto and not st.session_state.productos.empty:
        producto_info_selected = st.session_state.productos[st.session_state.productos["Nombre"] == producto]
        if not producto_info_selected.empty and "Cantidad" in producto_info_selected.columns:
            existencia_actual = int(producto_info_selected["Cantidad"].values[0])
        st.info(f"📦 Existencia actual: **{existencia_actual}** unidades.")
    # --- FIN CAMBIOS para mostrar la existencia ---

    cantidad = st.number_input("Cantidad", min_value=1, key="venta_cantidad")

    # Validar que la cantidad no exceda la existencia
    if cantidad > existencia_actual and existencia_actual >= 0:  # Solo si hay existencia definida
        st.warning(f"⚠️ La cantidad solicitada ({cantidad}) excede la existencia actual ({existencia_actual}).")
        # Opcional: Deshabilitar el botón de submit o ajustar la cantidad automáticamente
        # st.session_state.venta_cantidad = existencia_actual # Esto podría forzar la cantidad

    # Calcular precio y total EN TIEMPO REAL (para la UI antes del submit)
    precio = 0.0
    if not producto_info_selected.empty and "Precio Unitario" in producto_info_selected.columns:
        precio_from_df = producto_info_selected["Precio Unitario"].values[0]
        precio = float(precio_from_df) if pd.notna(precio_from_df) else 0.0
    total_ui_display = cantidad * precio  # Usar una variable diferente para evitar confusión

    st.markdown(f"**Precio unitario:** ${precio:.2f}")
    st.markdown(f"**Total de la venta:** ${total_ui_display:.2f}")

    # --- Lógica y UI para Anticipos Disponibles (VISIBLES) ---
    anticipos_cliente_total = st.session_state.transacciones_data[
        (st.session_state.transacciones_data["Categoría"] == "Anticipo Cliente") &
        (st.session_state.transacciones_data["Cliente"] == cliente) &
        (st.session_state.transacciones_data["Tipo"] == "Ingreso")
        ]["Monto"].sum()

    anticipos_aplicados_total = st.session_state.transacciones_data[
        (st.session_state.transacciones_data["Categoría"] == "Anticipo Aplicado") &
        (st.session_state.transacciones_data["Cliente"] == cliente) &
        (st.session_state.transacciones_data["Tipo"] == "Gasto")  # Asegúrate que esto sea consistente con tu db.py
        ]["Monto"].sum()

    saldo_anticipos = float(anticipos_cliente_total) - float(anticipos_aplicados_total)

    aplicar_anticipo = 0.0  # Inicializar a 0.0
    if saldo_anticipos > 0:
        st.subheader("Gestión de Anticipos")
        st.info(f"✨ **Anticipo disponible para {cliente}:** ${saldo_anticipos:.2f}")

        # Permitir al usuario decidir cuánto anticipo aplicar
        # El valor máximo es el mínimo entre el saldo disponible y el total de la venta (el que se muestra en UI)
        aplicar_anticipo = st.number_input(
            f"¿Cuánto anticipo desea aplicar a esta venta?",
            min_value=0.0,
            max_value=min(saldo_anticipos, total_ui_display),  # Usar total_ui_display aquí
            value=0.0,  # Valor inicial en 0, para que el usuario decida
            step=0.01,
            key="input_anticipo_visible"
        )
        st.session_state["anticipo_seleccionado_para_venta"] = aplicar_anticipo  # Guardar en session_state
    else:
        # Si no hay anticipos disponibles, asegurar que el valor en session_state sea 0
        st.session_state["anticipo_seleccionado_para_venta"] = 0.0

    # --- FIN Lógica y UI para Anticipos Disponibles ---

    # Calcular el total ajustado después de aplicar el anticipo (para la UI)
    total_ajustado_ui_display = total_ui_display - aplicar_anticipo
    st.markdown(f"**Total de la venta (ajustado por anticipo):** ${total_ajustado_ui_display:.2f}")

    # --- INICIO DEL FORMULARIO PRINCIPAL DE VENTA ---
    with st.form("form_ventas"):
        cliente_info = st.session_state.clientes[st.session_state.clientes["Nombre"] == cliente].iloc[0]
        limite_credito_raw = cliente_info.get("Límite de crédito", 0.0)
        try:
            limite_credito = float(limite_credito_raw) if pd.notna(limite_credito_raw) else 0.0
        except Exception:
            st.warning("⚠️ El límite de crédito del cliente no es válido. Se asignará 0.")
            limite_credito = 0.0

        # Filtrar pagos de cobranza para el cliente (para crédito)
        pagos = st.session_state.transacciones_data[  # Usar session_state.transacciones_data
            (st.session_state.transacciones_data["Categoría"] == "Cobranza") & (
                    st.session_state.transacciones_data["Cliente"] == cliente)
            ]
        pagos_realizados = pagos["Monto"].sum() if not pagos.empty else 0.0
        pagos_realizados = float(pagos_realizados)

        ventas_cliente = st.session_state.ventas[st.session_state.ventas["Cliente"] == cliente]

        total_credito_otorgado = 0.0
        if "Tipo de venta" in ventas_cliente.columns and "Monto Crédito" in ventas_cliente.columns:
            credito_otorgado_series = ventas_cliente[
                ventas_cliente["Tipo de venta"].isin(["Crédito", "Mixta"])
            ]["Monto Crédito"]
            total_credito_otorgado = float(credito_otorgado_series.sum()) if not credito_otorgado_series.empty else 0.0

        credito_usado = float(total_credito_otorgado) - float(pagos_realizados)
        credito_disponible = float(limite_credito) - float(credito_usado)

        st.markdown(f"💳 **Crédito autorizado:** ${limite_credito:.2f}")
        st.markdown(f"🔸 **Crédito usado:** ${credito_usado:.2f}")
        st.markdown(f"🟢 **Disponible para crédito:** ${credito_disponible:.2f}")

        # Monto contado y método de pago
        # El max_value debe ser el total ajustado, no el total original
        monto_contado = st.number_input("💵 Monto pagado al contado", min_value=0.0,
                                        max_value=float(total_ajustado_ui_display),  # Usar el total ajustado para UI
                                        step=0.01, key="venta_monto_contado_final")
        metodo_pago = st.selectbox("Método de pago (contado)", ["Efectivo", "Transferencia", "Tarjeta"],
                                   key="venta_metodo_pago_final")

        monto_credito = total_ajustado_ui_display - monto_contado  # Calcular basado en el total ajustado para UI
        st.markdown(f"**🧾 Crédito solicitado:** ${monto_credito:.2f}")

        submitted = st.form_submit_button("Registrar venta")

        if submitted:
            # --- RECARGAR DATOS FRESCOS JUSTO ANTES DE PROCESAR ---
            # Esto es CRÍTICO para asegurar que las validaciones se hagan con los valores más actuales
            st.session_state.ventas = leer_ventas()
            for col in numeric_cols_ventas:
                if col in st.session_state.ventas.columns:
                    st.session_state.ventas[col] = pd.to_numeric(st.session_state.ventas[col], errors='coerce').fillna(
                        0.0)

            st.session_state.transacciones_data = leer_transacciones()
            if "Monto" in st.session_state.transacciones_data.columns:
                st.session_state.transacciones_data["Monto"] = pd.to_numeric(
                    st.session_state.transacciones_data["Monto"],
                    errors='coerce').fillna(0.0)
            st.session_state.productos = leer_productos()  # Recargar productos para existencia y precio

            # --- OBTENER VALORES ACTUALES DE LOS INPUTS DEL FORMULARIO ---
            # Estos son los valores que el usuario ingresó y que están en los widgets
            submitted_fecha = fecha
            submitted_cliente = cliente
            submitted_producto = producto
            submitted_cantidad = cantidad  # Ya es el valor del number_input
            submitted_monto_contado = monto_contado  # Ya es el valor del number_input
            submitted_metodo_pago = metodo_pago

            # --- RECALCULAR PRECIO Y EXISTENCIA AL MOMENTO DEL SUBMIT CON DATOS FRESCOS ---
            current_producto_info = st.session_state.productos[
                st.session_state.productos["Nombre"] == submitted_producto]

            current_existencia = 0
            if not current_producto_info.empty and "Cantidad" in current_producto_info.columns:
                current_existencia = int(current_producto_info["Cantidad"].values[0])

            submitted_precio = 0.0
            if not current_producto_info.empty and "Precio Unitario" in current_producto_info.columns:
                submitted_precio = float(current_producto_info["Precio Unitario"].values[0])

            # --- RECALCULAR TOTALES Y COMPONENTES CON LOS VALORES DEL SUBMIT ---
            submitted_total_original = submitted_cantidad * submitted_precio

            # Recuperar el valor del anticipo que el usuario seleccionó y está en session_state
            anticipo_final_aplicado = st.session_state.get("anticipo_seleccionado_para_venta", 0.0)

            submitted_total_ajustado = submitted_total_original - anticipo_final_aplicado

            # El monto_credito_f DEBE ser la diferencia entre el total ajustado y el monto contado
            monto_credito_f = submitted_total_ajustado - submitted_monto_contado

            # Asegurar que los montos no sean negativos debido a flotantes
            monto_credito_f = max(0.0, monto_credito_f)
            submitted_monto_contado = max(0.0, submitted_monto_contado)
            anticipo_final_aplicado = max(0.0, anticipo_final_aplicado)

            # --- RECALCULAR CRÉDITO DISPONIBLE AL MOMENTO DEL SUBMIT CON DATOS FRESCOS ---
            current_cliente_info = \
                st.session_state.clientes[st.session_state.clientes["Nombre"] == submitted_cliente].iloc[0]
            current_limite_credito = float(current_cliente_info.get("Límite de crédito", 0.0))

            current_pagos = st.session_state.transacciones_data[
                (st.session_state.transacciones_data["Categoría"] == "Cobranza") & (
                        st.session_state.transacciones_data["Cliente"] == submitted_cliente)
                ]
            current_pagos_realizados = current_pagos["Monto"].sum() if not current_pagos.empty else 0.0

            current_ventas_cliente = st.session_state.ventas[st.session_state.ventas["Cliente"] == submitted_cliente]
            current_total_credito_otorgado = 0.0
            if "Tipo de venta" in current_ventas_cliente.columns and "Monto Crédito" in current_ventas_cliente.columns:
                current_credito_otorgado_series = current_ventas_cliente[
                    current_ventas_cliente["Tipo de venta"].isin(["Crédito", "Mixta"])
                ]["Monto Crédito"]
                current_total_credito_otorgado = float(
                    current_credito_otorgado_series.sum()) if not current_credito_otorgado_series.empty else 0.0

            current_credito_usado = float(current_total_credito_otorgado) - float(current_pagos_realizados)
            current_credito_disponible = float(current_limite_credito) - float(current_credito_usado)

            # --- DEBUG: Mostrar valores clave al momento del SUBMIT ---
            # st.subheader("DEBUG: Valores al momento del Submit")
            # st.write(f"submitted_fecha: {submitted_fecha}")
            # st.write(f"submitted_cliente: {submitted_cliente}")
            # st.write(f"submitted_producto: {submitted_producto}")
            # st.write(f"submitted_cantidad: {submitted_cantidad}")
            # st.write(f"submitted_precio (recalculado): {submitted_precio}")
            # st.write(f"submitted_total_original (recalculado): {submitted_total_original}")
            # st.write(f"anticipo_final_aplicado (del session_state): {anticipo_final_aplicado}")
            # st.write(f"submitted_total_ajustado (recalculado): {submitted_total_ajustado}")
            # st.write(f"submitted_monto_contado (del form): {submitted_monto_contado}")
            # st.write(f"monto_credito_f (recalculado): {monto_credito_f}")
            # st.write(f"current_existencia: {current_existencia}")
            # st.write(f"current_credito_disponible: {current_credito_disponible}")
            # --- FIN DEBUG ---

            suma_componentes = submitted_monto_contado + monto_credito_f + anticipo_final_aplicado

            # Definir una pequeña tolerancia para la comparación de punto flotante
            epsilon = 0.01  # Tolerancia de un centavo

            diferencia = abs(round(suma_componentes, 2) - round(submitted_total_original, 2))

            # Validaciones finales
            if submitted_cantidad > current_existencia and current_existencia >= 0:
                st.error(
                    f"❌ No hay suficiente existencia de {submitted_producto}. Solo quedan {current_existencia} unidades.")
            elif abs(round(suma_componentes, 2) - round(submitted_total_original,
                                                        2)) > epsilon:  # Comparar contra el total original recalculado
                st.error(
                    "❌ El total ingresado (contado + crédito + anticipo) no coincide con el total de la venta original. "
                    f"Desfase: {abs(round(suma_componentes, 2) - round(submitted_total_original, 2)):.4f}"
                )
            elif monto_credito_f > current_credito_disponible + epsilon:  # Añadir epsilon aquí también para seguridad
                st.error(
                    f"❌ El crédito solicitado (${monto_credito_f:.2f}) excede el disponible (${current_credito_disponible:.2f}).")
            else:
                # Determinar Tipo de Venta correctamente
                tipo_venta = ""
                if monto_credito_f > 0 and (submitted_monto_contado > 0 or anticipo_final_aplicado > 0):
                    tipo_venta = "Mixta"
                elif monto_credito_f > 0 and submitted_monto_contado == 0 and anticipo_final_aplicado == 0:
                    tipo_venta = "Crédito"
                elif monto_credito_f == 0 and (submitted_monto_contado > 0 or anticipo_final_aplicado > 0):
                    tipo_venta = "Contado"  # Puede ser 'Contado' si solo es anticipo, o solo efectivo
                elif monto_credito_f == 0 and submitted_monto_contado == 0 and anticipo_final_aplicado == 0 and submitted_total_original == 0:  # Usar submitted_total_original
                    tipo_venta = "Gratuita"
                else:
                    tipo_venta = "Indefinido"  # Fallback si no encaja

                venta_dict = {
                    "Fecha": submitted_fecha.isoformat(),
                    "Cliente": submitted_cliente,
                    "Producto": submitted_producto,
                    "Cantidad": float(submitted_cantidad),
                    "Precio Unitario": float(submitted_precio),
                    "Total": submitted_total_original,  # Guardar el total original de la venta recalculado
                    "Monto Crédito": monto_credito_f,
                    "Monto Contado": submitted_monto_contado,
                    "Anticipo Aplicado": anticipo_final_aplicado,  # Usar el valor decidido por el usuario
                    "Método de pago": submitted_metodo_pago if submitted_monto_contado > 0 else (
                        "Crédito" if monto_credito_f > 0 else (
                            "Anticipo" if anticipo_final_aplicado > 0 else "N/A"
                        )
                    ),
                    "Tipo de venta": tipo_venta
                }
                guardar_venta(venta_dict)

                if submitted_monto_contado > 0:
                    guardar_transaccion({
                        "Fecha": submitted_fecha.isoformat(),
                        "Descripción": f"Pago de contado por venta a {submitted_cliente}",
                        "Categoría": "Ventas",
                        "Tipo": "Ingreso",
                        "Monto": submitted_monto_contado,
                        "Cliente": submitted_cliente,
                        "Método de pago": submitted_metodo_pago
                    })

                if anticipo_final_aplicado > 0:
                    guardar_transaccion({
                        "Fecha": submitted_fecha.isoformat(),
                        "Descripción": f"Anticipo aplicado a venta de {submitted_cliente}",
                        "Categoría": "Anticipo Aplicado",
                        "Tipo": "Gasto",  # Desde la perspectiva del anticipo, es una reducción
                        "Monto": float(anticipo_final_aplicado),
                        "Cliente": submitted_cliente,
                        "Método de pago": "Anticipo"  # Método de pago específico
                    })

                # --- DESCONTAR CANTIDAD DEL INVENTARIO ---
                producto_clave = st.session_state.productos.loc[
                    st.session_state.productos["Nombre"] == submitted_producto, "Clave"].iloc[0]
                nueva_cantidad_inventario = current_existencia - submitted_cantidad
                actualizar_producto_por_clave(producto_clave, {"Cantidad": nueva_cantidad_inventario})
                # --- FIN DESCUENTO INVENTARIO ---

                # La actualización de st.session_state.ventas y transacciones_data ya se hace al inicio
                # y al final de este bloque, lo cual es redundante pero asegura la UI fresca.
                # Se puede simplificar si se quiere optimizar, pero por ahora está bien para depuración.
                st.session_state.ventas = leer_ventas()
                st.session_state.transacciones_data = leer_transacciones()
                st.session_state.productos = leer_productos()  # ¡Actualizar productos también!

                st.success("✅ Venta registrada correctamente")
                st.rerun()  # Volver a renderizar para limpiar el formulario y mostrar la venta reciente

    st.divider()
    st.subheader("📋 Histórico de ventas")
    st.dataframe(st.session_state.ventas, use_container_width=True)

    if not st.session_state.ventas.empty:
        st.subheader("📊 Ingresos diarios")
        df_daily = st.session_state.ventas.copy()
        df_daily["Total"] = pd.to_numeric(df_daily["Total"], errors='coerce').fillna(0.0)
        df_daily = df_daily.groupby("Fecha")["Total"].sum().reset_index()
        fig = px.bar(df_daily, x="Fecha", y="Total", title="Ventas por día", template="plotly_white")
        st.plotly_chart(fig, use_container_width=True)