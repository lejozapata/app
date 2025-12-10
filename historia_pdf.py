import os
from datetime import datetime, date

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
import re
from xml.sax.saxutils import escape
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib import colors

from db import (
    DB_PATH,
    obtener_paciente,
    obtener_historia_clinica,
    listar_antecedentes_medicos,
    listar_antecedentes_psicologicos,
    listar_sesiones_clinicas,
)

# ---------- Utilidades de rutas ----------


def _get_paths_historia():
    """Devuelve (directorio_historia, ruta_logo) usando la misma base que facturas."""
    data_dir = os.path.dirname(DB_PATH)
    img_dir = os.path.join(data_dir, "imagenes")
    historias_dir = os.path.join(data_dir, "historias_pdf")
    os.makedirs(historias_dir, exist_ok=True)

    logo_path = os.path.join(img_dir, "logo.png")
    return historias_dir, logo_path


# ---------- Estilos ----------

accent_color = colors.HexColor("#f27c4a")  # naranja Sara

TITLE_STYLE = ParagraphStyle(
    name="Title",
    fontName="Helvetica-Bold",
    fontSize=18,
    leading=22,
    alignment=TA_CENTER,
    textColor=colors.HexColor("#333333"),
    spaceAfter=10,
)

SECTION_TITLE_STYLE = ParagraphStyle(
    name="SectionTitle",
    fontName="Helvetica-Bold",
    fontSize=13,
    leading=16,
    textColor=accent_color,
    spaceBefore=8,
    spaceAfter=4,
)

NORMAL_STYLE = ParagraphStyle(
    name="Normal",
    fontName="Helvetica",
    fontSize=10.5,
    leading=14,
    alignment=TA_LEFT,
    textColor=colors.HexColor("#333333"),
    spaceAfter=4,
)

SMALL_STYLE = ParagraphStyle(
    name="Small",
    fontName="Helvetica",
    fontSize=9.5,
    leading=12,
    alignment=TA_LEFT,
    textColor=colors.HexColor("#555555"),
    spaceAfter=2,
)


def markdown_to_html(text: str) -> str:
    """
    Convierte un subset sencillo de Markdown a HTML soportado por reportlab:
    - **texto** -> <b>texto</b>
    - _texto_  -> <i>texto</i>
    - ==texto== -> <font color="#ff7b47">texto</font> (resaltado naranja)
    - Saltos de línea -> <br/>
    """

    if text is None:
        return ""

    text = str(text)

    text = escape(text)

    text = re.sub(
        r"==(.+?)==",
        r'<font color="#ff7b47">\1</font>',
        text,
        flags=re.DOTALL,
    )

    text = re.sub(
        r"\*\*(.+?)\*\*",
        r"<b>\1</b>",
        text,
        flags=re.DOTALL,
    )

    text = re.sub(
        r"_(.+?)_",
        r"<i>\1</i>",
        text,
        flags=re.DOTALL,
    )

    text = text.replace("\n", "<br/>")

    return text


def _p(
    text: str,
    style: ParagraphStyle = NORMAL_STYLE,
    bold: bool = False,
    use_markdown: bool = True,
):
    """
    Helper para crear Paragraph:
    - Si use_markdown=True, interpreta Markdown sencillo (**, _, ==).
    - Si bold=True, envuelve todo el resultado en <b>.
    """
    if use_markdown:
        html = markdown_to_html(text)
    else:
        html = escape(str(text or ""))

    if bold:
        html = f"<b>{html}</b>"

    return Paragraph(html, style)


# ---------- Generación de PDF de historia clínica ----------


