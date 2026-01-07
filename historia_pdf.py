import os
from datetime import datetime, date
import sqlite3
from html import unescape

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
    ListFlowable, 
    ListItem,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib import colors

from .fechas import calcular_edad
from .paths import get_historias_dir
from .db import (
    DB_PATH,
    obtener_paciente,
    obtener_historia_clinica,
    listar_antecedentes_medicos,
    listar_antecedentes_psicologicos,
    listar_sesiones_clinicas,
    listar_diagnosticos_historia,  # <-- NUEVO
)


# ---------- Utilidades de rutas ----------


def _get_paths_historia():
    """Devuelve (directorio_historia, ruta_logo) usando la misma base que facturas."""
    data_dir = os.path.dirname(DB_PATH)
    img_dir = os.path.join(data_dir, "imagenes")

    historias_dir = get_historias_dir()  # 👈 Mis Documentos
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

def normalize_newlines(s: str) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    # 3+ saltos -> 2
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


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



# ---------- HTML (Quill) -> ReportLab (solo para sesiones) ----------

def _sanitize_quill_inline(html: str) -> str:
    s = (html or "").strip()
    s = s.replace("<br>", "<br/>").replace("<br />", "<br/>").replace("<br/>", "<br/>")

    # quitar spans de quill
    s = re.sub(r"<span[^>]*>", "", s, flags=re.I)
    s = re.sub(r"</span\s*>", "", s, flags=re.I)

    # strong/em -> b/i para reportlab
    s = re.sub(r"</?\s*strong\s*>", lambda m: "</b>" if "/" in m.group(0) else "<b>", s, flags=re.I)
    s = re.sub(r"</?\s*em\s*>", lambda m: "</i>" if "/" in m.group(0) else "<i>", s, flags=re.I)

    # tachado no soportado bien -> quitar
    s = re.sub(r"</?\s*(s|strike)\s*>", "", s, flags=re.I)

    # links -> solo texto
    s = re.sub(r"<a[^>]*>", "", s, flags=re.I)
    s = re.sub(r"</a\s*>", "", s, flags=re.I)

    # quitar attrs en tags permitidos
    s = re.sub(r"<(b|i|u)\s+[^>]*>", r"<\1>", s, flags=re.I)

    s = unescape(s).replace("\xa0", " ")
    return s


