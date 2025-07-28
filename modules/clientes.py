import streamlit as st
import pandas as pd
import io # Importación necesaria para manejar datos en memoria para Excel
from utils.db import guardar_cliente, leer_clientes, actualizar_cliente

# Helper function to convert DataFrame to Excel
def to_excel(df):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Clientes') # Nombre de la hoja en Excel
    writer.close() # Importante cerrar el escritor para guardar el contenido
    processed_data = output.getvalue()
    return processed_data

def render():
    st.title("👥 Gestión de Clientes")

    # Siempre recargar la lista de clientes al inicio para asegurar que esté actualizada
    clientes_data = leer_clientes()
    st.session_state.clientes = pd.DataFrame(clientes_data)

    with st.form("form_clientes"):
        st.subheader("➕ Agregar nuevo cliente")
        id_cliente = st.text_input("🆔 Clave única del cliente (ID)", max_chars=20)
        nombre = st.text_input("Nombre")
        correo = st.text_input("Correo")
        telefono = st.text_input("Teléfono")
        empresa = st.text_input("Empresa")
        rfc = st.text_input("RFC")
        limite_credito = st.number_input("💳 Límite de crédito autorizado", min_value=0.0, step=100.0, format="%.2f")

        submitted = st.form_submit_button("Guardar cliente")

        if submitted:
            if not id_cliente:
                st.error("⚠️ Debes ingresar una clave única para el cliente.")
            elif id_cliente in st.session_state.clientes["ID"].values.astype(str): # Asegurarse de comparar tipos
                st.error("❌ Ya existe un cliente con esa clave única. Usa otra.")
            else:
                nuevo_cliente = {
                    "ID": id_cliente,
                    "Nombre": nombre,
                    "Correo": correo,
                    "Teléfono": telefono,
                    "Empresa": empresa,
                    "RFC": rfc,
                    "Límite de crédito": limite_credito
                }
                guardar_cliente(id_cliente, nuevo_cliente)
                # No necesitas crear un nuevo df y concatenar, simplemente recarga de la fuente de datos
                # para asegurar la consistencia.
                st.session_state.clientes = pd.DataFrame(leer_clientes()) # Recargar después de guardar
                st.success("✅ Cliente guardado correctamente")

    st.divider()

    st.subheader("✏️ Editar cliente existente")
    if not st.session_state.clientes.empty:
        # Asegurarse de que 'ID' y 'Nombre' son tratados como strings antes de concatenar
        st.session_state.clientes["ID-Nombre"] = st.session_state.clientes["ID"].astype(str) + " - " + st.session_state.clientes["Nombre"].astype(str)
        seleccion = st.selectbox("Selecciona un cliente para editar", st.session_state.clientes["ID-Nombre"].tolist(), key="select_cliente_edit")
        id_seleccionado = seleccion.split(" - ")[0]

        cliente_original = st.session_state.clientes[st.session_state.clientes["ID"].astype(str) == id_seleccionado].iloc[0]

        with st.form("form_editar_cliente"):
            # Usar claves únicas para los widgets dentro del formulario de edición
            nombre_edit = st.text_input("Nombre", value=cliente_original["Nombre"], key="edit_nombre")
            correo_edit = st.text_input("Correo", value=cliente_original["Correo"], key="edit_correo")
            telefono_edit = st.text_input("Teléfono", value=cliente_original["Teléfono"], key="edit_telefono")
            empresa_edit = st.text_input("Empresa", value=cliente_original["Empresa"], key="edit_empresa")
            rfc_edit = st.text_input("RFC", value=cliente_original["RFC"], key="edit_rfc")
            limite_credito_edit = st.number_input("💳 Límite de crédito autorizado", min_value=0.0,
                                                  value=float(cliente_original["Límite de crédito"]), # Convertir a float si es necesario
                                                  step=100.0, format="%.2f", key="edit_limite_credito")

            actualizar = st.form_submit_button("Actualizar cliente")

            if actualizar:
                cliente_actualizado = {
                    "ID": id_seleccionado,
                    "Nombre": nombre_edit,
                    "Correo": correo_edit,
                    "Teléfono": telefono_edit,
                    "Empresa": empresa_edit,
                    "RFC": rfc_edit,
                    "Límite de crédito": limite_credito_edit
                }
                actualizar_cliente(id_seleccionado, cliente_actualizado)
                # Recargar la lista de clientes desde la fuente de datos para reflejar los cambios
                st.session_state.clientes = pd.DataFrame(leer_clientes())
                st.success("✅ Cliente actualizado correctamente")
    else:
        st.info("No hay clientes para editar.")


    st.divider()
    st.subheader("📋 Lista de clientes")

    # Asegurarse de que la columna "ID-Nombre" no se muestre si no es relevante para el usuario final
    # Podemos crear una copia del DataFrame para mostrar si queremos ocultar columnas temporales.
    df_to_display = st.session_state.clientes.copy()
    if "ID-Nombre" in df_to_display.columns:
        df_to_display = df_to_display.drop(columns=["ID-Nombre"])

    st.dataframe(df_to_display, use_container_width=True)

    # --- Botón para exportar a Excel ---
    if not st.session_state.clientes.empty:
        st.download_button(
            label="Exportar lista de clientes a Excel",
            data=to_excel(df_to_display), # Usar el DataFrame limpio para exportar
            file_name="lista_clientes.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("No hay clientes para exportar.")