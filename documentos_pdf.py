# documentos_pdf.py
import os
import sqlite3
from datetime import datetime, date, timedelta

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.utils import ImageReader

from .db import DB_PATH, obtener_paciente, obtener_cita_con_paciente, upsert_documento_generado

try:
    from .paths import get_documentos_dir
except Exception:
    get_documentos_dir = None


# -----------------------------
# Paths / imágenes
# -----------------------------
def _get_paths_documentos():
    data_dir = os.path.dirname(DB_PATH)
    img_dir = os.path.join(data_dir, "imagenes")

    if get_documentos_dir:
        documentos_dir = get_documentos_dir()
    else:
        documentos_dir = os.path.join(data_dir, "documentos_pdf")
        os.makedirs(documentos_dir, exist_ok=True)

    logo_path = os.path.join(img_dir, "logo.png")
    firma_alt_path = os.path.join(img_dir, "firma_alt.png")  # NUEVA
    firma_path = os.path.join(img_dir, "firma.png")          # fallback

    return documentos_dir, logo_path, firma_alt_path, firma_path


def _choose_firma_path(firma_alt_path: str, firma_path: str) -> str:
    if os.path.exists(firma_alt_path):
        return firma_alt_path
    return firma_path


def _image_scaled(path: str, max_width_mm: float, max_height_mm: float):
    if not path or not os.path.exists(path):
        return None
    max_w = max_width_mm * mm
    max_h = max_height_mm * mm
    img_reader = ImageReader(path)
    iw, ih = img_reader.getSize()
    ratio = min(max_w / iw, max_h / ih, 1.0)
    return Image(path, width=iw * ratio, height=ih * ratio)


def _open_if_windows(path: str):
    if os.name == "nt" and os.path.exists(path):
        try:
            os.startfile(path)
        except Exception:
            pass


def _safe_filename(name: str) -> str:
    for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
        name = name.replace(ch, "-")
    return name.strip()


# -----------------------------
# Config dinámica profesional
# -----------------------------
def _get_profesional_config() -> dict:
    """
    Lee configuracion_profesional (si existe) para volver el documento dinámico.
    Campos esperados (según tu comentario):
      - nombre_profesional
    Opcionales (si existen en tu tabla):
      - tarjeta_profesional / tp / numero_tarjeta_profesional
      - ciudad
    """
    cfg = {
        "nombre_profesional": "Sara Milena Hernández Ramírez",
        "tp": "180733",
        "ciudad": "Medellín",
    }

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # 1) nombre profesional
        try:
            cur.execute("SELECT nombre_profesional FROM configuracion_profesional LIMIT 1;")
            row = cur.fetchone()
            if row and row[0]:
                cfg["nombre_profesional"] = str(row[0]).strip()
        except Exception:
            pass

        # 2) TP (intentamos varios nombres comunes)
        for col in ("tarjeta_profesional", "tp", "numero_tarjeta_profesional"):
            try:
                cur.execute(f"SELECT {col} FROM configuracion_profesional LIMIT 1;")
                row = cur.fetchone()
                if row and row[0]:
                    cfg["tp"] = str(row[0]).strip()
                    break
            except Exception:
                continue

        # 3) ciudad (si existe)
        try:
            cur.execute("SELECT ciudad FROM configuracion_profesional LIMIT 1;")
            row = cur.fetchone()
            if row and row[0]:
                cfg["ciudad"] = str(row[0]).strip()
        except Exception:
            pass

        conn.close()
    except Exception:
        # fallback silencioso
        pass

    return cfg


# -----------------------------
# Fecha/hora helpers
# -----------------------------
def _parse_fecha_hora(fecha_hora_raw):
    if not fecha_hora_raw:
        return None
    s = str(fecha_hora_raw).strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt)
        except Exception:
            pass
    try:
        return datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
    except Exception:
        return None


def _format_fecha_larga_es(dt: date) -> str:
    meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]
    return f"{dt.day} de {meses[dt.month - 1]} {dt.year}"


def _format_hora_12h(dt: datetime) -> str:
    # “8:00 am”
    h = dt.strftime("%I:%M").lstrip("0")
    suf = dt.strftime("%p").lower()
    return f"{h} {suf}"


