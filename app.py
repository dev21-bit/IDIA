import streamlit as st
import pymysql
import base64
import json
import os
import uuid
import qrcode
import re
from io import BytesIO
from openai import OpenAI
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
# =============================
# CONFIG
# =============================

st.set_page_config(page_title="IDAI", page_icon="🆔")
st.markdown("""
<style>

[data-testid="stFileUploaderDropzone"] > div {
    text-align: center;
}

[data-testid="stFileUploaderDropzone"] span {
    visibility: hidden;
}

[data-testid="stFileUploaderDropzone"]::before {
    content: "Haz clic para tomar o seleccionar la imagen de la INE";
    display: block;
    font-size: 16px;
    font-weight: 600;
    color: #444;
    margin-bottom: 5px;
}


</style>
""", unsafe_allow_html=True)

client = OpenAI(api_key=st.secrets["openai"]["api_key"])

BASE_DOWNLOAD_URL = "https://idai-ia.streamlit.app/?pdf="

# =============================
# SESIÓN
# =============================

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.usuario_nombre = None
    st.session_state.usuario_pin = None

# =============================
# CARPETAS
# =============================

os.makedirs("pdfs", exist_ok=True)
os.makedirs("qr", exist_ok=True)

# =============================
# DB
# =============================

def get_connection():
    return pymysql.connect(
        host=st.secrets["db"]["DB_HOST"],
        user=st.secrets["db"]["DB_USER"],
        password=st.secrets["db"]["DB_PASSWORD"],
        database=st.secrets["db"]["DB_NAME"],
        port=st.secrets["db"]["DB_PORT"],
        cursorclass=pymysql.cursors.DictCursor
    )

# =============================
# TABLAS
# =============================

