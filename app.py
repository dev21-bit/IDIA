import streamlit as st
import base64
import json
import pandas as pd
import pymysql
import re
from openai import OpenAI
import streamlit.components.v1 as components

# =====================================================
# CONFIGURACIÓN INICIAL
# =====================================================
st.set_page_config(
    page_title="IDAI - Sistema de Registro INE",
    page_icon="🆔",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# =====================================================
# INICIALIZAR ESTADO DE SESIÓN PARA LOS CAMPOS
# =====================================================
if "form_submitted" not in st.session_state:
    st.session_state.form_submitted = False
if "uploaded_file_key" not in st.session_state:
    st.session_state.uploaded_file_key = 0
if "telefono_value" not in st.session_state:
    st.session_state.telefono_value = ""
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.usuario_nombre = None
    st.session_state.usuario_pin = None

# =====================================================
# FUNCIÓN PARA RESETEAR EL FORMULARIO
# =====================================================
def reset_form():
    st.session_state.uploaded_file_key += 1
    st.session_state.telefono_value = ""
    st.session_state.form_submitted = False

# =====================================================
# ESTILOS PERSONALIZADOS
# =====================================================
st.markdown("""
<style>
/* Traducir uploader */
.stFileUploader > div > div > div > small {visibility:hidden;position:relative;}
.stFileUploader > div > div > div > small::after {content:"Arrastra y suelta tu archivo aquí";visibility:visible;position:absolute;left:0;top:0;color:#666;}
.stFileUploader > div > button > div {visibility:hidden;position:relative;}
.stFileUploader > div > button > div::after {content:"Explorar archivos";visibility:visible;position:absolute;left:0;top:0;width:100%;color:#650021;font-weight:500;}
.stFileUploader > div > div:last-child {visibility:hidden;position:relative;}
.stFileUploader > div > div:last-child::after {content:"Archivos permitidos: JPG, JPEG, PNG";visibility:visible;position:absolute;left:0;top:0;color:#888;font-size:0.8em;}

/* Botones */
.stButton button {background-color:#650021;color:white;border:none;border-radius:8px;padding:10px 20px;font-weight:600;transition:all 0.3s ease;}
.stButton button:hover {background-color:#8B0000;transform:translateY(-2px);box-shadow:0 4px 8px rgba(0,0,0,0.2);}

/* Inputs */
.stTextInput input {border:2px solid #650021;border-radius:8px;padding:8px 12px;}

/* Títulos */
h1 {color:#650021;font-size:2.5rem;font-weight:700;margin-bottom:0.5rem;}

/* Mensaje de éxito */
div[data-testid="stSuccess"] {border-left:5px solid #28a745;background-color:#d4edda;color:#155724;font-size:1.1rem;padding:1rem;border-radius:8px;box-shadow:0 4px 6px rgba(0,0,0,0.1);margin-bottom:20px;}
</style>
""", unsafe_allow_html=True)

# =====================================================
# FUNCIONES DE UTILIDAD
# =====================================================
def spanish_uploader_text():
    components.html("""
    <script>
    function translateStreamlitElements() {
        const uploaderTexts = document.querySelectorAll('.stFileUploader small');
        uploaderTexts.forEach(el => { if(el.innerText.includes('Drag and drop')) el.innerText='Arrastra y suelta tu archivo aquí'; });
        const uploaderButtons = document.querySelectorAll('.stFileUploader button div');
        uploaderButtons.forEach(el => { if(el.innerText.includes('Browse files')) el.innerText='Explorar archivos'; });
        const fileLimits = document.querySelectorAll('.stFileUploader > div > div:last-child');
        fileLimits.forEach(el => { if(el.innerText.includes('Limit')) el.innerText='Archivos permitidos: JPG, JPEG, PNG'; });
    }
    document.addEventListener('DOMContentLoaded', translateStreamlitElements);
    const observer = new MutationObserver(translateStreamlitElements);
    observer.observe(document.body, { childList: true, subtree: true });
    </script>""", height=0, width=0)

spanish_uploader_text()

client = OpenAI(api_key=st.secrets["openai"]["api_key"])

def get_connection():
    return pymysql.connect(
        host=st.secrets["db"]["DB_HOST"],
        user=st.secrets["db"]["DB_USER"],
        password=st.secrets["db"]["DB_PASSWORD"],
        database=st.secrets["db"]["DB_NAME"],
        port=st.secrets["db"]["DB_PORT"],
        cursorclass=pymysql.cursors.DictCursor
    )

def validar_pin(pin):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT nombre, pin FROM usuarios WHERE pin=%s", (pin,))
            return cursor.fetchone()
    finally:
        conn.close()

def limpiar_anio(valor):
    if not valor: return None
    match = re.search(r"\d{4}", str(valor))
    if match: return int(match.group())
    return None

def normalizar_clave(valor):
    if not valor: return None
    valor = str(valor).upper()
    valor = re.sub(r"\s+", "", valor)
    valor = re.sub(r"[^A-Z0-9]", "", valor)
    return valor

def extraer_json(texto):
    texto = re.sub(r"```json", "", texto)
    texto = re.sub(r"```", "", texto)
    match = re.search(r"\{.*\}", texto, re.DOTALL)
    if match: return match.group()
    return texto.strip()

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
        )""")
    conn.commit()
    conn.close()

crear_tabla()

def insertar_en_bd(data, usuario_nombre, usuario_pin):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            clave_elector = normalizar_clave(data.get("clave_elector"))
            data["clave_elector"] = clave_elector
            if not clave_elector or len(clave_elector)<18:
                return "Clave de elector inválida"
            cursor.execute("SELECT id FROM ine WHERE clave_elector=%s", (clave_elector,))
            if cursor.fetchone(): return "duplicado"
            cursor.execute("""
            INSERT INTO ine (nombre, apellido_paterno, apellido_materno, sexo,
            fecha_nacimiento, curp, clave_elector, domicilio, telefono, anio_registro,
            vigencia, seccion, usuario_nombre, usuario_pin)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