def _identificado_según_sexo(sexo_raw: str) -> str:
    s = (sexo_raw or "").strip().lower()
    if s in ("m", "masculino", "hombre"):
        return "Identificado"
    if s in ("f", "femenino", "mujer"):
        return "Identificada"
    return "Identificada/o"

def _tipo_doc_a_texto(tipo_doc_raw: str) -> str:
    """
    Convierte tipo_documento de BD a texto del certificado.
    CC -> cédula de ciudadanía
    TI -> tarjeta de identidad
    CE -> cédula de extranjería
    PASAPORTE -> pasaporte
    OTRO -> identificación
    """
    t = (tipo_doc_raw or "").strip().upper()
    if t == "CC":
        return "cédula de ciudadanía"
    if t == "TI":
        return "tarjeta de identidad"
    if t == "CE":
        return "cédula de extranjería"
    if t == "PASAPORTE":
        return "pasaporte"
    if t == "OTRO":
        return "identificación"
    # fallback general
    return "identificación"


# -----------------------------
# Estilos
# -----------------------------
ACCENT = colors.HexColor("#f27c4a")


def _styles():
    base = getSampleStyleSheet()
    normal = ParagraphStyle(
        "NormalSara",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=14,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#333333"),
    )
    title = ParagraphStyle(
        "TitleSara",
        parent=normal,
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#333333"),
        spaceAfter=8,
    )
    subtitle = ParagraphStyle(
        "SubTitleSara",
        parent=normal,
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=15,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#111111"),
        spaceBefore=10,
        spaceAfter=6,
    )
    small = ParagraphStyle(
        "SmallSara",
        parent=normal,
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor("#555555"),
    )
    header_contact = ParagraphStyle(
        "HeaderContact",
        parent=small,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#333333"),
    )
    return normal, title, subtitle, small, header_contact


def _header_logo_only(story, logo_path: str):
    logo_img = _image_scaled(logo_path, 70, 25)
    if logo_img:
        t = Table([[logo_img]], colWidths=[170 * mm])
        t.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        story.append(t)
        story.append(Spacer(1, 10))