def quill_html_to_flowables(html: str, normal_style, h1_style, h2_style):
    """
    Convierte HTML típico de Quill a flowables para reportlab.
    Soporta: p/br, b/i/u, h1/h2, ul/li.
    """
    html = (html or "").strip()
    if not html:
        return []

    out = []

    # 1) Extraer listas para procesarlas como bullets
    list_blocks = []
    def _take_list(m):
        list_blocks.append(m.group(0))
        return f"[[[LIST_{len(list_blocks)-1}]]]"

    tmp = re.sub(r"<(ul|ol)[^>]*>.*?</\1\s*>", _take_list, html, flags=re.I | re.S)
    tokens = re.split(r"(\[\[\[LIST_\d+\]\]\])", tmp)

    for part in tokens:
        part = (part or "").strip()
        if not part:
            continue

        # token de lista
        m = re.match(r"\[\[\[LIST_(\d+)\]\]\]", part)
        if m:
            idx = int(m.group(1))
            lb = list_blocks[idx]
            items = re.findall(r"<li[^>]*>(.*?)</li\s*>", lb, flags=re.I | re.S)

            bullets = []
            for it in items:
                it = _sanitize_quill_inline(it)
                if it.strip():
                    bullets.append(ListItem(Paragraph(it, normal_style)))

            if bullets:
                out.append(ListFlowable(bullets, bulletType="bullet", leftIndent=14))
                out.append(Spacer(1, 1))
            continue

        # headings
        # h1
        part2 = part
        while True:
            hm = re.search(r"<h1[^>]*>(.*?)</h1\s*>", part2, flags=re.I | re.S)
            if not hm:
                break
            before = part2[:hm.start()].strip()
            inner = hm.group(1).strip()
            after = part2[hm.end():].strip()

            if before:
                before = _sanitize_quill_inline(before)
                before = re.sub(r"</p\s*>", "\n", before, flags=re.I)
                before = re.sub(r"<p[^>]*>", "", before, flags=re.I)
                before = before.replace("\n", "<br/>").strip()
                if before:
                    out.append(Paragraph(before, normal_style))
                    out.append(Spacer(1, 2))

            inner = _sanitize_quill_inline(inner)
            if inner:
                out.append(Paragraph(f"<b>{inner}</b>", h1_style))
                out.append(Spacer(1, 2))

            part2 = after

        # h2
        while True:
            hm = re.search(r"<h2[^>]*>(.*?)</h2\s*>", part2, flags=re.I | re.S)
            if not hm:
                break
            before = part2[:hm.start()].strip()
            inner = hm.group(1).strip()
            after = part2[hm.end():].strip()

            if before:
                before = _sanitize_quill_inline(before)
                before = re.sub(r"</p\s*>", "\n", before, flags=re.I)
                before = re.sub(r"<p[^>]*>", "", before, flags=re.I)
                before = before.replace("\n", "<br/>").strip()
                if before:
                    out.append(Paragraph(before, normal_style))
                    out.append(Spacer(1, 2))

            inner = _sanitize_quill_inline(inner)
            if inner:
                out.append(Paragraph(f"<b>{inner}</b>", h2_style))
                out.append(Spacer(1, 2))

            part2 = after

        # párrafos restantes
        part2 = part2.replace("<br/>", "\n")
        part2 = re.sub(r"</p\s*>", "\n", part2, flags=re.I)
        part2 = re.sub(r"<p[^>]*>", "", part2, flags=re.I)
        part2 = _sanitize_quill_inline(part2)
        part2 = re.sub(r"\n{3,}", "\n", part2).strip()

        if part2:
            out.append(Paragraph(part2.replace("\n", "<br/>"), normal_style))
            out.append(Spacer(1, 2))

    return out


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

    # NUEVO: diagnósticos
    dx_rows = listar_diagnosticos_historia(historia["id"])
    diagnosticos = [dict(d) for d in dx_rows][::-1]  # antiguos primero

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
    story.append(_p(f"Fecha de generación del informe: {fecha_impresion}", SMALL_STYLE))
    story.append(Spacer(1, 8))

    # ==========================================================
    # DATOS DEL PACIENTE
    # ==========================================================

    story.append(Paragraph("Datos del paciente", SECTION_TITLE_STYLE))
    story.append(Spacer(1, 4))

    def _val(campo: str):
        if campo == "correo":
            v = pac.get("email") or pac.get("correo")
            return v if v not in (None, "", "None") else "-"
        if campo == "edad":
            return calcular_edad(pac.get("fecha_nacimiento"))
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
            Paragraph(_val("email"), SMALL_STYLE),
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
    story.append(_p(f"Fecha de apertura: {historia['fecha_apertura']}", SMALL_STYLE, bold=True))

    if historia.get("motivo_consulta_inicial"):
        story.append(_p("Motivo de consulta:", NORMAL_STYLE, bold=True))
        story.append(_p(historia["motivo_consulta_inicial"], NORMAL_STYLE))
        story.append(Spacer(1, 4))

    if historia.get("informacion_adicional"):
        story.append(_p("Información adicional:", NORMAL_STYLE, bold=True))
        story.append(_p(historia["informacion_adicional"], NORMAL_STYLE))
        story.append(Spacer(1, 6))

    # ==========================================================
    # DIAGNÓSTICOS (NUEVO)
    # ==========================================================

    story.append(Spacer(1, 6))
    story.append(Paragraph("Diagnósticos (CIE)", SECTION_TITLE_STYLE))

    if diagnosticos:
        for d in diagnosticos:
            sistema = d.get("sistema") or ""
            codigo = d.get("codigo") or ""
            titulo = d.get("titulo") or ""
            story.append(_p(f"{sistema} {codigo} - {titulo}", NORMAL_STYLE))
    else:
        story.append(_p("No hay diagnósticos registrados.", NORMAL_STYLE))

    story.append(Spacer(1, 8))
    story.append(
        Table(
            [[""]],
            colWidths=[170 * mm],
            style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.6, colors.HexColor("#DDDDDD"))]),
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
            style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.6, colors.HexColor("#DDDDDD"))]),
        )
    )
    story.append(Spacer(1, 8))

    # ==========================================================
    # ==========================================================
    # SESIONES CLÍNICAS
    # ==========================================================

    story.append(Paragraph("Sesiones clínicas", SECTION_TITLE_STYLE))
    story.append(_p("Listado de las sesiones registradas en la historia clínica.", SMALL_STYLE))
    story.append(Spacer(1, 4))

    if not sesiones:
        story.append(_p("No hay sesiones registradas.", NORMAL_STYLE))
    else:
        # --- precargar horas de citas para las sesiones vinculadas ---
        cita_hora_map = {}
        try:
            cita_ids = []
            for s in (sesiones or []):
                sd = dict(s) if not isinstance(s, dict) else s
                cid = sd.get("cita_id")
                if cid:
                    try:
                        cita_ids.append(int(cid))
                    except Exception:
                        pass

            cita_ids = sorted(set(cita_ids))
            if cita_ids:
                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                qmarks = ",".join(["?"] * len(cita_ids))
                cur.execute(f"SELECT id, fecha_hora FROM citas WHERE id IN ({qmarks});", tuple(cita_ids))
                for r in cur.fetchall():
                    try:
                        cita_hora_map[int(r["id"])] = r["fecha_hora"]
                    except Exception:
                        pass
                conn.close()
        except Exception:
            cita_hora_map = {}

        for idx, s in enumerate(sesiones, start=1):
            s = dict(s) if not isinstance(s, dict) else s

            # Fecha a mostrar:
            # - Si hay cita_id => usar citas.fecha_hora (con hora real)
            # - Si NO hay cita_id => usar sesiones_clinicas.fecha (solo fecha)
            fecha_txt = (s.get("fecha") or "").strip()
            cid = s.get("cita_id")

            if cid:
                try:
                    fh = cita_hora_map.get(int(cid))
                except Exception:
                    fh = None

                if fh:
                    try:
                        fecha_txt = datetime.fromisoformat(str(fh)).strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        # fallback: al menos yyyy-mm-dd HH:MM si viene como string
                        fecha_txt = str(fh)[:16]

            story.append(_p(f"Cita {idx} - Fecha: {fecha_txt}", NORMAL_STYLE, bold=True))
            story.append(Spacer(1, 2))

            titulo = (s.get("titulo") or "").strip()
            if titulo:
                story.append(_p(titulo, NORMAL_STYLE))

            contenido_html = (s.get("contenido_html") or "").strip()
            contenido = (s.get("contenido") or "").strip()

            if contenido_html:
                story.extend(
                    quill_html_to_flowables(
                        contenido_html,
                        normal_style=NORMAL_STYLE,
                        h1_style=SECTION_TITLE_STYLE,
                        h2_style=NORMAL_STYLE,
                    )
                )
            elif contenido:
                story.append(_p(normalize_newlines(contenido), NORMAL_STYLE))

            obs = (s.get("observaciones") or "").strip()
            if obs:
                story.append(Spacer(1, 2))
                story.append(_p(obs, SMALL_STYLE))

            story.append(Spacer(1, 4))
            story.append(
                Table(
                    [[""]],
                    colWidths=[170 * mm],
                    style=TableStyle(
                        [("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#E0E0E0"))]
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
