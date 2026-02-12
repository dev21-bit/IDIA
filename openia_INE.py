import streamlit as st
import base64
import json
import pandas as pd
import pymysql
import re
from openai import OpenAI

# =====================================================
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# =====================================================
def get_connection():
    return pymysql.connect(
        host=st.secrets["DB_HOST"],
        user=st.secrets["DB_USER"],
        password=st.secrets["DB_PASSWORD"],
        database=st.secrets["DB_NAME"],
        port=st.secrets["DB_PORT"],
        cursorclass=pymysql.cursors.DictCursor
    )

# =====================================================
def validar_pin(pin):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT nombre, pin FROM usuarios WHERE pin=%s", (pin,))
            return cursor.fetchone()  # devuelve None si no existe, o dict con nombre y pin
    finally:
        conn.close()

# =====================================================
def limpiar_anio(valor):
    if not valor:
        return None
    match = re.search(r"\d{4}", str(valor))
    if match:
        return int(match.group())
    return None

def normalizar_clave(valor):
    if not valor:
        return None
    valor = str(valor).upper()
    valor = re.sub(r"\s+", "", valor)
    valor = re.sub(r"[^A-Z0-9]", "", valor)
    return valor

def extraer_json(texto):
    texto = re.sub(r"```json", "", texto)
    texto = re.sub(r"```", "", texto)
    match = re.search(r"\{.*\}", texto, re.DOTALL)
    if match:
        return match.group()
    return texto.strip()

# =====================================================
def crear_tabla():
    conn = get_connection()
    with conn.cursor() as cursor:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ine (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nombre VARCHAR(100),
            apellido_paterno VARCHAR(100),
            apellido_materno VARCHAR(100),
            sexo VARCHAR(5),
            fecha_nacimiento VARCHAR(20),
            curp VARCHAR(25) UNIQUE,
            clave_elector VARCHAR(30) UNIQUE,
            domicilio TEXT,
            telefono VARCHAR(20),
            anio_registro INT,
            vigencia VARCHAR(20),
            seccion VARCHAR(20),
            usuario_nombre VARCHAR(100),
            usuario_pin VARCHAR(20)
        )
        """)
    conn.commit()
    conn.close()

crear_tabla()

# =====================================================
def insertar_en_bd(data, usuario_nombre, usuario_pin):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            clave_elector = normalizar_clave(data.get("clave_elector"))
            data["clave_elector"] = clave_elector

            if not clave_elector or len(clave_elector) < 18:
                return "Clave de elector inválida"

            cursor.execute("SELECT id FROM ine WHERE clave_elector=%s", (clave_elector,))
            if cursor.fetchone():
                return "duplicado"

            cursor.execute("""
            INSERT INTO ine (
                nombre, apellido_paterno, apellido_materno, sexo,
                fecha_nacimiento, curp, clave_elector, domicilio,
                telefono, anio_registro, vigencia, seccion,
                usuario_nombre, usuario_pin
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                data.get("nombre"),
                data.get("apellido_paterno"),
                data.get("apellido_materno"),
                data.get("sexo"),
                data.get("fecha_nacimiento"),
                data.get("curp"),
                clave_elector,
                data.get("domicilio"),
                data.get("telefono"),
                data.get("anio_registro"),
                data.get("vigencia"),
                data.get("seccion"),
                usuario_nombre,
                usuario_pin
            ))
        conn.commit()
        return "insertado"
    except Exception as e:
        return f"error: {e}"
    finally:
        conn.close()

# =====================================================
st.set_page_config(page_title="IDAI", layout="centered")
st.title("IDAI")
st.markdown("Extracción inteligente de INE")


# =====================================================
# Autenticación con PIN
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.usuario_nombre = None
    st.session_state.usuario_pin = None

if not st.session_state.autenticado:
    with st.container():
        st.subheader("Ingresa tu PIN")
        with st.form("pin_form"):
            pin_col1, pin_col2 = st.columns([2,1])
            with pin_col1:
                pin = st.text_input("PIN", type="password")
            with pin_col2:
                submit_pin = st.form_submit_button("Validar PIN")
            if submit_pin:
                usuario = validar_pin(pin)
                if usuario:
                    st.session_state.autenticado = True
                    st.session_state.usuario_nombre = usuario["nombre"]
                    st.session_state.usuario_pin = usuario["pin"]
                    st.success(f"✅ PIN correcto. Bienvenido {usuario['nombre']}")
                else:
                    st.error("❌ PIN incorrecto")

# =====================================================
# Formulario principal solo si PIN es correcto
if st.session_state.autenticado:
    with st.expander(f"Registro de INE - Usuario: {st.session_state.usuario_nombre}", expanded=True):
        st.info("Sube la imagen de la INE y completa el número de teléfono (10 dígitos).")
        
        with st.form("form_ine"):
            col1, col2 = st.columns(2)
            with col1:
                uploaded_file = st.file_uploader("Sube o captura imagen INE", type=["jpg","jpeg","png"])
            with col2:
                telefono_input = st.text_input("Teléfono", max_chars=10)
            
            submit_ine = st.form_submit_button("Procesar y guardar registro")
            
            if submit_ine:
                if not uploaded_file:
                    st.error("❌ Debes subir la imagen de la INE")
                elif not (telefono_input.isdigit() and len(telefono_input)==10):
                    st.error("❌ El número de teléfono debe tener 10 dígitos")
                else:
                    with st.spinner("Procesando imagen y guardando datos..."):
                        image_bytes = uploaded_file.read()
                        base64_image = base64.b64encode(image_bytes).decode("utf-8")

                        # Llamada a OpenAI
                        response = client.responses.create(
                            model="gpt-4.1",
                            input=[{
                                "role": "user",
                                "content": [
                                    {"type": "input_text", "text": """
Extrae la información de la credencial INE y devuelve únicamente un JSON
con esta estructura exacta:

{
  "nombre": "",
  "apellido_paterno": "",
  "apellido_materno": "",
  "sexo": "",
  "fecha_nacimiento": "",
  "curp": "",
  "clave_elector": "",
  "domicilio": "",
  "anio_registro": "",
  "vigencia": "",
  "seccion": ""
}
No agregues explicación. Solo JSON válido.
"""},
                                    {"type": "input_image", "image_url": f"data:image/jpeg;base64,{base64_image}"}
                                ]
                            }]
                        )

                        try:
                            json_limpio = extraer_json(response.output_text)
                            data = json.loads(json_limpio)
                            data["anio_registro"] = limpiar_anio(data.get("anio_registro"))
                            data["telefono"] = telefono_input

                            st.subheader("Datos extraídos")
                            st.dataframe(pd.DataFrame([data]), use_container_width=True)

                            resultado = insertar_en_bd(
                                data,
                                st.session_state.usuario_nombre,
                                st.session_state.usuario_pin
                            )

                            if resultado == "insertado":
                                st.success("✅ Registro guardado correctamente")
                            elif resultado == "duplicado":
                                st.warning("⚠ Registro duplicado (clave de elector ya existe)")
                            elif resultado == "Clave de elector inválida":
                                st.error("❌ Clave de elector inválida, revisa la imagen")
                            else:
                                st.error(f"❌ Error SQL: {resultado}")
                        except Exception as e:
                            st.error("❌ Respuesta no es JSON válido")
                            st.write(e)