# =========================================================
# CONSENTIMIENTO INFORMADO (PRO: logo solo al inicio, contacto solo al final)
# =========================================================
def generar_pdf_consentimiento(
    documento_paciente: str,
    abrir: bool = True,
    force: bool = False,
) -> str:
    pac_row = obtener_paciente(documento_paciente)
    if not pac_row:
        raise ValueError("Paciente no encontrado")

    pac = dict(pac_row)
    cfg = _get_profesional_config()

    documentos_dir, logo_path, firma_alt_path, firma_path = _get_paths_documentos()
    firma_usar = _choose_firma_path(firma_alt_path, firma_path)

    hoy = date.today().strftime("%d/%m/%Y")

    nombre = pac.get("nombre_completo") or ""
    documento = pac.get("documento") or documento_paciente
    telefono = pac.get("telefono") or ""
    tipo_doc = pac.get("tipo_documento") or "Cédula de ciudadanía"

    # ✅ Mapeo solicitado
    contacto_emergencia_nombre = pac.get("contacto_emergencia_nombre") or ""

    filename = os.path.join(
        documentos_dir,
        _safe_filename(f"Consentimiento - {nombre} ({documento}).pdf"),
    )

    if os.path.exists(filename) and not force:
        if abrir:
            _open_if_windows(filename)
        return filename

    if os.path.exists(filename) and force:
        try:
            os.remove(filename)
        except Exception:
            pass

    normal, title, subtitle, small, header_contact = _styles()

    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    story = []

    # ✅ Logo SOLO al inicio
    _header_logo_only(story, logo_path)

    story.append(Paragraph("CONSENTIMIENTO INFORMADO PARA SERVICIO DE ATENCIÓN PSICOLÓGICA", title))
    story.append(Spacer(1, 8))

    bienvenida = (
        "Permítame darle la Bienvenida a mi consulta psicológica. En este documento encontrará información "
        "importante sobre mis servicios profesionales y las reglas de funcionamiento en contrato de atención con lo "
        "especificado en las políticas del Ministerio de Protección Social y del Colegio Colombiano de "
        "Psicólogos, sobre los derechos de los pacientes. Aunque este documento puede ser un poco largo, "
        "es muy importante que lo lea y lo entienda. Al firmarlo, indica que está de acuerdo con las reglas del "
        "trabajo que vamos a realizar en conjunto. Con mucho gusto, estaré en disposición de responder "
        "cualquier pregunta que pueda tener sobre esto ahora o en el futuro."
    )
    story.append(Paragraph(bienvenida, normal))
    story.append(Spacer(1, 10))

    story.append(Paragraph("DATOS DE CONTACTO", subtitle))

    label_contacto = Paragraph("Persona de contacto<br/>o representante legal:", ParagraphStyle(
        "lbl",
        parent=small,
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
        textColor=colors.HexColor("#333333"),
    ))

    data = [
        [Paragraph("Fecha:", ParagraphStyle("lbl2", parent=small, fontName="Helvetica-Bold")), hoy],
        [Paragraph("Nombres y apellidos:", ParagraphStyle("lbl2", parent=small, fontName="Helvetica-Bold")), nombre],
        [Paragraph("Tipo de documento:", ParagraphStyle("lbl2", parent=small, fontName="Helvetica-Bold")), tipo_doc],
        [Paragraph("Número de documento:", ParagraphStyle("lbl2", parent=small, fontName="Helvetica-Bold")), str(documento)],
        [label_contacto, contacto_emergencia_nombre],
        [Paragraph("Número de teléfono:", ParagraphStyle("lbl2", parent=small, fontName="Helvetica-Bold")), str(telefono)],
    ]
    
    t = Table(data, colWidths=[78 * mm, 87 * mm])
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#333333")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 10))

    story.append(Paragraph("SERVICIOS PSICOLÓGICOS", subtitle))

    servicios = (
        "La terapia psicológica es una relación entre personas que trabajan profesionalmente en colaboración "
        "en búsqueda del objetivo común de mejorar la calidad de vida y aumentar el bienestar psicológico "
        "del consultante. Por lo tanto, conlleva derechos y responsabilidades por parte de cada uno. Antes de "
        "decidir iniciar el proceso, es muy importante que entienda con claridad sus derechos y "
        "responsabilidades como consultante. También es importante que conozca y tenga presentes las "
        "limitaciones legales de algunos de estos derechos. Por otra parte, Yo, como terapeuta, también tengo "
        "responsabilidades hacia Usted. En los siguientes párrafos se describen esos derechos y "
        "responsabilidades.<br/><br/>"
        "La terapia psicológica tiene al mismo tiempo beneficios y riesgos. Como en el proceso terapéutico "
        "con frecuencia es necesario hablar o enfrentar aspectos dolorosos, los riesgos pueden incluir la "
        "posibilidad de sentir sensaciones desagradables o incómodas, como, por ejemplo, malestar, "
        "ansiedad, tristeza, rabia o frustración, entre otras. Sin embargo, las terapias psicológicas que están "
        "basadas en evidencia han demostrado en múltiples estudios de investigación que tienen efectos "
        "benéficos para las personas que llevan a cabo el proceso y cumplen con las indicaciones. La terapia "
        "psicológica puede producir una reducción importante de malestar psicológico y emocional, y además "
        "ayudar a aumentar los niveles generales de satisfacción en la vida y en las relaciones "
        "interpersonales, así como el nivel de autoconocimiento y consciencia vital. Además, puede ayudarle "
        "a través de herramientas concretas para afrontar nuevas situaciones y tener un mejor manejo de "
        "fuentes de tensión o de estrés y generar estrategias efectivas de solución de problemas. Sin "
        "embargo, como los resultados de la terapia dependen de varios factores, entre ellos un papel activo "
        "de su parte, no es posible garantizar los resultados. Para lograr aumentar la probabilidad de lograr "
        "los resultados esperados, es necesario que siga las indicaciones y practique fuera de las sesiones "
        "en el consultorio."
    )
    story.append(Paragraph(servicios, normal))
    story.append(Spacer(1, 10))

    story.append(Paragraph("CITAS Y SESIONES", subtitle))
    citas = (
        "Las sesiones por lo general tienen una duración aproximada de 40-60 minutos de duración y en la "
        "mayoría de los casos se realizan una vez a la semana. Habrá situaciones especiales, en las que, "
        "por la naturaleza de la intervención, puede ser necesario programar sesiones de mayor duración, de "
        "90 minutos, o de mayor frecuencia, en cuyo caso se discutirá y acordará previamente con el "
        "consultante.<br/><br/>"
        "Se respetará la cita asignada, y no se le asignará a ninguna otra persona. En caso de que tenga que "
        "cancelarla o reprogramarla, por favor informe con un período de anticipación de por lo menos 24 "
        "horas, con el fin de que pueda ser reasignada a otra persona en lista de espera. En caso de no asistir "
        "a una sesión sin cancelar previamente, se hará el cobro completo de la sesión, a menos que se trate "
        "de un motivo excepcional o de fuerza mayor. En la medida de lo posible, trataremos de reprogramar "
        "la sesión lo más pronto posible. Finalmente, en caso de llegar tarde, la sesión terminará a la hora "
        "acordada previamente.<br/><br/>"
        "Se espera que el pago por consulta se realice en cada sesión, aunque en algunos casos se pueden "
        "acordar otras formas de pago de acuerdo a las circunstancias, aunque en ningún caso se puede "
        "acumular un valor superior a 3 sesiones. Los pagos se realizan en efectivo preferiblemente, o "
        "mediante transferencia bancaria."
    )
    story.append(Paragraph(citas, normal))

    story.append(PageBreak())

    # ✅ Página 2 sin logo repetido ni contactos
    story.append(Paragraph("CONFIDENCIALIDAD Y LÍMITES", subtitle))
    confid = (
        "De acuerdo con lo establecido en la Constitución Nacional, en el Código de Procedimiento Civil y en "
        "el Código Deontológico del Psicólogo, la totalidad de la información, así como los registros e historias "
        "clínicas, están cobijadas por el secreto profesional. Por consiguiente, no discutiré ninguna "
        "información revelada en consulta con ninguna persona ni entidad. En caso de que, por algún motivo, "
        "como interconsulta profesional o informe psicológico solicitado, solamente podré suministrar "
        "información específica, previa aprobación escrita del consultante. En este sentido, no podré revelar "
        "a nadie que Usted está asistiendo a consulta profesional, y tomo todas las medidas necesarias para "
        "salvaguardar la confidencialidad del material escrito relacionado, así como de la historia clínica. Sin "
        "embargo, la confidencialidad tiene un límite, de acuerdo con lo señalado en el artículo 2o, numeral "
        "5o de la Ley 1090 de 2006, dentro del cual se estipula que en caso de tener información de "
        "intenciones de atentar contra su vida o de hacer daño o atentar contra la vida de otras personas, o "
        "si es de nuestro conocimiento una situación de abuso hacia niños o ancianos, tenemos la obligación "
        "ética y legal de revelar de inmediato esta información a las personas o autoridades competentes. "
        "Por lo tanto, tengo la responsabilidad de valorar la gravedad de la situación para establecer el límite "
        "de confidencialidad."
    )
    story.append(Paragraph(confid, normal))
    story.append(Spacer(1, 10))

    story.append(Paragraph("DERECHO A SUSPENDER EL TRATAMIENTO", subtitle))
    susp = (
        "Usted tiene el derecho de suspender el tratamiento en el momento en el que desee. Sin embargo, "
        "es recomendable que le manifieste su decisión a su terapeuta con el fin de que tenga oportunidad "
        "de dar retroalimentación y a escuchar las recomendaciones que le pueda hacer el terapeuta. De la "
        "misma forma, como terapeuta puedo decidir suspender el tratamiento si considero que no está "
        "siendo benéfico para sus objetivos, o si hay retrasos o cancelaciones reiteradas o si no hay suficiente "
        "cumplimiento o adherencia a las recomendaciones terapéuticas. En tales casos, aunque puedo "
        "hacer sugerencias de tratamiento alternativo, Usted tiene la responsabilidad de buscar otras "
        "alternativas de atención profesional de salud mental. Al firmar este Consentimiento Informado "
        "declara que es mayor de edad y lo hace en su propio nombre."
    )
    story.append(Paragraph(susp, normal))
    story.append(Spacer(1, 16))

    # ✅ Firmas con firma alt en el bloque "Profesional"
    firma_img = _image_scaled(firma_usar, 40, 14)  # tamaño adecuado para colocarlo sobre la línea
    profesional_nombre = cfg.get("nombre_profesional") or "Nombre Profesional"
    profesional_tp = cfg.get("tp") or ""

    firmas = Table(
        [
            ["", "", firma_img if firma_img else ""],               # 👈 FIRMA ARRIBA
            ["________________________", "_____________________", "_________________________"],  # 👈 LINEA
            ["Firma Paciente", "Firma representante legal", "Profesional"],
            ["", "", profesional_nombre],
            ["", "", f"T. pro No: {profesional_tp}"],
        ],
        colWidths=[55 * mm, 55 * mm, 55 * mm],
    )
    firmas.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),

                # paddings finos para que firma “bese” la línea (como firma real)
                ("BOTTOMPADDING", (0, 0), (-1, 0), 0),   # fila firma
                ("TOPPADDING", (0, 1), (-1, 1), 0),      # fila línea
                ("TOPPADDING", (0, 0), (-1, 0), 0),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 0),

                ("TOPPADDING", (0, 2), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 2), (-1, -1), 2),
            ]
        )
    )
    story.append(firmas)
    story.append(Spacer(1, 220))

    # ✅ Contacto SOLO al final del documento (debajo de firmas)
    story.append(Paragraph("Sara Hernández Ramírez. Contacto: 3052374794", header_contact))
    story.append(Paragraph("Mail: sara.hdz.psicologa@gmail.com", header_contact))

    doc.build(story)

    if abrir:
        _open_if_windows(filename)
    return filename


