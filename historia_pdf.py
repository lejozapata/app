import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
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


def _p(text: str, style: ParagraphStyle = NORMAL_STYLE, bold: bool = False):
    if bold:
        text = f"<b>{text}</b>"
    return Paragraph(text, style)


# ---------- Generación de PDF de historia clínica ----------


def generar_pdf_historia(documento_paciente: str, abrir: bool = True) -> str:
    """
    Genera el PDF completo de historia clínica del paciente.
    Se crea (o sobreescribe) en carpeta ./historias_pdf/ dentro de la ruta de datos.
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
    # más antiguas primero
    sesiones = [dict(s) for s in sesiones_rows][::-1]

    antecedentes_med = listar_antecedentes_medicos(documento_paciente)
    antecedentes_psico = listar_antecedentes_psicologicos(documento_paciente)

    historias_dir, logo_path = _get_paths_historia()
    archivo_pdf = os.path.join(
        historias_dir,
        f"{pac['nombre_completo']} - Historia Clínica.pdf",
    )

    # Documento A4 con márgenes en mm (alineado al de facturas)
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
        img._restrictSize(35 * mm, 20 * mm)  # <--- Tamaño máximo permitido sin deformar
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
    # DATOS DEL PACIENTE - tabla tipo ficha (3 bloques)
    # ==========================================================

    story.append(Paragraph("Datos del paciente", SECTION_TITLE_STYLE))
    story.append(Spacer(1, 4))

    def _val(campo: str):
        v = pac.get(campo)
        return v if v not in (None, "", "None") else "-"

    # 3 bloques: (izq, centro, derecha) -> 4 filas
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

    # 6 columnas: etiqueta/valor x3 → ancho total 168mm (no se sale de 170mm)
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

    # ==========================================================
    # CONSTRUIR DOCUMENTO
    # ==========================================================

    doc.build(story)

    # ==========================================================
    # ABRIR ARCHIVO
    # ==========================================================

    if abrir:
        try:
            if os.name == "nt":
                os.startfile(archivo_pdf)
            else:
                os.system(f'open "{archivo_pdf}"')
        except Exception:
            pass

    return archivo_pdf