def crear_tablas():

    conn = get_connection()

    with conn.cursor() as cursor:

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ine (
            id INT NOT NULL AUTO_INCREMENT,
            nombre VARCHAR(100),
            apellido_paterno VARCHAR(100),
            apellido_materno VARCHAR(100),
            sexo VARCHAR(10),
            fecha_nacimiento VARCHAR(20),
            curp VARCHAR(25),
            clave_elector VARCHAR(30) UNIQUE,
            domicilio TEXT,
            telefono VARCHAR(20),
            anio_registro INT,
            vigencia VARCHAR(20),
            seccion VARCHAR(20),
            usuario_nombre VARCHAR(100),
            usuario_pin VARCHAR(20),
            pdf LONGBLOB,
            PRIMARY KEY (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

    conn.commit()
    conn.close()

# =============================
# LOGIN PIN
# =============================

def validar_pin(pin):

    conn = get_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute(
                "SELECT nombre, pin FROM usuarios WHERE pin=%s",
                (pin.strip(),)
            )

            return cursor.fetchone()

    finally:

        conn.close()

# =============================
# LIMPIEZA
# =============================

def limpiar_anio(valor):

    if not valor:
        return None

    m = re.search(r"\d{4}", str(valor))

    if m:
        return int(m.group())

    return None


def extraer_json(texto):

    texto = re.sub(r"```json", "", texto)
    texto = re.sub(r"```", "", texto)

    match = re.search(r"\{.*\}", texto, re.DOTALL)

    if match:
        return match.group()

    return texto

# =============================
# PDF
# =============================

def generar_pdf(data):

    buffer = BytesIO()

    folio = str(uuid.uuid4())[:8]

    clave = data["clave_elector"]

    url = BASE_DOWNLOAD_URL + clave

    qr = qrcode.make(url)

    qr_buffer = BytesIO()
    qr.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)

    c = canvas.Canvas(buffer, pagesize=letter)

    width, height = letter

    # =============================
    # TITULO SEGUN TIPO
    # =============================

    c.setFont("Helvetica-Bold", 18)

    if data.get("tipo_registro") == "Afiliado al partido":
        titulo = "FORMATO DE AFILIACIÓN AL PARTIDO"
    else:
        titulo = "FORMATO DE REGISTRO DE APOYO"

    c.drawCentredString(width/2, 750, titulo)

    c.setFont("Helvetica", 10)

    # =============================
    # FOLIO
    # =============================

    c.drawString(50,720,"Folio")
    c.rect(90,710,120,20)
    c.drawString(95,715,folio)

    # =============================
    # NOMBRE
    # =============================

    y=680

    c.drawString(50,y+20,"Apellido Paterno")
    c.rect(50,y,170,20)

    c.drawString(230,y+20,"Apellido Materno")
    c.rect(230,y,170,20)

    c.drawString(410,y+20,"Nombre(s)")
    c.rect(410,y,150,20)

    c.drawString(55,y+5,data.get("apellido_paterno",""))
    c.drawString(235,y+5,data.get("apellido_materno",""))
    c.drawString(415,y+5,data.get("nombre",""))

    # =============================
    # DOMICILIO
    # =============================

    y=640

    c.drawString(50,y+20,"Domicilio")
    c.rect(50,y,510,20)

    c.drawString(55,y+5,data.get("domicilio",""))

    # =============================
    # CURP
    # =============================

    y=600

    c.drawString(50,y+20,"CURP")
    c.rect(50,y,250,20)

    c.drawString(55,y+5,data.get("curp",""))

    c.drawString(320,y+20,"Clave de Elector")

    clave_txt=data.get("clave_elector","")

    x=320

    for i in range(18):

        c.rect(x+(i*12),y,10,15)

        if i<len(clave_txt):
            c.drawString(x+(i*12)+2,y+3,clave_txt[i])

    # =============================
    # DATOS PERSONALES
    # =============================

    y=550

    c.drawString(50,y+20,"Fecha Nacimiento")
    c.rect(50,y,130,20)
    c.drawString(55,y+5,data.get("fecha_nacimiento",""))

    c.drawString(200,y+20,"Sexo")
    c.rect(200,y,70,20)
    c.drawString(205,y+5,data.get("sexo",""))

    c.drawString(290,y+20,"Sección")
    c.rect(290,y,70,20)
    c.drawString(295,y+5,data.get("seccion",""))

    c.drawString(380,y+20,"Teléfono")
    c.rect(380,y,180,20)
    c.drawString(385,y+5,data.get("telefono",""))

    # =============================
    # REGISTRO
    # =============================

    y=500

    c.drawString(50,y+20,"Año Registro")
    c.rect(50,y,100,20)
    c.drawString(55,y+5,str(data.get("anio_registro","")))

    c.drawString(170,y+20,"Vigencia")
    c.rect(170,y,120,20)
    c.drawString(175,y+5,data.get("vigencia",""))

    # =============================
    # TEXTO LEGAL
    # =============================

    y=450

    c.setFont("Helvetica",9)

    if data.get("tipo_registro") == "Afiliado al partido":

        c.drawString(50,y,"Por mi libre voluntad solicito mi afiliación al partido en virtud de estar de acuerdo con sus documentos básicos.")
        c.drawString(50,y-15,"Me comprometo a cumplir sus estatutos y trabajar activamente con sus miembros.")
        c.drawString(50,y-35,"Declaro bajo protesta de decir verdad que no me encuentro afiliado a otro partido político.")

    else:

        c.drawString(50,y,"Por medio del presente manifiesto mi apoyo ciudadano al partido.")
        c.drawString(50,y-15,"Este apoyo no implica afiliación formal ni militancia política.")
        c.drawString(50,y-35,"Autorizo el uso de mis datos únicamente para fines de registro y contacto.")

    # =============================
    # FIRMAS
    # =============================

    y=340

    c.line(80,y,260,y)
    c.drawCentredString(170,y-15,"Firma del Ciudadano")

    c.line(340,y,520,y)
    c.drawCentredString(430,y-15,"Firma del Responsable")

    # =============================
    # QR
    # =============================

    qr_x=470
    qr_y=240


    c.drawImage(ImageReader(qr_buffer),qr_x,qr_y,80,80)

    c.setFont("Helvetica",7)
    c.drawCentredString(qr_x+40,qr_y-10,"Escanear para descargar")

    # =============================
    # FOOTER
    # =============================

    c.setFont("Helvetica-Oblique",8)
    c.drawCentredString(width/2,300,"Sistema IDAI - Registro Inteligente")

    c.save()

    buffer.seek(0)

    return buffer.read()

# =============================
# INSERTAR
# =============================

def insertar(data):
    """Inserta los datos en la base de datos y guarda el PDF en la BD"""
    conn = None
    try:
        conn = get_connection()
        
        with conn.cursor() as cursor:
            # Verificar si ya existe la clave de elector
            cursor.execute(
                "SELECT id FROM ine WHERE clave_elector = %s",
                (data["clave_elector"],)
            )
            existe = cursor.fetchone()
            
            if existe:
                return "duplicado"
            
            # Generar PDF
            pdf_bytes = generar_pdf(data)
            
            # Insertar en base de datos incluyendo el PDF
            cursor.execute("""
            INSERT INTO ine(
                nombre,
                apellido_paterno,
                apellido_materno,
                sexo,
                fecha_nacimiento,
                curp,
                clave_elector,
                domicilio,
                telefono,
                anio_registro,
                vigencia,
                seccion,
                usuario_nombre,
                usuario_pin,
                pdf
            )
            VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                data["nombre"],
                data["apellido_paterno"],
                data["apellido_materno"],
                data["sexo"],
                data["fecha_nacimiento"],
                data["curp"],
                data["clave_elector"],
                data["domicilio"],
                data["telefono"],
                data["anio_registro"],
                data["vigencia"],
                data["seccion"],
                st.session_state.usuario_nombre,
                st.session_state.usuario_pin,
                pdf_bytes
            ))
            
            conn.commit()
            
            # También guardamos una copia en archivo para descarga rápida
            pdf_path = f"pdfs/{data['clave_elector']}.pdf"
            with open(pdf_path, "wb") as pdf_file:
                pdf_file.write(pdf_bytes)
                
            return "ok"
            
    except pymysql.IntegrityError as e:
        if conn:
            conn.rollback()
        if "duplicate" in str(e).lower():
            return "duplicado"
        return "error"
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Error en insertar: {str(e)}")
        return "error"
        
    finally:
        if conn:
            conn.close()
# =============================
# DESCARGA QR (versión con BD)
# =============================

params = st.query_params

if "pdf" in params:
    clave = params["pdf"]
    
    conn = get_connection()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT pdf FROM ine WHERE clave_elector = %s",
            (clave,)
        )
        resultado = cursor.fetchone()
        
        if resultado and resultado['pdf']:
            st.download_button(
                "Descargar documento",
                resultado['pdf'],
                file_name=f"{clave}.pdf",
                mime="application/pdf"
            )
    conn.close()
    st.stop()

# =============================
# LOGIN UI
# =============================

if not st.session_state.autenticado:

    st.title("🆔 IDAI")

    pin=st.text_input("Clave de acceso",type="password")

    if st.button("Ingresar"):

        usuario=validar_pin(pin)

        if usuario:

            st.session_state.autenticado=True
            st.session_state.usuario_nombre=usuario["nombre"]
            st.session_state.usuario_pin=usuario["pin"]

            st.success(f"Bienvenido {usuario['nombre']}")

            st.rerun()

        else:

            st.error("PIN incorrecto")

    st.stop()

# =============================
# PANEL
# =============================

st.title("🆔 IDAI")

st.write(f"Usuario activo: {st.session_state.usuario_nombre}")

if st.button("Cerrar sesión"):

    st.session_state.autenticado=False
    st.rerun()

img = st.file_uploader(
    "📷 Subir imagen de credencial INE",
    type=["jpg","jpeg","png"],
    label_visibility="visible"
)

telefono=st.text_input("Teléfono")
tipo_registro = st.radio(
    "Tipo de registro",
    ["Afiliado al partido", "Solo apoyo"]
)

# =============================
# AVISO DE PRIVACIDAD
# =============================
with st.expander("📋 Aviso de Privacidad"):
    st.markdown("""
    **AVISO DE PRIVACIDAD**
    
    De conformidad con lo establecido en la Ley Federal de Protección de Datos Personales en Posesión de los Particulares, IDAI pone a su disposición el siguiente aviso de privacidad.
    
    IDAI es responsable del uso y protección de sus datos personales, en este sentido y atendiendo las obligaciones legales establecidas en la Ley Federal de Protección de Datos Personales en Posesión de los Particulares, a través de este instrumento se informa a los titulares de los datos, la información que de ellos se recaba y los fines que se le darán a dicha información.
    
    Los datos personales que recabamos de usted serán utilizados para las siguientes finalidades: registro en el sistema, generación de documentos oficiales, verificación de identidad y contacto.
    
    **Consentimiento**
    Al marcar la casilla de aceptación, usted otorga su consentimiento para el tratamiento de sus datos personales conforme a este aviso de privacidad.
    """)

acepto_privacidad = st.checkbox("He leído y acepto el Aviso de Privacidad", value=False)

# =============================
# BOTÓN DE PROCESAR
# =============================
if st.button("Procesar"):

    # Validaciones
    if not img:
        st.error("❌ Error: Por favor sube una imagen de la INE")
    
    elif not acepto_privacidad:
        st.error("❌ Error: Debes aceptar el Aviso de Privacidad para continuar con el registro")
    
    else:
        with st.spinner("Procesando imagen y generando registro..."):
            try:
                bytes_img=img.read()

                base64_img=base64.b64encode(bytes_img).decode()

                response=client.responses.create(
                model="gpt-4.1",
                input=[{
                "role":"user",
                "content":[
                {"type":"input_text","text":"""
Extrae datos INE y devuelve JSON:

{
"nombre":"",
"apellido_paterno":"",
"apellido_materno":"",
"sexo":"",
"fecha_nacimiento":"",
"curp":"",
"clave_elector":"",
"domicilio":"",
"anio_registro":"",
"vigencia":"",
"seccion":""
}
"""},

                {"type":"input_image",
                "image_url":f"data:image/jpeg;base64,{base64_img}"}
                ]
                }]
                )

                limpio=extraer_json(response.output_text)

                data=json.loads(limpio)

                data["telefono"]=telefono
                data["tipo_registro"] = tipo_registro

                data["anio_registro"]=limpiar_anio(data.get("anio_registro"))

                resultado=insertar(data)

                if resultado=="ok":
                    st.success("✅ ¡Registro exitoso! Los datos han sido guardados correctamente en el sistema")
                    
                    pdf=f"pdfs/{data['clave_elector']}.pdf"

                    with open(pdf,"rb") as f:
                        col1, col2 = st.columns([1, 3])
                        with col1:
                            st.download_button(
                            "📥 Descargar PDF",
                            f,
                            file_name=f"{data['clave_elector']}.pdf"
                            )
                        with col2:
                            st.info(f"Folio: {data['clave_elector'][:8]} - Se ha generado el documento correctamente")

                elif resultado == "duplicado":
                    st.error("❌ Error: Ya existe un registro con esta clave de elector. No se puede duplicar el registro")
                    st.info("Si necesitas actualizar un registro existente, contacta al administrador del sistema")
                else:
                    st.error("❌ Error: No se pudo completar el registro. Por favor intenta nuevamente")
                    
            except Exception as e:
                st.error(f"❌ Error inesperado: {str(e)}")
                st.info("Por favor verifica la imagen e intenta nuevamente")