# =========================================================
# CERTIFICADO ASISTENCIA (PRO: espaciado, sexo, firma_alt, profesional dinámico)
# =========================================================
def generar_pdf_certificado_asistencia(
    cita_id: int,
    abrir: bool = True,
    force: bool = False,
) -> str:
    row = obtener_cita_con_paciente(cita_id)
    if not row:
        raise ValueError("Cita no encontrada")

    data = dict(row)
    cfg = _get_profesional_config()

    documentos_dir, logo_path, firma_alt_path, firma_path = _get_paths_documentos()
    firma_usar = _choose_firma_path(firma_alt_path, firma_path)

    # Paciente (sexo + tipo documento con fallback a obtener_paciente)
    nombre = data.get("nombre_completo") or "Paciente"
    documento_paciente = data.get("documento_paciente") or data.get("documento") or ""
    documento = documento_paciente

    sexo = (data.get("sexo") or "").strip()
    tipo_doc = (data.get("tipo_documento") or "").strip()

    # 🔥 Fallback robusto: si el JOIN no trae sexo/tipo_documento, lo leemos de pacientes
    if not sexo or not tipo_doc:
        try:
            pac_row = obtener_paciente(documento_paciente)
            if pac_row:
                pac = dict(pac_row)
                sexo = sexo or (pac.get("sexo") or "")
                tipo_doc = tipo_doc or (pac.get("tipo_documento") or "")
        except Exception:
            pass

    palabra_ident = _identificado_según_sexo(sexo)
    tipo_doc_txt = _tipo_doc_a_texto(tipo_doc)

    # Cita
    dt = _parse_fecha_hora(data.get("fecha_hora"))
    if not dt:
        raise ValueError("La cita no tiene fecha_hora válida.")

    # Tu BD no tiene duración, usamos 60 min por defecto (si luego agregas duración, lo conectamos)
    dt_fin = dt + timedelta(minutes=60)

    # Formato del certificado de referencia
    ciudad = (cfg.get("ciudad") or "Medellín").strip()
    fecha_expedicion = _format_fecha_larga_es(date.today())

    fecha_cita_str = _format_fecha_larga_es(dt.date()).replace(str(dt.year), f"del {dt.year}")
    hora_ini = _format_hora_12h(dt)
    hora_fin = _format_hora_12h(dt_fin)

    profesional_nombre = cfg.get("nombre_profesional") or "Sara Hernández Ramírez"
    profesional_tp = cfg.get("tp") or "180733"

    filename = os.path.join(
        documentos_dir,
        _safe_filename(f"Certificado Asistencia - {nombre} ({documento}) - {dt.strftime('%d-%m-%Y')}.pdf"),
    )

    if os.path.exists(filename) and not force:
        if abrir:
            _open_if_windows(filename)
        return filename

    if os.path.exists(filename) and force:
        try:
            os.remove(filename)
        except Exception:
            pass

    normal, title, subtitle, small, _ = _styles()

    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    story = []

    _header_logo_only(story, logo_path)

    story.append(Paragraph("CERTIFICADO DE ASISTENCIA", ParagraphStyle("ct", parent=title, fontSize=15)))
    story.append(Spacer(1, 30))

    story.append(Paragraph(f"{ciudad}, {fecha_expedicion}", normal))
    story.append(Spacer(1, 24))

    story.append(Paragraph("A quien pueda interesar", normal))
    story.append(Spacer(1, 70))

    # ✅ Texto con palabra de sexo condicional
    texto = (
        f"Con la presente se hace constar que <b>{nombre}</b> {palabra_ident.lower()} con "
        f"{tipo_doc_txt} No <b>{documento}</b> asistió a consulta psicológica el día "
        f"<b>{fecha_cita_str}</b> de <b>{hora_ini}</b> a <b>{hora_fin}</b> con la profesional "
        f"de salud mental <b>{profesional_nombre}</b>."
    )
    story.append(Paragraph(texto, normal))

    # ✅ Espaciado “pro” para que no quede vacío (similar al de referencia)
    story.append(Spacer(1, 80))

   # Firma: un poco más pequeña y alineada a la izquierda, ANTES del bloque final
    firma_img = _image_scaled(firma_usar, 40, 14)  # ↓ tamaño
    if firma_img:
        firma_tbl = Table([[firma_img]], colWidths=[160 * mm])
        firma_tbl.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(firma_tbl)
        story.append(Spacer(1, 10))
    else:
        story.append(Spacer(1, 25))

    # Bloque final (alineado con la firma)
    story.append(Paragraph("Psicóloga Clínica", normal))
    story.append(Paragraph("Especialista en psicología clínica y salud mental", normal))
    story.append(Paragraph(f"T.P {profesional_tp}", normal))

    doc.build(story)

    if abrir:
        _open_if_windows(filename)
    return filename

