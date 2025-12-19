import os
from datetime import datetime
from .paths import get_facturas_dir

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
from reportlab.lib.utils import ImageReader

from .db import (
    DB_PATH,
    obtener_factura_convenio,
    obtener_configuracion_profesional,
    obtener_configuracion_facturacion,
    total_a_letras_pesos,
    actualizar_ruta_pdf_factura_convenio,
)


# ---------- Utilidades de rutas ----------


def _get_paths():
    data_dir = os.path.dirname(DB_PATH)
    img_dir = os.path.join(data_dir, "imagenes")
    #facturas_dir = os.path.join(data_dir, "facturas_pdf")
    #os.makedirs(facturas_dir, exist_ok=True)

    facturas_dir = get_facturas_dir()  # 👈 Mis Documentos

    logo_path = os.path.join(img_dir, "logo.png")
    firma_path = os.path.join(img_dir, "firma.png")
    return facturas_dir, logo_path, firma_path


def _image_scaled(path: str, max_width_mm: float, max_height_mm: float):
    """
    Carga una imagen manteniendo proporción, ajustada a ancho/alto máximos.
    Devuelve un objeto Image de Platypus o None si no existe.
    """
    if not os.path.exists(path):
        return None

    max_w = max_width_mm * mm
    max_h = max_height_mm * mm

    img_reader = ImageReader(path)
    iw, ih = img_reader.getSize()
    ratio = min(max_w / iw, max_h / ih, 1.0)

    w = iw * ratio
    h = ih * ratio

    return Image(path, width=w, height=h)


# ---------- Generación de PDF ----------


