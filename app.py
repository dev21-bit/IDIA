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
# ESTILOS PERSONALIZADOS PARA TRADUCIR ELEMENTOS
# =====================================================
st.markdown("""
<style>
    /* Traducir el texto del uploader */
    .stFileUploader > div > div > div > small {
        visibility: hidden;
        position: relative;
    }
    .stFileUploader > div > div > div > small::after {
        content: "Arrastra y suelta tu archivo aquí";
        visibility: visible;
        position: absolute;
        left: 0;
        top: 0;
        color: #666;
    }
    
    /* Traducir el texto del botón de archivos */
    .stFileUploader > div > button > div {
        visibility: hidden;
        position: relative;
    }
    .stFileUploader > div > button > div::after {
        content: "Explorar archivos";
        visibility: visible;
        position: absolute;
        left: 0;
        top: 0;
        width: 100%;
        color: #650021;
        font-weight: 500;
    }
    
    /* Traducir el texto de límite de archivos */
    .stFileUploader > div > div:last-child {
        visibility: hidden;
        position: relative;
    }
    .stFileUploader > div > div:last-child::after {
        content: "Archivos permitidos: JPG, JPEG, PNG";
        visibility: visible;
        position: absolute;
        left: 0;
        top: 0;
        color: #888;
        font-size: 0.8em;
    }
    
    /* Personalizar botones */
    .stButton button {
        background-color: #650021;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 10px 20px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    
    .stButton button:hover {
        background-color: #8B0000;
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    
    /* Personalizar inputs */
    .stTextInput input {
        border: 2px solid #650021;
        border-radius: 8px;
        padding: 8px 12px;
    }
    
    /* Personalizar títulos */
    h1 {
        color: #650021;
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }
    
    /* Personalizar spinner */
    .stSpinner > div {
        color: #650021 !important;
    }
    
    /* Traducir texto del spinner */
    .stSpinner > div > div {
        visibility: hidden;
        position: relative;
    }
    .stSpinner > div > div::after {
        content: "Procesando imagen...";
        visibility: visible;
        position: absolute;
        left: 0;
        top: 0;
        color: #650021;
        font-weight: 500;
    }
    
    /* Personalizar mensajes de éxito/error */
    .stAlert {
        border-radius: 8px;
        border-left: 5px solid;
    }
    
    /* Traducir placeholder de input */
    input::placeholder {
        color: #aaa;
        font-style: italic;
    }
</style>
""", unsafe_allow_html=True)

# =====================================================
# FUNCIONES DE UTILIDAD PARA TRADUCCIÓN
# =====================================================
def spanish_uploader_text():
    """Inyecta JavaScript para traducir el uploader"""
    components.html(
        """
        <script>
        // Función para traducir elementos de Streamlit
        function translateStreamlitElements() {
            // Traducir texto del uploader
            const uploaderTexts = document.querySelectorAll('.stFileUploader small');
            uploaderTexts.forEach(el => {
                if (el.innerText.includes('Drag and drop')) {
                    el.innerText = 'Arrastra y suelta tu archivo aquí';
                }
            });
            
            // Traducir botón del uploader
            const uploaderButtons = document.querySelectorAll('.stFileUploader button div');
            uploaderButtons.forEach(el => {
                if (el.innerText.includes('Browse files')) {
                    el.innerText = 'Explorar archivos';
                }
            });
            
            // Traducir límite de archivos
            const fileLimits = document.querySelectorAll('.stFileUploader > div > div:last-child');
            fileLimits.forEach(el => {
                if (el.innerText.includes('Limit')) {
                    el.innerText = 'Archivos permitidos: JPG, JPEG, PNG';
                }
            });
            
            // Traducir spinner
            const spinners = document.querySelectorAll('.stSpinner > div > div');
            spinners.forEach(el => {
                if (el.innerText.includes('Processing')) {
                    el.innerText = 'Procesando imagen...';
                }
            });
        }
        
        // Ejecutar cuando el DOM esté listo
        document.addEventListener('DOMContentLoaded', translateStreamlitElements);
        
        // También ejecutar después de actualizaciones de Streamlit
        const observer = new MutationObserver(translateStreamlitElements);
        observer.observe(document.body, { childList: true, subtree: true });
        </script>
        """,
        height=0,
        width=0
    )

# Llamar a la función de traducción
spanish_uploader_text()

client = OpenAI(api_key=st.secrets["openai"]["api_key"])

# =====================================================
def get_connection():
    return pymysql.connect(
        host=st.secrets["db"]["DB_HOST"],
        user=st.secrets["db"]["DB_USER"],
        password=st.secrets["db"]["DB_PASSWORD"],
        database=st.secrets["db"]["DB_NAME"],
        port=st.secrets["db"]["DB_PORT"],
        cursorclass=pymysql.cursors.DictCursor
    )