# INTERFAZ PRINCIPAL
# =====================================================
st.title("🆔 IDAI")
st.markdown("### Sistema de Extracción Inteligente de INE")
st.markdown("---")

# Autenticación
if not st.session_state.autenticado:
    with st.container():
        st.subheader("Iniciar Sesión")
        with st.form("pin_form"):
            pin_col1, pin_col2 = st.columns([2,1])
            with pin_col1:
                pin = st.text_input("Ingresa tu clave de acceso", type="password", placeholder="Ej: IDAI1234")
            with pin_col2:
                submit_pin = st.form_submit_button("Validar", use_container_width=True)
            if submit_pin:
                usuario = validar_pin(pin)
                if usuario:
                    st.session_state.autenticado = True
                    st.session_state.usuario_nombre = usuario["nombre"]
                    st.session_state.usuario_pin = usuario["pin"]
                    st.success(f"✅ ¡Bienvenido {usuario['nombre']}!")
                    st.rerun()
                else:
                    st.error("❌ Clave incorrecta. Intenta de nuevo.")

# Formulario principal
if st.session_state.autenticado:
    col_user1, col_user2, col_user3 = st.columns([3,1,1])
    with col_user1:
        st.markdown(f"**👤 Usuario:** {st.session_state.usuario_nombre}")
    with col_user3:
        if st.button("Cerrar Sesión", use_container_width=True):
            st.session_state.autenticado = False
            st.session_state.usuario_nombre = None
            st.session_state.usuario_pin = None
            reset_form()
            st.rerun()
    
    st.markdown("---")
    
    with st.expander("📝 Registro de Nueva Credencial INE", expanded=True):
        st.info("📌 **Instrucciones:** Sube una imagen de la credencial INE (frente) y completa el número de teléfono a 10 dígitos.")
        uploader_key = f"file_uploader_{st.session_state.uploaded_file_key}"
        
        with st.form("form_ine"):
            col1, col2 = st.columns(2)
            with col1:
                uploaded_file = st.file_uploader(
                    "📸 Selecciona o captura la imagen de la INE",
                    type=["jpg","jpeg","png"],
                    key=uploader_key
                )
            with col2:
                telefono_input = st.text_input(
                    "📱 Teléfono (10 dígitos)",
                    max_chars=10,
                    value=st.session_state.telefono_value,
                    placeholder="Ej: 4921234567"
                )
            
            submit_disabled = False
            submit_ine = st.form_submit_button("Procesar y Guardar Registro", use_container_width=True, disabled=submit_disabled)
            limpiar_btn = st.form_submit_button("Limpiar Formulario", use_container_width=True)
            
            if limpiar_btn:
                reset_form()
                st.experimental_rerun()
            
            if submit_ine:
                if not uploaded_file:
                    st.error("❌ Error: Debes subir la imagen de la INE")
                elif not (telefono_input.isdigit() and len(telefono_input)==10):
                    st.error("❌ Error: El número de teléfono debe tener 10 dígitos numéricos")
                else:
                    with st.spinner("⏳ Procesando imagen con IA..."):
                        image_bytes = uploaded_file.read()
                        base64_image = base64.b64encode(image_bytes).decode("utf-8")

                        response = client.responses.create(
                            model="gpt-4.1",
                            input=[{
                                "role":"user",
                                "content":[
                                    {"type":"input_text","text":"""
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
"""},{"type":"input_image","image_url":f"data:image/jpeg;base64,{base64_image}"}]
                            }]
                        )

                        try:
                            json_limpio = extraer_json(response.output_text)
                            data = json.loads(json_limpio)
                            data["anio_registro"] = limpiar_anio(data.get("anio_registro"))
                            data["telefono"] = telefono_input

                            resultado = insertar_en_bd(data, st.session_state.usuario_nombre, st.session_state.usuario_pin)

                            if resultado=="insertado":
                                st.session_state.telefono_value = telefono_input
                                st.success("✅ ¡Registro guardado exitosamente!")
                                reset_form()

                            elif resultado=="duplicado":
                                st.warning("⚠️ Registro duplicado - La clave de elector ya existe en la base de datos")
                            elif resultado=="Clave de elector inválida":
                                st.error("❌ Clave de elector inválida - Por favor verifica la imagen")
                            else:
                                st.error(f"❌ Error en base de datos: {resultado}")

                        except Exception as e:
                            st.error("❌ Error al procesar la respuesta - La imagen no contiene información válida")
                            with st.expander("Ver detalle técnico"):
                                st.write(e)

# Pie de página
st.markdown("---")
col_footer1, col_footer2, col_footer3 = st.columns(3)
with col_footer1:
    st.caption("2026 IDAI - Sistema de Extracción Inteligente de INE")
with col_footer2:
    st.caption(f"Usuario activo: {st.session_state.usuario_nombre}")
with col_footer3:
    st.caption("Versión 2.0")