# modules/productos.py

import streamlit as st
import io
import pandas as pd
import datetime
from utils.db import (
    guardar_producto,
    leer_productos,
    actualizar_producto_por_clave,
    eliminar_producto_por_clave,
    guardar_transaccion
)


# Helper function to convert DataFrame to Excel
def to_excel(df):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Productos') # 'Productos' es el nombre de la hoja en Excel
    writer.close() # Importante cerrar el escritor para guardar el contenido
    processed_data = output.getvalue()
    return processed_data


def render():
    st.title("📦 Gestión de Productos")

    # Cargar productos desde Firestore
    # Siempre recargar para tener los datos más recientes, especialmente después de actualizaciones
    productos_data = leer_productos()
    st.session_state.productos = pd.DataFrame(productos_data)

    # Asegurar columnas necesarias
    columnas_necesarias = ["Clave", "Nombre", "Categoría", "Precio Unitario", "Costo Unitario", "Cantidad",
                           "Descripción"]
    for col in columnas_necesarias:
        if col not in st.session_state.productos.columns:
            st.session_state.productos[col] = pd.Series(dtype="object")

    # Campos temporales para el formulario de agregar
    valores_iniciales_agregar = {
        "clave_add": "",
        "nombre_add": "",
        "categoria_add": "Producto",
        "precio_add": 0.0,
        "costo_add": 0.0,
        "cantidad_add": 0,
        "descripcion_add": ""
    }
    for campo, valor in valores_iniciales_agregar.items():
        if campo not in st.session_state:
            st.session_state[campo] = valor

    # Botón limpiar campos del formulario de agregar
    if st.button("🧹 Limpiar campos (Agregar Producto)"):
        for campo, valor in valores_iniciales_agregar.items():
            st.session_state[campo] = valor
        st.rerun()

    # Formulario de producto (Agregar Nuevo)
    with st.form("form_productos_agregar"):
        st.subheader("Agregar nuevo producto/servicio")
        clave = st.text_input("Clave del producto", value=st.session_state.clave_add, key="clave_add")
        nombre = st.text_input("Nombre", value=st.session_state.nombre_add, key="nombre_add")
        categoria = st.selectbox("Categoría", ["Producto", "Servicio", "Otro"], key="categoria_add")
        precio = st.number_input("Precio Unitario", min_value=0.0, format="%.2f",
                                 value=float(st.session_state.precio_add),
                                 key="precio_add")
        costo = st.number_input("Costo Unitario", min_value=0.0, format="%.2f", value=float(st.session_state.costo_add),
                                key="costo_add")
        cantidad = st.number_input("Cantidad en inventario", min_value=0, step=1,
                                   value=int(st.session_state.cantidad_add),
                                   key="cantidad_add")
        descripcion = st.text_area("Descripción", value=st.session_state.descripcion_add, key="descripcion_add")
        submitted_add = st.form_submit_button("Guardar nuevo producto")

        if submitted_add:
            if "Clave" not in st.session_state.productos.columns:
                st.session_state.productos["Clave"] = pd.Series(dtype="object")

            if clave in st.session_state.productos["Clave"].values:
                st.error(f"❌ Ya existe un producto con la clave '{clave}'. Usa una clave distinta.")
            elif precio <= 0 or costo < 0 or cantidad <= 0:
                st.warning("⚠️ El precio y la cantidad deben ser mayores a cero. El costo no puede ser negativo.")
            else:
                nuevo_producto = {
                    "Clave": clave,
                    "Nombre": nombre,
                    "Categoría": categoria,
                    "Precio Unitario": precio,
                    "Costo Unitario": costo,
                    "Cantidad": cantidad,
                    "Descripción": descripcion
                }
                guardar_producto(nuevo_producto)
                # Recargar productos para reflejar el cambio en el DataFrame de sesión
                st.session_state.productos = pd.DataFrame(leer_productos())
                st.success("✅ Producto guardado en Firestore y agregado al catálogo")

                # --- Registrar el egreso por la compra del nuevo inventario ---
                if costo * cantidad > 0:
                    transaccion_costo = {
                        "Fecha": datetime.date.today().isoformat(),
                        "Descripción": f"Compra inicial de inventario: {nombre} ({cantidad} unidades)",
                        "Categoría": "Compras",
                        "Tipo": "Egreso",  # Cambiado a Egreso
                        "Monto": float(costo * cantidad),
                        "Cliente": "N/A",
                        "Método de pago": "N/A"
                    }
                    guardar_transaccion(transaccion_costo)
                    st.info(f"🛒 Costo de ${costo * cantidad:.2f} registrado como egreso en contabilidad.")
                # --- FIN del registro de egreso ---
            st.rerun()  # Para limpiar el formulario y actualizar las tablas

    st.divider()
    st.subheader("📋 Inventario / Catálogo")

    filtro = st.text_input("Buscar por clave o nombre", key="filtro_inventario")
    if filtro:
        df_filtrado = st.session_state.productos[
            st.session_state.productos["Clave"].str.contains(filtro, case=False, na=False) |
            st.session_state.productos["Nombre"].str.contains(filtro, case=False, na=False)
            ]
        st.dataframe(df_filtrado, use_container_width=True)

        # Botón de descarga para el DataFrame filtrado
        if not df_filtrado.empty:
            st.download_button(
                label="Descargar catálogo filtrado a Excel",
                data=to_excel(df_filtrado),
                file_name="catalogo_productos_filtrado.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("No hay productos que coincidan con el filtro.")
    else:
        st.dataframe(st.session_state.productos, use_container_width=True)

        # Botón de descarga para todo el catálogo
        if not st.session_state.productos.empty:
            st.download_button(
                label="Descargar catálogo completo a Excel",
                data=to_excel(st.session_state.productos),
                file_name="catalogo_productos_completo.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("No hay productos registrados para exportar.")

    st.divider()
    st.subheader("➕ Dar entrada a productos existentes (Reabastecimiento)")

    if not st.session_state.productos.empty:
        claves_existentes = st.session_state.productos["Clave"].dropna().unique().tolist()

        # Usamos un form distinto para esta sección
        with st.form("form_entrada_existente"):
            producto_a_reabastecer = st.selectbox("Selecciona producto a reabastecer", claves_existentes,
                                                  key="select_reabastecer")

            # Obtener datos del producto seleccionado para mostrar info y pre-llenar costo
            datos_producto_reabastecer = st.session_state.productos[
                st.session_state.productos["Clave"] == producto_a_reabastecer
                ].iloc[0]

            st.write(
                f"Producto seleccionado: **{datos_producto_reabastecer['Nombre']}** (Stock actual: {int(datos_producto_reabastecer['Cantidad'])})")

            cantidad_entrada = st.number_input(
                "Cantidad a añadir al inventario",
                min_value=1,
                step=1,
                value=1,
                key="cantidad_entrada_reabastecer"
            )
            # El costo unitario se toma del producto existente, o se permite modificarlo
            costo_unitario_entrada = st.number_input(
                "Costo Unitario de esta entrada",
                min_value=0.0,
                format="%.2f",
                value=float(datos_producto_reabastecer.get("Costo Unitario", 0.0)),
                key="costo_unitario_entrada"
            )

            submitted_entrada = st.form_submit_button("Registrar entrada")

            if submitted_entrada:
                if cantidad_entrada <= 0:
                    st.warning("⚠️ La cantidad a añadir debe ser mayor a cero.")
                else:
                    # Actualizar cantidad en Firestore
                    nueva_cantidad_total = int(datos_producto_reabastecer["Cantidad"]) + cantidad_entrada
                    actualizar_producto_por_clave(producto_a_reabastecer, {
                        "Cantidad": nueva_cantidad_total,
                        "Costo Unitario": costo_unitario_entrada
                        # Opcional: actualizar el costo unitario promedio o mantener el último
                    })

                    # Actualizar el DataFrame en session_state para reflejar el cambio inmediatamente
                    idx = \
                    st.session_state.productos.index[st.session_state.productos["Clave"] == producto_a_reabastecer][0]
                    st.session_state.productos.at[idx, "Cantidad"] = nueva_cantidad_total
                    st.session_state.productos.at[
                        idx, "Costo Unitario"] = costo_unitario_entrada  # Actualizamos también el costo

                    st.success(
                        f"✅ Se añadieron {cantidad_entrada} unidades de {datos_producto_reabastecer['Nombre']}. Nuevo stock: {nueva_cantidad_total}")

                    # --- Registrar el egreso por el reabastecimiento ---
                    costo_total_entrada = float(costo_unitario_entrada * cantidad_entrada)
                    if costo_total_entrada > 0:
                        transaccion_entrada = {
                            "Fecha": datetime.date.today().isoformat(),
                            "Descripción": f"Reabastecimiento de inventario: {datos_producto_reabastecer['Nombre']} ({cantidad_entrada} unidades)",
                            "Categoría": "Compras",
                            "Tipo": "Egreso",  # Cambiado a Egreso
                            "Monto": costo_total_entrada,
                            "Cliente": "N/A",
                            "Método de pago": "N/A"
                        }
                        guardar_transaccion(transaccion_entrada)
                        st.info(
                            f"🛒 Costo de reabastecimiento de ${costo_total_entrada:.2f} registrado como egreso en contabilidad.")
                    # --- FIN del registro de egreso ---
                st.rerun()  # Para limpiar el formulario y actualizar las tablas
    else:
        st.info("No hay productos registrados para reabastecer.")

    st.divider()
    st.subheader("🛠️ Editar producto (Precio, Costo, Descripción)")

    if not st.session_state.productos.empty:
        claves_disponibles_editar = st.session_state.productos["Clave"].dropna().unique().tolist()
        seleccionado_editar = st.selectbox("Selecciona un producto para editar", claves_disponibles_editar,
                                           key="select_editar")
        filtro_editar = st.session_state.productos["Clave"] == seleccionado_editar

        if filtro_editar.any():
            datos_editar = st.session_state.productos[filtro_editar].iloc[0]

            # Campos solo para edición, no para añadir stock
            nuevo_precio = st.number_input("Nuevo precio", value=float(datos_editar["Precio Unitario"]), format="%.2f",
                                           key="nuevo_precio_edit")
            nuevo_costo = st.number_input("Nuevo costo unitario", value=float(datos_editar.get("Costo Unitario", 0.0)),
                                          format="%.2f", key="nuevo_costo_edit")
            nueva_descripcion = st.text_area("Nueva descripción", value=datos_editar["Descripción"],
                                             key="nueva_descripcion_edit")

            col1_edit, col2_edit = st.columns(2)
            with col1_edit:
                if st.button("✏️ Actualizar detalles del producto"):
                    actualizar_producto_por_clave(seleccionado_editar, {
                        "Precio Unitario": nuevo_precio,
                        "Costo Unitario": nuevo_costo,
                        "Descripción": nueva_descripcion
                    })
                    idx = st.session_state.productos.index[st.session_state.productos["Clave"] == seleccionado_editar][
                        0]
                    st.session_state.productos.at[idx, "Precio Unitario"] = nuevo_precio
                    st.session_state.productos.at[idx, "Costo Unitario"] = nuevo_costo
                    st.session_state.productos.at[idx, "Descripción"] = nueva_descripcion
                    st.success("✅ Detalles del producto actualizados.")
                    st.rerun()

            with col2_edit:
                if st.button("🗑️ Eliminar producto", key="eliminar_producto_btn"):
                    eliminar_producto_por_clave(seleccionado_editar)
                    st.session_state.productos = st.session_state.productos[
                        st.session_state.productos["Clave"] != seleccionado_editar
                        ]
                    st.success("✅ Producto eliminado del inventario y Firestore")
                    st.rerun()
    else:
        st.info("No hay productos para editar o eliminar.")