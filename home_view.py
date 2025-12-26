import os
import flet as ft
from datetime import date, datetime, timedelta

from .ui_config import BRAND_PRIMARY, TEXT_MAIN
from .db import (
    DB_PATH,
    contar_pacientes,
    citas_por_mes_anio,
    contar_citas_periodo,
    tasa_asistencia,
    top_5_pacientes_frecuentes,
    listar_citas_con_paciente_rango,
    listar_pacientes,
    resumen_financiero_mensual,
    listar_paquetes_arriendo,
    resumen_paquetes_arriendo,
)
from .fechas import calcular_edad

MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
PERIODOS = ["Año actual", "Último mes", "Última semana"]

MONTH_COLORS = [
    "#dc774a",  # naranja marca
    "#f4a24c",  # naranja claro
    "#a94416",  # naranja oscuro
    "#c1dbd0",  # menta suave
    "#cad8cf",  # verde/gris suave
    "#ecdccc",  # beige
    "#dc7648",  # variante naranja (si la usas)
    "#f4a24c",  # repetir (funciona)
    "#a94416",  # repetir
    "#6b7280",  # gris fuerte (reemplaza blanco tráfico)
    "#374151",  # gris más fuerte
    "#c1dbd0",  # repetir menta
]


# -----------------------------
# Helpers
# -----------------------------
def _row(r, key, default=""):
    """Soporta sqlite3.Row y dict."""
    try:
        if hasattr(r, "keys") and key in r.keys():
            v = r[key]
            return default if v is None else v
    except Exception:
        pass
    try:
        if isinstance(r, dict):
            v = r.get(key, default)
            return default if v is None else v
    except Exception:
        pass
    return default


def _get_logo_path():
    data_dir = os.path.dirname(DB_PATH)
    img_dir = os.path.join(data_dir, "imagenes")
    return os.path.join(img_dir, "logosmall.png")


def _periodo_subtitulo(periodo: str) -> str:
    hoy = date.today()
    if periodo == "Última semana":
        return "Últimos 7 días"
    if periodo == "Último mes":
        return hoy.strftime("%B %Y").capitalize()
    return f"Año {hoy.year} (YTD)"


def _fmt_money(v: float) -> str:
    try:
        return f"${float(v):,.0f}".replace(",", ".")
    except Exception:
        return "$0"


def _fmt_int(v: int) -> str:
    try:
        return f"{int(v)}"
    except Exception:
        return "0"