def generar_pdf_historia(
    documento_paciente: str,
    abrir: bool = True,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
) -> str:
    """
    Genera el PDF de historia clínica del paciente.
    Si se proporcionan fecha_desde y fecha_hasta, solo incluye las sesiones
    dentro de ese rango (ambos extremos inclusive).
    El archivo se crea en ./historias_pdf/ dentro de la ruta de datos.
    """
    pac_row = obtener_paciente(documento_paciente)
    if not pac_row:
        raise ValueError("Paciente no encontrado")

    pac = dict(pac_row)

    historia_row = obtener_historia_clinica(documento_paciente)
    if not historia_row:
        raise ValueError("El paciente no tiene historia clínica registrada.")

    historia = dict(historia_row)

    sesiones_rows = listar_sesiones_clinicas(historia["id"])
    sesiones = [dict(s) for s in sesiones_rows][::-1]  # más antiguas primero

    # --- Filtrado opcional por rango de fechas ---
    if fecha_desde and fecha_hasta:
        def _parse_fecha(fecha_raw):
            if isinstance(fecha_raw, datetime):
                return fecha_raw.date()
            if isinstance(fecha_raw, date):
                return fecha_raw
            try:
                return datetime.strptime(str(fecha_raw)[:10], "%Y-%m-%d").date()
            except Exception:
                return None

        fd = fecha_desde if isinstance(fecha_desde, date) else _parse_fecha(fecha_desde)
        fh = fecha_hasta if isinstance(fecha_hasta, date) else _parse_fecha(fecha_hasta)

        if fd and fh:
            sesiones = [
                s
                for s in sesiones
                if (d := _parse_fecha(s.get("fecha"))) is not None and fd <= d <= fh
            ]

    antecedentes_med = listar_antecedentes_medicos(documento_paciente)
    antecedentes_psico = listar_antecedentes_psicologicos(documento_paciente)

    historias_dir, logo_path = _get_paths_historia()
    archivo_pdf = os.path.join(
        historias_dir,
        f"{pac['nombre_completo']} - Historia Clínica.pdf",
    )

    doc = SimpleDocTemplate(
        archivo_pdf,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
    )

    story = []

    # ---------- Encabezado: logo + título ----------
    if os.path.exists(logo_path):
        img = Image(logo_path)
        img._restrictSize(35 * mm, 20 * mm)
        img.hAlign = "LEFT"
        story.append(img)
        story.append(Spacer(1, 4))

    story.append(Paragraph("HISTORIA CLÍNICA", TITLE_STYLE))

    fecha_impresion = datetime.now().strftime("%d/%m/%Y %H:%M")
    story.append(
        _p(f"Fecha de generación del informe: {fecha_impresion}", SMALL_STYLE)
    )
    story.append(Spacer(1, 8))

    # ==========================================================
    # DATOS DEL PACIENTE
    # ==========================================================

    story.append(Paragraph("Datos del paciente", SECTION_TITLE_STYLE))
    story.append(Spacer(1, 4))

    def _val(campo: str):
        v = pac.get(campo)
        return v if v not in (None, "", "None") else "-"

    datos_matrix = [
        [
            Paragraph("<b>Nombre completo:</b>", SMALL_STYLE),
            Paragraph(_val("nombre_completo"), SMALL_STYLE),
            Paragraph("<b>Sexo:</b>", SMALL_STYLE),
            Paragraph(_val("sexo"), SMALL_STYLE),
            Paragraph("<b>Dirección:</b>", SMALL_STYLE),
            Paragraph(_val("direccion"), SMALL_STYLE),
        ],
        [
            Paragraph("<b>Documento&#58;</b>", SMALL_STYLE),
            Paragraph(_val("documento"), SMALL_STYLE),
            Paragraph("<b>Estado civil:</b>", SMALL_STYLE),
            Paragraph(_val("estado_civil"), SMALL_STYLE),
            Paragraph("<b>Correo:</b>", SMALL_STYLE),
            Paragraph(_val("correo"), SMALL_STYLE),
        ],
        [
            Paragraph("<b>Fecha nacimiento:</b>", SMALL_STYLE),
            Paragraph(_val("fecha_nacimiento"), SMALL_STYLE),
            Paragraph("<b>Escolaridad:</b>", SMALL_STYLE),
            Paragraph(_val("escolaridad"), SMALL_STYLE),
            Paragraph("<b>Teléfono:</b>", SMALL_STYLE),
            Paragraph(_val("telefono"), SMALL_STYLE),
        ],
        [
            Paragraph("<b>Edad:</b>", SMALL_STYLE),
            Paragraph(_val("edad"), SMALL_STYLE),
            Paragraph("<b>EPS:</b>", SMALL_STYLE),
            Paragraph(_val("eps"), SMALL_STYLE),
            Paragraph("", SMALL_STYLE),
            Paragraph("", SMALL_STYLE),
        ],
    ]

    datos_table = Table(
        datos_matrix,
        colWidths=[28 * mm, 32 * mm, 28 * mm, 32 * mm, 28 * mm, 32 * mm],
        hAlign="LEFT",
    )
    datos_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#CCCCCC")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )

    story.append(datos_table)
    story.append(Spacer(1, 10))

    # ==========================================================
    # HISTORIA INICIAL
    # ==========================================================

    story.append(Paragraph("Historia inicial", SECTION_TITLE_STYLE))
    story.append(
        _p(f"Fecha de apertura: {historia['fecha_apertura']}", SMALL_STYLE, bold=True)
    )

    if historia.get("motivo_consulta_inicial"):
        story.append(_p("Motivo de consulta:", NORMAL_STYLE, bold=True))
        story.append(_p(historia["motivo_consulta_inicial"], NORMAL_STYLE))
        story.append(Spacer(1, 4))

    if historia.get("informacion_adicional"):
        story.append(_p("Información adicional:", NORMAL_STYLE, bold=True))
        story.append(_p(historia["informacion_adicional"], NORMAL_STYLE))
        story.append(Spacer(1, 6))

    story.append(Spacer(1, 6))
    story.append(
        Table(
            [[""]],
            colWidths=[170 * mm],
            style=TableStyle(
                [("LINEBELOW", (0, 0), (-1, -1), 0.6, colors.HexColor("#DDDDDD"))]
            ),
        )
    )
    story.append(Spacer(1, 8))

    # ==========================================================
    # ANTECEDENTES
    # ==========================================================

    story.append(Paragraph("Antecedentes de salud", SECTION_TITLE_STYLE))
    if antecedentes_med:
        for a in antecedentes_med:
            texto = f"{a['fecha_registro'][:10]} - {a['descripcion']}"
            story.append(_p(texto, NORMAL_STYLE))
    else:
        story.append(_p("No hay antecedentes de salud registrados.", NORMAL_STYLE))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Antecedentes psicológicos", SECTION_TITLE_STYLE))
    if antecedentes_psico:
        for a in antecedentes_psico:
            texto = f"{a['fecha_registro'][:10]} - {a['descripcion']}"
            story.append(_p(texto, NORMAL_STYLE))
    else:
        story.append(_p("No hay antecedentes psicológicos registrados.", NORMAL_STYLE))
    story.append(Spacer(1, 8))

    story.append(
        Table(
            [[""]],
            colWidths=[170 * mm],
            style=TableStyle(
                [("LINEBELOW", (0, 0), (-1, -1), 0.6, colors.HexColor("#DDDDDD"))]
            ),
        )
    )
    story.append(Spacer(1, 8))

    # ==========================================================
    # SESIONES CLÍNICAS
    # ==========================================================

    story.append(Paragraph("Sesiones clínicas", SECTION_TITLE_STYLE))
    story.append(
        _p("Listado de las sesiones registradas en la historia clínica.", SMALL_STYLE)
    )
    story.append(Spacer(1, 4))

    if not sesiones:
        story.append(_p("No hay sesiones registradas.", NORMAL_STYLE))
    else:
        for idx, s in enumerate(sesiones, start=1):
            story.append(
                _p(f"Cita {idx} - Fecha: {s['fecha']}", NORMAL_STYLE, bold=True)
            )
            story.append(Spacer(1, 2))

            titulo = s.get("titulo") or ""
            if titulo:
                story.append(_p(titulo, NORMAL_STYLE))
                story.append(Spacer(1, 2))

            story.append(_p(s["contenido"], NORMAL_STYLE))
            story.append(Spacer(1, 2))

            obs = s.get("observaciones") or ""
            if obs:
                story.append(_p("Observaciones:", SMALL_STYLE, bold=True))
                story.append(_p(obs, SMALL_STYLE))

            story.append(Spacer(1, 4))
            story.append(
                Table(
                    [[""]],

                    colWidths=[170 * mm],
                    style=TableStyle(
                        [
                            (
                                "LINEBELOW",
                                (0, 0),
                                (-1, -1),
                                0.4,
                                colors.HexColor("#E0E0E0"),
                            )
                        ]
                    ),
                )
            )
            story.append(Spacer(1, 4))

    doc.build(story)

    if abrir:
        try:
            if os.name == "nt":
                os.startfile(archivo_pdf)
            else:
                os.system(f'open "{archivo_pdf}"')
        except Exception:
            pass

    return archivo_pdf