##################################################
#    FORMATO CONSENTIMIENTO VACIO PARA IMPRESION
##################################################

def generar_pdf_consentimiento_vacio(
    out_path: str,
    abrir: bool = False,
    force: bool = True,
) -> str:
    """
    Genera el consentimiento informado SIN datos (ni paciente ni profesional),
    para imprimir y diligenciar manualmente.
    Guarda EXACTAMENTE en out_path (no usa carpeta Documentos).
    """
    if not out_path:
        raise ValueError("Debe especificar out_path")

    out_path = os.path.abspath(out_path)

    if os.path.exists(out_path) and force:
        try:
            os.remove(out_path)
        except Exception:
            pass

    _, logo_path, firma_alt_path, firma_path = _get_paths_documentos()

    normal, title, subtitle, small, header_contact = _styles()

    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    story = []

    # Logo SOLO al inicio (como tu versión PRO)
    _header_logo_only(story, logo_path)

    story.append(Paragraph("CONSENTIMIENTO INFORMADO PARA SERVICIO DE ATENCIÓN PSICOLÓGICA", title))
    story.append(Spacer(1, 8))

    bienvenida = (
        "Permítame darle la Bienvenida a mi consulta psicológica. En este documento encontrará información "
        "importante sobre mis servicios profesionales y las reglas de funcionamiento en contrato de atención con lo "
        "especificado en las políticas del Ministerio de Protección Social y del Colegio Colombiano de "
        "Psicólogos, sobre los derechos de los pacientes. Aunque este documento puede ser un poco largo, "
        "es muy importante que lo lea y lo entienda. Al firmarlo, indica que está de acuerdo con las reglas del "
        "trabajo que vamos a realizar en conjunto. Con mucho gusto, estaré en disposición de responder "
        "cualquier pregunta que pueda tener sobre esto ahora o en el futuro."
    )
    story.append(Paragraph(bienvenida, normal))
    story.append(Spacer(1, 10))

    story.append(Paragraph("DATOS DE CONTACTO", subtitle))

    label_contacto = Paragraph(
        "Persona de contacto<br/>o representante legal:",
        ParagraphStyle(
            "lbl",
            parent=small,
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12,
            textColor=colors.HexColor("#333333"),
        ),
    )

    # Campos en blanco
    data = [
        [Paragraph("Fecha:", ParagraphStyle("lbl2", parent=small, fontName="Helvetica-Bold")), "____/____/________"],
        [Paragraph("Nombres y apellidos:", ParagraphStyle("lbl2", parent=small, fontName="Helvetica-Bold")), ""],
        [Paragraph("Tipo de documento:", ParagraphStyle("lbl2", parent=small, fontName="Helvetica-Bold")), ""],
        [Paragraph("Número de documento:", ParagraphStyle("lbl2", parent=small, fontName="Helvetica-Bold")), ""],
        [label_contacto, ""],
        [Paragraph("Número de teléfono:", ParagraphStyle("lbl2", parent=small, fontName="Helvetica-Bold")), ""],
    ]

    t = Table(data, colWidths=[78 * mm, 87 * mm])
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#333333")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 10))

    story.append(Paragraph("SERVICIOS PSICOLÓGICOS", subtitle))

    servicios = (
        "La terapia psicológica es una relación entre personas que trabajan profesionalmente en colaboración "
        "en búsqueda del objetivo común de mejorar la calidad de vida y aumentar el bienestar psicológico "
        "del consultante. Por lo tanto, conlleva derechos y responsabilidades por parte de cada uno. Antes de "
        "decidir iniciar el proceso, es muy importante que entienda con claridad sus derechos y "
        "responsabilidades como consultante. También es importante que conozca y tenga presentes las "
        "limitaciones legales de algunos de estos derechos. Por otra parte, Yo, como terapeuta, también tengo "
        "responsabilidades hacia Usted. En los siguientes párrafos se describen esos derechos y "
        "responsabilidades.<br/><br/>"
        "La terapia psicológica tiene al mismo tiempo beneficios y riesgos. Como en el proceso terapéutico "
        "con frecuencia es necesario hablar o enfrentar aspectos dolorosos, los riesgos pueden incluir la "
        "posibilidad de sentir sensaciones desagradables o incómodas, como, por ejemplo, malestar, "
        "ansiedad, tristeza, rabia o frustración, entre otras. Sin embargo, las terapias psicológicas que están "
        "basadas en evidencia han demostrado en múltiples estudios de investigación que tienen efectos "
        "benéficos para las personas que llevan a cabo el proceso y cumplen con las indicaciones. La terapia "
        "psicológica puede producir una reducción importante de malestar psicológico y emocional, y además "
        "ayudar a aumentar los niveles generales de satisfacción en la vida y en las relaciones "
        "interpersonales, así como el nivel de autoconocimiento y consciencia vital. Además, puede ayudarle "
        "a través de herramientas concretas para afrontar nuevas situaciones y tener un mejor manejo de "
        "fuentes de tensión o de estrés y generar estrategias efectivas de solución de problemas. Sin "
        "embargo, como los resultados de la terapia dependen de varios factores, entre ellos un papel activo "
        "de su parte, no es posible garantizar los resultados. Para lograr aumentar la probabilidad de lograr "
        "los resultados esperados, es necesario que siga las indicaciones y practique fuera de las sesiones "
        "en el consultorio."
    )
    story.append(Paragraph(servicios, normal))
    story.append(Spacer(1, 10))

    story.append(Paragraph("CITAS Y SESIONES", subtitle))
    citas = (
        "Las sesiones por lo general tienen una duración aproximada de 40-60 minutos de duración y en la "
        "mayoría de los casos se realizan una vez a la semana. Habrá situaciones especiales, en las que, "
        "por la naturaleza de la intervención, puede ser necesario programar sesiones de mayor duración, de "
        "90 minutos, o de mayor frecuencia, en cuyo caso se discutirá y acordará previamente con el "
        "consultante.<br/><br/>"
        "Se respetará la cita asignada, y no se le asignará a ninguna otra persona. En caso de que tenga que "
        "cancelarla o reprogramarla, por favor informe con un período de anticipación de por lo menos 24 "
        "horas, con el fin de que pueda ser reasignada a otra persona en lista de espera. En caso de no asistir "
        "a una sesión sin cancelar previamente, se hará el cobro completo de la sesión, a menos que se trate "
        "de un motivo excepcional o de fuerza mayor. En la medida de lo posible, trataremos de reprogramar "
        "la sesión lo más pronto posible. Finalmente, en caso de llegar tarde, la sesión terminará a la hora "
        "acordada previamente.<br/><br/>"
        "Se espera que el pago por consulta se realice en cada sesión, aunque en algunos casos se pueden "
        "acordar otras formas de pago de acuerdo a las circunstancias, aunque en ningún caso se puede "
        "acumular un valor superior a 3 sesiones. Los pagos se realizan en efectivo preferiblemente, o "
        "mediante transferencia bancaria."
    )
    story.append(Paragraph(citas, normal))

    story.append(PageBreak())

    story.append(Paragraph("CONFIDENCIALIDAD Y LÍMITES", subtitle))
    confid = (
        "De acuerdo con lo establecido en la Constitución Nacional, en el Código de Procedimiento Civil y en "
        "el Código Deontológico del Psicólogo, la totalidad de la información, así como los registros e historias "
        "clínicas, están cobijadas por el secreto profesional. Por consiguiente, no discutiré ninguna "
        "información revelada en consulta con ninguna persona ni entidad. En caso de que, por algún motivo, "
        "como interconsulta profesional o informe psicológico solicitado, solamente podré suministrar "
        "información específica, previa aprobación escrita del consultante. En este sentido, no podré revelar "
        "a nadie que Usted está asistiendo a consulta profesional, y tomo todas las medidas necesarias para "
        "salvaguardar la confidencialidad del material escrito relacionado, así como de la historia clínica. Sin "
        "embargo, la confidencialidad tiene un límite, de acuerdo con lo señalado en el artículo 2o, numeral "
        "5o de la Ley 1090 de 2006, dentro del cual se estipula que en caso de tener información de "
        "intenciones de atentar contra su vida o de hacer daño o atentar contra la vida de otras personas, o "
        "si es de nuestro conocimiento una situación de abuso hacia niños o ancianos, tenemos la obligación "
        "ética y legal de revelar de inmediato esta información a las personas o autoridades competentes. "
        "Por lo tanto, tengo la responsabilidad de valorar la gravedad de la situación para establecer el límite "
        "de confidencialidad."
    )
    story.append(Paragraph(confid, normal))
    story.append(Spacer(1, 10))

    story.append(Paragraph("DERECHO A SUSPENDER EL TRATAMIENTO", subtitle))
    susp = (
        "Usted tiene el derecho de suspender el tratamiento en el momento en el que desee. Sin embargo, "
        "es recomendable que le manifieste su decisión a su terapeuta con el fin de que tenga oportunidad "
        "de dar retroalimentación y a escuchar las recomendaciones que le pueda hacer el terapeuta. De la "
        "misma forma, como terapeuta puedo decidir suspender el tratamiento si considero que no está "
        "siendo benéfico para sus objetivos, o si hay retrasos o cancelaciones reiteradas o si no hay suficiente "
        "cumplimiento o adherencia a las recomendaciones terapéuticas. En tales casos, aunque puedo "
        "hacer sugerencias de tratamiento alternativo, Usted tiene la responsabilidad de buscar otras "
        "alternativas de atención profesional de salud mental. Al firmar este Consentimiento Informado "
        "declara que es mayor de edad y lo hace en su propio nombre."
    )
    story.append(Paragraph(susp, normal))
    story.append(Spacer(1, 16))

    # Firmas vacías (sin nombre profesional, sin TP, sin firma)
    firmas = Table(
        [
            ["________________________", "_____________________", "_________________________"],
            ["Firma Paciente", "Firma representante legal", "Profesional"],
            ["", "", "T. pro No:"],
        ],
        colWidths=[55 * mm, 55 * mm, 55 * mm],
    )
    firmas.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(firmas)
    story.append(Spacer(1, 220))

    # ✅ Contacto SOLO al final del documento (debajo de firmas)
    story.append(Paragraph("Sara Hernández Ramírez. Contacto: 3052374794", header_contact))
    story.append(Paragraph("Mail: sara.hdz.psicologa@gmail.com", header_contact))

    doc.build(story)

    if abrir:
        _open_if_windows(out_path)
    return out_path