# =====================================================
def validar_pin(pin):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT nombre, pin FROM usuarios WHERE pin=%s", (pin,))
            return cursor.fetchone()
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
# TÍTULO PRINCIPAL
# =====================================================
st.title("🆔 IDAI")
st.markdown("### Sistema de Extracción Inteligente de INE")
st.markdown("---")

# =====================================================
# Autenticación con PIN
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.usuario_nombre = None
    st.session_state.usuario_pin = None

if not st.session_state.autenticado:
    with st.container():
        st.subheader("🔐 Iniciar Sesión")
        with st.form("pin_form"):
            pin_col1, pin_col2 = st.columns([2,1])
            with pin_col1:
                pin = st.text_input("Ingresa tu clave de acceso", type="password", placeholder="Ej: 1234")
            with pin_col2:
                submit_pin = st.form_submit_button("🔑 Validar", use_container_width=True)
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

# =====================================================
# Formulario principal solo si PIN es correcto
if st.session_state.autenticado:
    # Barra de usuario
    col_user1, col_user2, col_user3 = st.columns([3,1,1])
    with col_user1:
        st.markdown(f"**👤 Usuario:** {st.session_state.usuario_nombre}")
    with col_user3:
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state.autenticado = False
            st.session_state.usuario_nombre = None
            st.session_state.usuario_pin = None
            st.rerun()
    
    st.markdown("---")
    
    with st.expander("📝 Registro de Nueva Credencial INE", expanded=True):
        st.info("📌 **Instrucciones:** Sube una imagen de la credencial INE (frente) y completa el número de teléfono a 10 dígitos.")
        
        with st.form("form_ine"):
            col1, col2 = st.columns(2)
            with col1:
                uploaded_file = st.file_uploader(
                    "📸 Selecciona o captura la imagen de la INE",
                    type=["jpg", "jpeg", "png"],
                    help="Formatos aceptados: JPG, JPEG, PNG"
                )
            with col2:
                telefono_input = st.text_input(
                    "📱 Teléfono (10 dígitos)",
                    max_chars=10,
                    placeholder="Ej: 4921234567",
                    help="Ingresa el número de teléfono a 10 dígitos"
                )
            
            submit_ine = st.form_submit_button("🚀 Procesar y Guardar Registro", use_container_width=True)
            
            if submit_ine:
                if not uploaded_file:
                    st.error("❌ Error: Debes subir la imagen de la INE")
                elif not (telefono_input.isdigit() and len(telefono_input) == 10):
                    st.error("❌ Error: El número de teléfono debe tener 10 dígitos numéricos")
                else:
                    with st.spinner("⏳ Procesando imagen con IA..."):
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

                            st.subheader("📋 Datos Extraídos")
                            st.dataframe(
                                pd.DataFrame([data]),
                                use_container_width=True,
                                column_config={
                                    "nombre": "Nombre",
                                    "apellido_paterno": "Apellido Paterno",
                                    "apellido_materno": "Apellido Materno",
                                    "sexo": "Sexo",
                                    "fecha_nacimiento": "Fecha Nacimiento",
                                    "curp": "CURP",
                                    "clave_elector": "Clave Elector",
                                    "domicilio": "Domicilio",
                                    "anio_registro": "Año Registro",
                                    "vigencia": "Vigencia",
                                    "seccion": "Sección",
                                    "telefono": "Teléfono"
                                }
                            )

                            resultado = insertar_en_bd(
                                data,
                                st.session_state.usuario_nombre,
                                st.session_state.usuario_pin
                            )

                            if resultado == "insertado":
                                st.success("✅ ¡Registro guardado exitosamente!")
                                st.balloons()
                            elif resultado == "duplicado":
                                st.warning("⚠️ Registro duplicado - La clave de elector ya existe en la base de datos")
                            elif resultado == "Clave de elector inválida":
                                st.error("❌ Clave de elector inválida - Por favor verifica la imagen")
                            else:
                                st.error(f"❌ Error en base de datos: {resultado}")
                        except Exception as e:
                            st.error("❌ Error al procesar la respuesta - La imagen no contiene información válida")
                            st.write("Detalle técnico:", e)
    
    # Pie de página
    st.markdown("---")
    col_footer1, col_footer2, col_footer3 = st.columns(3)
    with col_footer1:
        st.caption("© 2024 IDAI - Sistema de Registro")
    with col_footer2:
        st.caption(f"Usuario activo: {st.session_state.usuario_nombre}")
    with col_footer3:
        st.caption("Versión 2.0")