def generar_pdf_factura(factura_id: int, abrir: bool = True, force: bool = False) -> str:
    """
    Genera un PDF de factura de convenio en 2 páginas:
    - Página 1: Encabezado, datos empresa, detalle, totales, forma de pago, SON, datos bancarios.
    - Página 2: Declaración renta + firma.
    """
    datos = obtener_factura_convenio(factura_id)
    if not datos:
        raise ValueError(f"No se encontró la factura con id={factura_id}")

    enc = datos["encabezado"]
    dets = datos["detalles"]
    cfg_prof = obtener_configuracion_profesional()
    cfg_fact = obtener_configuracion_facturacion()
    facturas_dir, logo_path, firma_path = _get_paths()

    numero = enc["numero"]
    fecha_str = enc["fecha"]
    fecha_dt = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    fecha_hum = fecha_dt.strftime("%d/%m/%Y")

    archivo_pdf = os.path.join(facturas_dir, f"{numero} - Sara Hernandez.pdf")

    # Si existe y NO queremos reemplazar, lo abrimos y ya
    if os.path.exists(archivo_pdf) and not force:
        if abrir and os.name == "nt":
            try:
                os.startfile(archivo_pdf)
            except Exception:
                pass
        return archivo_pdf

    # Si existe y force=True, lo borramos para regenerarlo
    if os.path.exists(archivo_pdf) and force:
        try:
            os.remove(archivo_pdf)
        except Exception:
            # Si Windows lo tiene abierto, igual intentamos regenerar (puede fallar)
            pass

    # ---------- Estilos base ----------
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    normal.fontName = "Helvetica"
    normal.fontSize = 9
    normal.leading = 12

    titulo_prof = ParagraphStyle(
        "TituloProf",
        parent=normal,
        fontSize=14,
        leading=16,
        fontName="Helvetica-Bold",
    )
    subtitulo_prof = ParagraphStyle(
        "SubtituloProf",
        parent=normal,
        fontSize=9,
        textColor=colors.HexColor("#666666"),
    )
    bold = ParagraphStyle(
        "Bold",
        parent=normal,
        fontName="Helvetica-Bold",
    )
    etiqueta = ParagraphStyle(
        "Etiqueta",
        parent=normal,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#555555"),
    )

    accent_color = colors.HexColor("#f27c4a")  # naranja para el Nº de factura

    # Ancho útil de página según los márgenes del SimpleDocTemplate (15mm a cada lado)
    page_width_mm = (A4[0] / mm) - 30  # 210mm - 15mm - 15mm = 180mm
    detalle_total_width_mm = page_width_mm

    # Definimos las columnas del detalle UNA sola vez,
    # y usamos estos anchos en todas las secciones (empresa, detalle, totales)
    col_vu_mm = 25.0      # Valor unitario
    col_cant_mm = 20.0    # Cantidad
    col_total_mm = 25.0   # VALOR COP
    col_desc_mm = detalle_total_width_mm - (col_vu_mm + col_cant_mm + col_total_mm)
    right_block_mm = col_vu_mm + col_cant_mm + col_total_mm  # bloque derecha

    doc = SimpleDocTemplate(
        archivo_pdf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    story = []

    # ==========================================================
    # PÁGINA 1
    # ==========================================================

    # ---------- Encabezado: logo + datos profesionales + Nº factura ----------
    logo_img = _image_scaled(logo_path, max_width_mm=60, max_height_mm=30)

    nombre_prof = (
        cfg_prof.get("nombre_profesional")
        or "Sara Milena Hernández Ramírez"
    )
    nit_prof = cfg_fact.get("nit") or "1216719908"

    col_izq = []
    if logo_img:
        col_izq.append(logo_img)
        col_izq.append(Spacer(1, 15))
    col_izq.append(Paragraph(nombre_prof, titulo_prof))
    col_izq.append(
        Paragraph("Psicología / Atención clínica", subtitulo_prof)
    )

    bloque_izq = Table([[col_izq]], colWidths=[100 * mm])
    bloque_izq.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    col_der = []
    col_der.append(
        Paragraph(
            "<b>FACTURA NO.</b>",
            ParagraphStyle(
                "FacturaLabel",
                parent=normal,
                alignment=2,
                fontName="Helvetica-Bold",
            ),
        )
    )
    col_der.append(
        Paragraph(
            f'<font color="{accent_color}"><b>{numero}</b></font>',
            ParagraphStyle(
                "FacturaNum",
                parent=normal,
                alignment=2,
                fontSize=13,
                leading=15,
            ),
        )
    )
    col_der.append(Spacer(1, 6))
    col_der.append(
        Paragraph(
            f"CC. {nit_prof}",
            ParagraphStyle("CC", parent=normal, alignment=2),
        )
    )

    bloque_der = Table([[col_der]], colWidths=[50 * mm])
    bloque_der.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    header_table = Table(
        [[bloque_izq, bloque_der]],
        colWidths=[(detalle_total_width_mm - 50.0) * mm, 50.0 * mm],
    )
    story.append(header_table)
    story.append(Spacer(1, 12))

    # ---------- Caja empresa + caja fecha ----------

    empresa_nombre = enc.get("empresa_nombre") or ""
    empresa_nit = enc.get("empresa_nit") or ""
    empresa_dir = enc.get("empresa_direccion") or ""
    empresa_ciudad = enc.get("empresa_ciudad") or ""
    empresa_pais = enc.get("empresa_pais") or ""

    # Queremos que la caja de fecha quede alineada con el bloque de FACTURA NO.
    separador_mm = 5.0
    # ancho de empresa = ancho útil - separador - ancho bloque derecha (50mm)
    ancho_empresa_mm = detalle_total_width_mm - separador_mm - 50.0

    caja_empresa = Table(
        [
            [Paragraph(f"<b>{empresa_nombre}</b>", normal)],
            [Paragraph(f"NIT {empresa_nit}", normal)],
            [Paragraph(empresa_dir, normal)],
            [Paragraph(f"{empresa_ciudad}, {empresa_pais}", normal)],
        ],
        colWidths=[ancho_empresa_mm * mm],
    )
    caja_empresa.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    caja_fecha = Table(
        [
            [Paragraph("<b>FECHA FACTURA</b>", normal)],
            [Paragraph(fecha_hum, bold)],
        ],
        colWidths=[50 * mm],  # <<< mismo ancho que el bloque FACTURA NO.
    )
    caja_fecha.setStyle(
    TableStyle(
        [
            ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f9cba7")),

            # centrar horizontal ambos renglones
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            # centrar vertical ambos renglones
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),

            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )
)

    bloque_empresa_fecha = Table(
        [[caja_empresa, "", caja_fecha]],
        colWidths=[ancho_empresa_mm * mm, separador_mm * mm, 55 * mm],
    )
    bloque_empresa_fecha.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (1, 0), (1, 0), 0, colors.white),
                ("LINEABOVE", (1, 0), (1, 0), 0, colors.white),
                ("LEFTPADDING", (1, 0), (1, 0), 0),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
            ]
        )
    )

    story.append(bloque_empresa_fecha)
    story.append(Spacer(1, 14))

    detalle_rows = [
        [
            Paragraph("<b>Descripción</b>", normal),
            Paragraph("<b>Valor unitario</b>", normal),
            Paragraph("<b>Cantidad</b>", normal),
            Paragraph("<b>VALOR COP</b>", normal),
        ]
    ]

    for d in dets:
        desc_base = d["descripcion"]

        # Obtener paciente para concatenar correctamente
        paciente_nombre = enc.get("paciente_nombre") or ""

        # Concatenar SOLO para el PDF
        if paciente_nombre:
            desc = f"{desc_base} de {paciente_nombre}"
        else:
            desc = desc_base

        vu = d["valor_unitario"]
        cant = d["cantidad"]
        vt = d["valor_total"]

        detalle_rows.append(
        [
            Paragraph(desc, normal),
            f"{vu:,.0f}".replace(",", "."),
            f"{cant:g}",
            f"{vt:,.0f}".replace(",", "."),
        ]
    )

    # --- RELLENO PARA QUE LA TABLA OCULPE MÁS ESPACIO VERTICAL ---
    min_filas_detalle = 7  # número mínimo de filas de detalle (sin contar la cabecera)
    filas_actuales = len(dets)
    filas_extra = max(0, min_filas_detalle - filas_actuales)

    for _ in range(filas_extra):
        detalle_rows.append(["", "", "", ""])

    detalle_table = Table(
        detalle_rows,
        colWidths=[
            col_desc_mm * mm,
            col_vu_mm * mm,
            col_cant_mm * mm,
            col_total_mm * mm,
        ],
    )
    detalle_table.setStyle(
        TableStyle(
            [
                # Borde exterior completo
                ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
                # Líneas verticales para separar columnas
                ("LINEBEFORE", (1, 0), (1, -1), 0.8, colors.black),
                ("LINEBEFORE", (2, 0), (2, -1), 0.8, colors.black),
                ("LINEBEFORE", (3, 0), (3, -1), 0.8, colors.black),
                # Línea horizontal debajo del encabezado
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),

                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(detalle_table)
    story.append(Spacer(1, 10))

    # ---------- Resumen: Subtotal / IVA / Total ----------
    subtotal = enc["subtotal"]
    iva = enc["iva"]
    total = enc["total"]
    total_letras = enc.get("total_letras") or total_a_letras_pesos(total)

    # El bloque de resumen debe ocupar exactamente el ancho de las
    # columnas Valor unitario + Cantidad + VALOR COP
    resumen_width_mm = right_block_mm
    col_label_mm = 35.0
    col_moneda_mm = 12.0
    col_valor_mm = resumen_width_mm - (col_label_mm + col_moneda_mm)

    tabla_resumen = Table(
        [
            [
                Paragraph("Subtotal", normal),
                Paragraph("COP$", normal),
                Paragraph(
                    f"{subtotal:,.0f}".replace(",", "."), normal
                ),
            ],
            [
                Paragraph("Impuesto (IVA)", normal),
                Paragraph("COP$", normal),
                Paragraph(f"{iva:,.0f}".replace(",", "."), normal),
            ],
            [
                Paragraph("<b>Total</b>", bold),
                Paragraph("<b>COP$</b>", bold),
                Paragraph(
                    f"<b>{total:,.0f}</b>".replace(",", "."),
                    bold,
                ),
            ],
        ],
        colWidths=[
            col_label_mm * mm,
            col_moneda_mm * mm,
            col_valor_mm * mm,
        ],
    )
    tabla_resumen.setStyle(
        TableStyle(
            [
                # Caja solo alrededor de la columna de títulos (Subtotal / IVA / Total)
                ("BOX", (0, 0), (0, 2), 0.8, colors.black),
                ("LINEBELOW", (0, 0), (0, 0), 0.8, colors.black),
                ("LINEBELOW", (0, 1), (0, 1), 0.8, colors.black),
                
                
                # Líneas superiores e inferiores, sin caja completa
                ("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.black),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
                ("LINEBELOW", (0, 1), (-1, 1), 0.5, colors.black),
                ("LINEBELOW", (0, 2), (-1, 2), 0.8, colors.black),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LINEAFTER", (2, 0), (2, 2), 0.8, colors.black),
            ]
        )
    )

    offset_mm = 2.0  # prueba con 2, si quieres un pelín más a la izq pon 3.0

    espacio_izq_mm = detalle_total_width_mm - resumen_width_mm - offset_mm

    tabla_resumen_wrapper = Table(
    [[Spacer(1, 0), tabla_resumen]],
    colWidths=[espacio_izq_mm * mm, resumen_width_mm * mm],
    )

    # y quita el leftPadding que habíamos puesto antes:
    tabla_resumen.leftPadding = 0
    story.append(tabla_resumen_wrapper)
    story.append(Spacer(1, 15))

    # ---------- Forma de pago + SON ----------
    forma_pago = (
        enc.get("forma_pago")
        or cfg_fact.get("forma_pago")
        or "Transferencia bancaria"
    )

    story.append(
        Paragraph(
            f"<b>Forma de Pago:</b> {forma_pago}",
            normal,
        )
    )
    story.append(Spacer(1, 4))
    story.append(
        Paragraph(
            f"<b>SON:</b> {total_letras}",
            normal,
        )
    )
    story.append(Spacer(1, 12))
    
    #Definir forma de pago en el PDF
    
    es_transferencia = "transfer" in (forma_pago or "").lower()

    # ---------- Datos bancarios ----------
    if es_transferencia:
        banco = cfg_fact.get("banco") or "Bancolombia"
        beneficiario = cfg_fact.get("beneficiario") or nombre_prof
        nit_benef = cfg_fact.get("nit") or nit_prof
        num_cuenta = cfg_fact.get("numero_cuenta") or ""

        datos_banco = [
            [Paragraph("Banco:", etiqueta), Paragraph(banco, normal)],
            [Paragraph("Beneficiario:", etiqueta), Paragraph(beneficiario, normal)],
            [Paragraph("NIT:", etiqueta), Paragraph(nit_benef, normal)],
            [Paragraph("No. Cuenta:", etiqueta), Paragraph(num_cuenta, normal)],
        ]
        tabla_banco = Table(
            datos_banco,
            colWidths=[30 * mm, (detalle_total_width_mm - 30) * mm],
        )
        tabla_banco.setStyle(
            TableStyle(
                [
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        story.append(tabla_banco)

    # ==========================================================
    # PÁGINA 2: Declaración + firma
    # ==========================================================
    story.append(PageBreak())

    declaracion_data = [
        [
            Paragraph("<b>Declaración</b>", normal),
            Paragraph("<b>SI</b>", normal),
            Paragraph("<b>NO</b>", normal),
        ],
        [
            Paragraph(
                'A. Manifiesto bajo la gravedad de juramento que en mi depuración del impuesto sobre la Renta usaré la renta exenta del 25% contenida en el numeral 10 del artículo 206 del ET',
                normal,
            ),
            "X",
            "",
        ],
        [
            Paragraph(
                "B. Manifiesto bajo la gravedad de juramento que en mi depuración del impuesto sobre la renta usaré costos y Deducciones",
                normal,
            ),
            "",
            "X",
        ],
    ]

    declaracion_table = Table(
        declaracion_data,
        colWidths=[140 * mm, 15 * mm, 15 * mm],
    )
    declaracion_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.8, colors.black),
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#cde4f8")),  # Declaración azul
                ("BACKGROUND", (1, 0), (2, 0), colors.HexColor("#dddddd")),  # SI/NO gris
                ("ALIGN", (1, 0), (2, 0), "CENTER"),
                ("ALIGN", (1, 1), (2, 2), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(declaracion_table)
    story.append(Spacer(1, 20))

    # ---------- Firma ----------
    firma_cells = [[Paragraph("<b>Firma:</b>", normal)]]
    firma_img = _image_scaled(firma_path, max_width_mm=80, max_height_mm=35)
    if firma_img:
        firma_cells.append([firma_img])
    else:
        firma_cells.append([Paragraph(nombre_prof, normal)])

    firma_table = Table(
        firma_cells,
        colWidths=[140 * mm],
    )
    firma_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(firma_table)

    # ---------- Construir PDF ----------
    doc.build(story)

    if abrir and os.name == "nt":
        try:
            os.startfile(archivo_pdf)
        except Exception:
            pass

    actualizar_ruta_pdf_factura_convenio(factura_id, archivo_pdf)
    return archivo_pdf
