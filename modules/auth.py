import streamlit as st
import firebase_admin
from firebase_admin import auth
import datetime

def registrar_usuario(correo, contrasena):
    try:
        user = auth.create_user(
            email=correo,
            password=contrasena
        )
        st.success("✅ Usuario registrado correctamente")
    except Exception as e:
        st.error(f"❌ Error al registrar usuario: {e}")

def iniciar_sesion(correo, contrasena):
    try:
        st.session_state.usuario = correo
        st.success("✅ Inicio de sesión exitoso")
        st.success("Inicio de sesión exitoso. Redirigiendo...")
        st.rerun()
    except Exception as e:
        st.error(f"❌ Error al iniciar sesión: {e}")

def cerrar_sesion():
    if "usuario" in st.session_state:
        del st.session_state.usuario
        st.success("👋 Sesión cerrada exitosamente")

def recuperar_contrasena(correo):
    try:
        link = auth.generate_password_reset_link(correo)
        st.info(f"🔐 Enlace de recuperación enviado: {link}")
    except Exception as e:
        st.error(f"❌ Error al enviar recuperación: {e}")

def mostrar_login():
    # 🔷 TÍTULO y SUBTÍTULO
    st.markdown("""
        <div style='text-align: center; margin-bottom: 2rem;'>
            <h1 style='color: #2C3E50;'>💼 MiNegocio Pro</h1>
            <h4 style='color: #7F8C8D;'>- By Xibalbá Business -</h4>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("### 🔐 Iniciar sesión o Registrarse")
    opcion = st.radio("Selecciona una opción", ["Iniciar sesión", "Registrar nuevo", "Recuperar contraseña"])

    if opcion == "Iniciar sesión":
        correo = st.text_input("Correo")
        contrasena = st.text_input("Contraseña", type="password")
        if st.button("Iniciar sesión"):
            iniciar_sesion(correo, contrasena)

    elif opcion == "Registrar nuevo":
        correo = st.text_input("Correo")
        contrasena = st.text_input("Contraseña", type="password")
        if st.button("Registrar"):
            registrar_usuario(correo, contrasena)

    elif opcion == "Recuperar contraseña":
        correo = st.text_input("Correo para recuperación")
        if st.button("Enviar recuperación"):
            recuperar_contrasena(correo)

def mostrar_logout():
    if "usuario" in st.session_state:
        st.sidebar.markdown(f"👤 Usuario: **{st.session_state.usuario}**")
        if st.sidebar.button("Cerrar sesión"):
            cerrar_sesion()