def _max_y_and_step(vals):
    maxv = max([0] + [int(x) for x in vals])
    if maxv <= 5:
        step = 1
    elif maxv <= 20:
        step = 2
    else:
        step = max(5, maxv // 5)
    maxy = ((maxv // step) + 1) * step if maxv > 0 else 5
    return maxy, step


# -----------------------------
# UI Blocks
# -----------------------------
def _kpi_finanzas_style(
    titulo: str,
    valor_text: ft.Text,
    icono=None,
    icon_color=ft.Colors.ORANGE_700,
    icon_bg=ft.Colors.ORANGE_50,
):
    left = []

    if icono:
        left.append(
            ft.Container(
                width=44,
                height=44,
                border_radius=12,
                bgcolor=icon_bg,
                alignment=ft.alignment.center,
                content=ft.Icon(icono, color=icon_color),
            )
        )

    left.append(
        ft.Column(
            [
                ft.Text(titulo, size=12, color=ft.Colors.GREY_700),
                valor_text,
            ],
            spacing=4,
        )
    )

    return ft.Container(
        padding=12,
        border_radius=14,
        bgcolor=ft.Colors.WHITE,
        border=ft.border.all(1, ft.Colors.GREY_300),
        shadow=ft.BoxShadow(
            blur_radius=12,
            spread_radius=1,
            color=ft.Colors.with_opacity(0.08, ft.Colors.BLACK),
        ),
        content=ft.Row(
            left,
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def _bar_chart_meses(valores, titulo: str):
    valores_int = [int(v) for v in valores]
    maxy, step = _max_y_and_step(valores_int)

    left_labels = []
    y = 0
    while y <= maxy:
        left_labels.append(ft.ChartAxisLabel(value=y, label=ft.Text(str(y), size=11)))
        y += step

    groups = []
    for i, v in enumerate(valores_int):
        groups.append(
            ft.BarChartGroup(
                x=i,
                bar_rods=[
                    ft.BarChartRod(
                        from_y=0,
                        to_y=int(v),
                        width=14,
                        border_radius=6,
                        color=MONTH_COLORS[i % len(MONTH_COLORS)],
                    )
                ],
            )
        )

    return ft.Container(
        bgcolor="#ffffff",
        border_radius=16,
        padding=16,
        shadow=ft.BoxShadow(
            blur_radius=10,
            spread_radius=1,
            color=ft.Colors.with_opacity(0.08, ft.Colors.BLACK),
            offset=ft.Offset(0, 3),
        ),
        content=ft.Column(
            [
                ft.Text(titulo, weight=ft.FontWeight.BOLD),
                ft.BarChart(
                    bar_groups=groups,
                    max_y=float(maxy),
                    left_axis=ft.ChartAxis(labels=left_labels, labels_size=38),
                    bottom_axis=ft.ChartAxis(
                        labels=[
                            ft.ChartAxisLabel(value=i, label=ft.Text(MESES[i], size=11))
                            for i in range(12)
                        ],
                        labels_size=28,
                    ),
                    horizontal_grid_lines=ft.ChartGridLines(interval=float(step)),
                    interactive=True,
                    expand=True,
                    height=240,
                    border=ft.border.all(1, "#eee"),
                ),
            ],
            spacing=12,
        ),
    )


def _card_lista(titulo: str, content: ft.Control):
    return ft.Container(
        bgcolor="#ffffff",
        border_radius=16,
        padding=16,
        shadow=ft.BoxShadow(
            blur_radius=10,
            spread_radius=1,
            color=ft.Colors.with_opacity(0.08, ft.Colors.BLACK),
            offset=ft.Offset(0, 3),
        ),
        content=ft.Column(
            [
                ft.Text(titulo, weight=ft.FontWeight.BOLD),
                content,
            ],
            spacing=12,
        ),
    )


# -----------------------------
# Data builders for widgets
# -----------------------------
def _cumpleanios_hoy():
    hoy = date.today()
    pacientes = listar_pacientes()  # List[sqlite3.Row] o dicts
    out = []

    for p in pacientes:
        fn = str(_row(p, "fecha_nacimiento", "")).strip()
        if not fn:
            continue

        try:
            nac = datetime.strptime(fn, "%d-%m-%Y").date()
        except Exception:
            continue

        if nac.day == hoy.day and nac.month == hoy.month:
            nombre = str(_row(p, "nombre_completo", "")).strip()
            edad = calcular_edad(fn)
            out.append({"nombre": nombre, "edad": edad})

    return out


def _utilidad_por_mes_anio(anio: int):
    vals = []
    for mes in range(1, 13):
        try:
            data = resumen_financiero_mensual(anio, mes)
            utilidad = (data.get("utilidad", {}) or {})
            vals.append(float(utilidad.get("neta_cobrada", 0) or 0))
        except Exception:
            vals.append(0.0)
    return vals


def _utilidad_periodo(periodo: str):
    hoy = date.today()
    anio = hoy.year
    mes_actual = hoy.month

    if periodo == "Última semana":
        data = resumen_financiero_mensual(anio, mes_actual)
        utilidad = (data.get("utilidad", {}) or {})
        return float(utilidad.get("neta_cobrada", 0) or 0), "Mensual (mes actual)"

    if periodo == "Último mes":
        data = resumen_financiero_mensual(anio, mes_actual)
        utilidad = (data.get("utilidad", {}) or {})
        return float(utilidad.get("neta_cobrada", 0) or 0), "Mes actual"

    total = 0.0
    for m in range(1, mes_actual + 1):
        data = resumen_financiero_mensual(anio, m)
        utilidad = (data.get("utilidad", {}) or {})
        total += float(utilidad.get("neta_cobrada", 0) or 0)

    return total, f"Ene–{MESES[mes_actual-1]} {anio}"


def _widget_paquetes():
    info = resumen_paquetes_arriendo(solo_activos=True) or {}

    total = int(info.get("total_citas", 0) or 0)
    usadas = int(info.get("citas_usadas", 0) or 0)
    disp = int(info.get("citas_disponibles", 0) or 0)

    # Empty state
    if total <= 0:
        body = ft.ListView(
            height=85,
            spacing=6,
            auto_scroll=False,
            controls=[
                ft.Row(
                    [
                        ft.Icon(ft.Icons.INFO_OUTLINE, color=ft.Colors.GREY_600, size=18),
                        ft.Text("No hay paquetes de arriendo registrados.", size=12, color=ft.Colors.GREY_700),
                    ],
                    spacing=8,
                )
            ],
        )
        return _card_lista("Paquetes de consultorio", body)

    # Porcentajes
    pct_disp = (disp / total) if total > 0 else 0.0
    pct_usadas = (usadas / total) if total > 0 else 0.0

    # Color dinámico por disponibilidad
    # >=50% verde, 20-49% naranja, <20% rojo
    if pct_disp >= 0.50:
        color_estado = ft.Colors.GREEN_600
        bg_estado = ft.Colors.GREEN_50
        label_estado = "Disponible"
    elif pct_disp >= 0.20:
        color_estado = ft.Colors.ORANGE_700
        bg_estado = ft.Colors.ORANGE_50
        label_estado = "Quedan pocas"
    else:
        color_estado = ft.Colors.RED_600
        bg_estado = ft.Colors.RED_50
        label_estado = "Casi se termina"

    # Chip estado
    pct_txt = int(round(pct_disp * 100))
    
    if pct_disp >= 0.50:
        icon_estado = ft.Icons.CHECK_CIRCLE
    elif pct_disp >= 0.20:
        icon_estado = ft.Icons.WARNING_AMBER_ROUNDED
    else:
        icon_estado = ft.Icons.ERROR_OUTLINE

    chip = ft.Container(
        padding=ft.padding.symmetric(horizontal=10, vertical=5),
        border_radius=999,
        bgcolor=bg_estado,
        content=ft.Row(
            [
                ft.Icon(icon_estado, size=14, color=color_estado),
                ft.Text(
                    f"{label_estado} · {pct_txt}%",
                    size=11,
                    color=color_estado,
                    weight=ft.FontWeight.BOLD,
                ),
            ],
            spacing=6,
        ),
    )
    # Progreso (usadas vs total)
    progress = ft.ProgressBar(
        value=min(1.0, max(0.0, pct_usadas)),
        height=6,
        color=color_estado,
        bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.BLACK),
    )

    # Línea resumen con números resaltados
    resumen = ft.Row(
        [
            ft.Text("Total", size=11, color=ft.Colors.GREY_600),
            ft.Text(str(total), size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_900),
            ft.Text("  •  Usadas", size=11, color=ft.Colors.GREY_600),
            ft.Text(str(usadas), size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_900),
            ft.Text("  •  Disponibles", size=11, color=ft.Colors.GREY_600),
            ft.Text(str(disp), size=12, weight=ft.FontWeight.BOLD, color=color_estado),
        ],
        wrap=True,
    )

    body = ft.ListView(
        height=85,
        spacing=6,
        auto_scroll=False,
        controls=[
            ft.Row(
                [
                    ft.Text("Paquetes de arriendo", size=11, color=ft.Colors.GREY_700),
                    ft.Container(expand=True),
                    chip,
                ],
            ),
            resumen,
            progress,
        ],
    )

    return _card_lista("Paquetes de consultorio", body)

# -----------------------------
# Helper altura constants
# -----------------------------
ALTURA_PROX = 300
ALTURA_WIDGET = 140

# -----------------------------
# Main builder
# -----------------------------
def build_home_view(page: ft.Page):

    dd_periodo = ft.Dropdown(
        value="Año actual",
        options=[ft.dropdown.Option(p) for p in PERIODOS],
        width=220,
    )

    kpis_row = ft.ResponsiveRow(run_spacing=12, spacing=12)
    charts_row = ft.ResponsiveRow(run_spacing=12, spacing=12)

    # Este NO será ResponsiveRow; se arma con Row + Column para que quede como tu imagen "BIEN"
    widgets_section_holder = ft.Container()
    
    # -------------------------
    #Funciones PRO para Widgets
    # -------------------------
    
    def _fmt_fecha_humana(dt: datetime) -> str:
        dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        return f"{dias[dt.weekday()]} {dt.day:02d} {meses[dt.month-1]} {dt.year}"

    def _parse_fecha_hora(fh: str):
        """
        Parser tolerante para fechas de citas.
        La BD actualmente usa 'YYYY-MM-DD HH:MM', pero se aceptan
        variantes con segundos o formato ISO por robustez.
        """
        fh = (fh or "").strip()
        # formatos típicos que puede tener tu BD
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(fh, fmt)
            except Exception:
                pass
        return None

    def _chip_canal(canal: str):
        c = (canal or "").strip().lower()
        if "virtual" in c:
            color = ft.Colors.BLUE_700
            bg = ft.Colors.BLUE_50
            icon = ft.Icons.VIDEOCAM_OUTLINED
            text = "Virtual"
        else:
            color = ft.Colors.GREEN_700
            bg = ft.Colors.GREEN_50
            icon = ft.Icons.PERSON_PIN_CIRCLE_OUTLINED
            text = "Presencial"

        return ft.Container(
            padding=ft.padding.symmetric(horizontal=10, vertical=5),
            border_radius=999,
            bgcolor=bg,
            content=ft.Row(
                [
                    ft.Icon(icon, size=14, color=color),
                    ft.Text(text, size=11, color=color, weight=ft.FontWeight.BOLD),
                ],
                spacing=6,
            ),
        )

    def _chip_cuando(dt: datetime):
        if not dt:
            return None
        hoy = datetime.now().date()
        d = dt.date()
        delta = (d - hoy).days

        if delta == 0:
            label = "Hoy"
            color = ft.Colors.PURPLE_700
            bg = ft.Colors.PURPLE_50
        elif delta == 1:
            label = "Mañana"
            color = ft.Colors.PURPLE_700
            bg = ft.Colors.PURPLE_50
        else:
            label = f"En {delta} días"
            color = ft.Colors.GREY_700
            bg = ft.Colors.GREY_100

        return ft.Container(
            padding=ft.padding.symmetric(horizontal=10, vertical=5),
            border_radius=999,
            bgcolor=bg,
            content=ft.Text(label, size=11, color=color, weight=ft.FontWeight.BOLD),
        )
        
        #######################################################
        #   RENDER FUNCTION
        #######################################################

    def _render():
        periodo = dd_periodo.value or "Año actual"
        subt_periodo = _periodo_subtitulo(periodo)

        hoy = date.today()
        anio = hoy.year

        # ---------------- KPIs ----------------
        total_pacientes = contar_pacientes()
        total_citas = contar_citas_periodo(periodo)
        utilidad_val, utilidad_sub = _utilidad_periodo(periodo)

        ta = tasa_asistencia(periodo)
        tasa_pct = int(ta.get("tasa_pct", 0) or 0)

        kpi_pacientes = ft.Text(_fmt_int(total_pacientes), size=22, weight=ft.FontWeight.BOLD, color=TEXT_MAIN)
        kpi_citas = ft.Text(_fmt_int(total_citas), size=22, weight=ft.FontWeight.BOLD, color=TEXT_MAIN)
        kpi_utilidad = ft.Text(_fmt_money(utilidad_val), size=22, weight=ft.FontWeight.BOLD, color=TEXT_MAIN)
        kpi_asistencia = ft.Text(f"{tasa_pct}%", size=22, weight=ft.FontWeight.BOLD, color=TEXT_MAIN)

        kpis_row.controls = [
            ft.Container(
                col={"sm": 12, "md": 6, "lg": 3},
                content=_kpi_finanzas_style("Pacientes registrados", kpi_pacientes, icono=ft.Icons.PEOPLE),
            ),
            ft.Container(
                col={"sm": 12, "md": 6, "lg": 3},
                content=_kpi_finanzas_style("Citas en el período", kpi_citas, icono=ft.Icons.EVENT_AVAILABLE),
            ),
            ft.Container(
                col={"sm": 12, "md": 6, "lg": 3},
                content=_kpi_finanzas_style(
                    "Utilidad neta",
                    kpi_utilidad,
                    icono=ft.Icons.SAVINGS,
                    icon_color=ft.Colors.GREEN_700,
                    icon_bg=ft.Colors.GREEN_50,
                ),
            ),
            ft.Container(
                col={"sm": 12, "md": 6, "lg": 3},
                content=_kpi_finanzas_style(
                    "Tasa de asistencia",
                    kpi_asistencia,
                    icono=ft.Icons.INSIGHTS,
                    icon_color=ft.Colors.BLUE_700,
                    icon_bg=ft.Colors.BLUE_50,
                ),
            ),
        ]

        # ---------------- Charts ----------------
        citas_mes = citas_por_mes_anio(anio)
        utilidad_mes = _utilidad_por_mes_anio(anio)

        charts_row.controls = [
            ft.Container(col={"sm": 12, "lg": 6}, content=_bar_chart_meses(citas_mes, "Citas por mes")),
            ft.Container(col={"sm": 12, "lg": 6}, content=_bar_chart_meses([int(x) for x in utilidad_mes], "Utilidad neta por mes")),
        ]

        # ---------------- Widgets ----------------
        # Próximas citas (7 días): fijo + scroll + máximo 7
        fi = hoy.strftime("%Y-%m-%d 00:00")
        ff = (hoy + timedelta(days=7)).strftime("%Y-%m-%d 23:59")
        try:
            prox = listar_citas_con_paciente_rango(fi, ff) or []
        except Exception:
            prox = []

        prox_list = ft.ListView(
            spacing=10,
            height=ALTURA_PROX,
            auto_scroll=False,
        )

        if not prox:
            prox_list.controls.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.EVENT_BUSY_OUTLINED, color=ft.Colors.GREY_600, size=18),
                        ft.Text("No hay citas programadas para los próximos 7 días.", color=ft.Colors.GREY_700),
                    ],
                    spacing=8,
                )
            )
        else:
            for r in prox[:7]:
                nombre = str(_row(r, "nombre_completo", "")).strip()
                canal = str(_row(r, "canal", "")).strip()
                fh = str(_row(r, "fecha_hora", "")).strip()

                dt = _parse_fecha_hora(fh)
                if dt:
                    titulo_fecha = f"{_fmt_fecha_humana(dt)} · {dt.strftime('%H:%M')}"
                else:
                    titulo_fecha = fh  # fallback

                prox_list.controls.append(
                    ft.Container(
                        padding=12,
                        border_radius=14,
                        bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.BLACK),
                        content=ft.Column(
                            [
                                # Header: Fecha + chips
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.CALENDAR_MONTH, color=BRAND_PRIMARY),
                                        ft.Text(titulo_fecha, weight=ft.FontWeight.BOLD),
                                        ft.Container(expand=True),
                                        _chip_cuando(dt) if dt else ft.Container(),
                                    ],
                                    spacing=10,
                                ),

                                # Paciente + canal (chip)
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.PERSON_OUTLINE, size=18, color=ft.Colors.GREY_700),
                                        ft.Text(nombre, size=12, color=ft.Colors.GREY_900, weight=ft.FontWeight.W_600),
                                        ft.Container(expand=True),
                                        _chip_canal(canal),
                                    ],
                                    spacing=10,
                                ),
                            ],
                            spacing=8,
                        ),
                    )
                )

        # Top 5 frecuentes (fijo + scroll)
        top5 = top_5_pacientes_frecuentes(periodo) or []
        top_list = ft.ListView(spacing=8, height=140, auto_scroll=False)
        if not top5:
            top_list.controls.append(ft.Text("Aún no hay datos suficientes en este período.", color="#666"))
        else:
            for t in top5:
                top_list.controls.append(
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.STAR, color=ft.Colors.AMBER_600),
                            ft.Text(
                                str(_row(t, "nombre_completo", "")),
                                expand=True,
                                no_wrap=True,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(str(int(_row(t, "cantidad", 0) or 0)), weight=ft.FontWeight.BOLD),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    )
                )

        # Cumpleaños (fijo + scroll)
        cumple = _cumpleanios_hoy()
        cumple_list = ft.ListView(spacing=8, height=140, auto_scroll=False)
        if not cumple:
            cumple_list.controls.append(
                ft.Container(
                    alignment=ft.alignment.center,
                    padding=10,
                    content=ft.Text(
                        "Hoy no hay cumpleaños registrados 🎉",
                        color=ft.Colors.GREY_700,
                        text_align=ft.TextAlign.CENTER,
                    ),
                )
            )
        else:
            for c in cumple:
                cumple_list.controls.append(
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.CAKE, color=ft.Colors.PINK_400),
                            ft.Text(
                                c["nombre"],
                                expand=True,
                                no_wrap=True,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(f"{c['edad']} años", weight=ft.FontWeight.BOLD),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    )
                )

        # --- LAYOUT "BIEN": izquierda grande + derecha (Top5 y Cumple en fila) + Paquetes abajo ---
        # --- LAYOUT alineado con los charts (2 columnas lg=6) ---
        widgets_section = ft.ResponsiveRow(
            spacing=12,
            run_spacing=12,
            controls=[
                # Columna izquierda (igual ancho que chart "Citas por mes")
                ft.Container(
                    col={"sm": 12, "lg": 6},
                    content=_card_lista("Próximas citas (7 días)", prox_list),
                ),

                # Columna derecha (igual ancho que chart "Utilidad neta por mes")
                ft.Container(
                    col={"sm": 12, "lg": 6},
                    content=ft.Column(
                        spacing=12,
                        controls=[
                            # Top5 y Cumpleños en la misma fila cuando hay ancho,
                            # y se apilan cuando la pantalla es pequeña.
                            ft.ResponsiveRow(
                                spacing=12,
                                run_spacing=12,
                                controls=[
                                    ft.Container(
                                        col={"sm": 12, "md": 6},
                                        content=_card_lista("Top 5 pacientes frecuentes", top_list),
                                    ),
                                    ft.Container(
                                        col={"sm": 12, "md": 6},
                                        content=_card_lista("Cumpleaños de hoy", cumple_list),
                                    ),
                                ],
                            ),
                            # Paquetes abajo ocupando todo el ancho de la columna derecha
                            _widget_paquetes(),
                        ],
                    ),
                ),
            ],
        )

        widgets_section_holder.content = widgets_section
        page.update()

    def _on_periodo_change(e):
        _render()

    dd_periodo.on_change = _on_periodo_change

    logo_path = _get_logo_path()
    _render()

    return ft.Container(
        expand=True,
        padding=16,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Image(src=logo_path, height=110, fit=ft.ImageFit.CONTAIN),
                        ft.Container(expand=True),
                        ft.Column(
                            [
                                ft.Text("Periodo de tiempo", size=12, color="#666"),
                                dd_periodo,
                            ],
                            spacing=6,
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(),
                kpis_row,
                ft.Divider(height=12, color="transparent"),
                charts_row,
                ft.Divider(height=12, color="transparent"),
                widgets_section_holder,
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        ),
    )
