import flet as ft
from datetime import date, timedelta

from db import obtener_configuracion_profesional, obtener_horarios_atencion


DIAS_SEMANA = [
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes",
    "Sábado",
    "Domingo",
]

MESES = [
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]


def build_agenda_view(page: ft.Page) -> ft.Control:
    """Vista de agenda semanal con mini calendario."""

    hoy = date.today()

    # estado
    fecha_seleccionada = {"value": hoy}
    semana_lunes = {"value": hoy - timedelta(days=hoy.weekday())}
    mes_actual = {"value": fecha_seleccionada["value"].replace(day=1)}

    calendario_semanal_col = ft.Column(expand=True, spacing=0, scroll=ft.ScrollMode.AUTO)
    mini_calendario_col = ft.Column(spacing=5)
    texto_semana = ft.Text(weight="bold")
    panel_expandido = {"value": True}
    slot_minutes = {"value": 60}

    # Config y horarios
    cfg = obtener_configuracion_profesional()
    horarios = obtener_horarios_atencion()
    horarios_map = {h["dia"]: h for h in horarios}

    def hhmm_to_hour(hhmm: str) -> int:
        try:
            h, m = map(int, hhmm.split(":"))
            return h
        except Exception:
            return 0

    horas_inicio = []
    horas_fin = []
    for h in horarios:
        if h["habilitado"] and h["hora_inicio"] and h["hora_fin"]:
            horas_inicio.append(hhmm_to_hour(h["hora_inicio"]))
            horas_fin.append(hhmm_to_hour(h["hora_fin"]))

    if horas_inicio and horas_fin:
        START_HOUR = min(horas_inicio)
        END_HOUR = max(horas_fin)
    else:
        START_HOUR = 7
        END_HOUR = 21

    year_min = hoy.year - 4
    year_max = hoy.year + 1

    dd_mes = ft.Dropdown(
        width=140,
        dense=True,
        border_width=0,
        text_style=ft.TextStyle(size=13, weight=ft.FontWeight.BOLD),
        text_align=ft.TextAlign.CENTER,
        options=[ft.dropdown.Option(m) for m in MESES],
    )
    dd_year = ft.Dropdown(
        width=100,
        dense=True,
        border_width=0,
        text_style=ft.TextStyle(size=14, weight=ft.FontWeight.BOLD),
        text_align=ft.TextAlign.CENTER,
        options=[ft.dropdown.Option(str(y)) for y in range(year_min, year_max + 1)],
    )

    def obtener_dias_semana(lunes: date):
        return [lunes + timedelta(days=i) for i in range(7)]

    def minutos_desde_medianoche(hhmm: str) -> int:
        h, m = map(int, hhmm.split(":"))
        return h * 60 + m

    def click_slot(dia: date, minuto: int):
        h = minuto // 60
        mm = minuto % 60
        page.snack_bar = ft.SnackBar(
            content=ft.Text(f"Click en {dia.strftime('%Y-%m-%d')} {h:02d}:{mm:02d}"),
            bgcolor=ft.Colors.BLUE_200,
        )
        page.snack_bar.open = True
        page.update()

    def construir_celda(d: date, m: int) -> ft.Container:
        info = horarios_map.get(d.weekday())
        bgcolor = ft.Colors.GREY_200

        if info:
            if not info["habilitado"]:
                bgcolor = ft.Colors.GREY_300
            else:
                inicio_min = minutos_desde_medianoche(info["hora_inicio"])
                fin_min = minutos_desde_medianoche(info["hora_fin"])
                if m < inicio_min or m >= fin_min:
                    bgcolor = ft.Colors.GREY_300
        else:
            bgcolor = ft.Colors.GREY_300

        return ft.Container(
            width=150,
            height=50,
            bgcolor=bgcolor,
            border=ft.border.all(0.5, ft.Colors.GREY_400),
            alignment=ft.alignment.center,
            on_click=lambda e, dia=d, minuto=m: click_slot(dia, minuto),
        )

    def dibujar_calendario_semanal():
        dias = obtener_dias_semana(semana_lunes["value"])
        intervalo = slot_minutes["value"]
        start_min = START_HOUR * 60
        end_min = END_HOUR * 60
        minutos = list(range(start_min, end_min + 1, intervalo))

        filas = []

        inicio = dias[0]
        fin = dias[-1]
        texto_semana.value = (
            f"{DIAS_SEMANA[inicio.weekday()]} {inicio.day:02d}/{inicio.month:02d}/{inicio.year} "
            f"- {DIAS_SEMANA[fin.weekday()]} {fin.day:02d}/{fin.month:02d}/{fin.year}"
        )

        # encabezado de días
        encabezado_cells = [ft.Container(width=70)]
        for d in dias:
            encabezado_cells.append(
                ft.Container(
                    content=ft.Text(
                        f"{DIAS_SEMANA[d.weekday()]} {d.day:02d}/{d.month:02d}",
                        weight="bold",
                    ),
                    alignment=ft.alignment.center,
                    width=150,
                    padding=5,
                )
            )
        encabezado_cells.append(ft.Container(width=10))
        filas.append(ft.Row(encabezado_cells))

        # filas de horas
        for m in minutos:
            h = m // 60
            mm = m % 60
            etiqueta_hora = f"{h:02d}:{mm:02d}"

            cells = [
                ft.Container(
                    width=80,
                    content=ft.Text(etiqueta_hora),
                    alignment=ft.alignment.center_right,
                    padding=5,
                )
            ]
            for d in dias:
                cells.append(construir_celda(d, m))
            cells.append(ft.Container(width=10))
            filas.append(ft.Row(cells))

        calendario_semanal_col.controls = filas
        page.update()

    def dibujar_mini_calendario():
        m = mes_actual["value"]
        year = m.year
        month = m.month

        dd_mes.value = MESES[month - 1]
        dd_year.value = str(year)

        fila_dias = ft.Row(
            [ft.Text(x, size=11) for x in ["L", "M", "X", "J", "V", "S", "D"]],
            alignment=ft.MainAxisAlignment.SPACE_AROUND,
        )

        primer_dia_mes = date(year, month, 1)
        offset = primer_dia_mes.weekday()

        if month == 12:
            siguiente_mes = date(year + 1, 1, 1)
        else:
            siguiente_mes = date(year, month + 1, 1)
        dias_en_mes = (siguiente_mes - timedelta(days=1)).day

        celdas = []
        for _ in range(offset):
            celdas.append(ft.Container(width=28, height=24))

        for dia_num in range(1, dias_en_mes + 1):
            fecha_dia = date(year, month, dia_num)
            es_hoy = fecha_dia == hoy
            es_sel = fecha_dia == fecha_seleccionada["value"]

            bgcolor = None
            border = None
            text_color = None
            weight = None

            if es_sel:
                bgcolor = ft.Colors.DEEP_PURPLE_200
                text_color = ft.Colors.WHITE
                weight = "bold"

            if es_hoy:
                border = ft.border.all(1, ft.Colors.BLACK87)

            celdas.append(
                ft.Container(
                    width=28,
                    height=24,
                    alignment=ft.alignment.center,
                    bgcolor=bgcolor,
                    border=border,
                    border_radius=20,
                    content=ft.Text(
                        str(dia_num),
                        size=11,
                        color=text_color,
                        weight=weight,
                    ),
                    on_click=lambda e, f=fecha_dia: seleccionar_dia(f),
                )
            )

        filas_semanas = []
        for i in range(0, len(celdas), 7):
            fila = celdas[i : i + 7]
            while len(fila) < 7:
                fila.append(ft.Container(width=28, height=24))
            filas_semanas.append(
                ft.Row(
                    fila,
                    alignment=ft.MainAxisAlignment.SPACE_AROUND,
                    spacing=0,
                )
            )

        mini_calendario_col.controls = [fila_dias, *filas_semanas]
        page.update()

    def seleccionar_dia(fecha: date):
        fecha_seleccionada["value"] = fecha
        semana_lunes["value"] = fecha - timedelta(days=fecha.weekday())
        mes_actual["value"] = fecha.replace(day=1)
        dibujar_calendario_semanal()
        dibujar_mini_calendario()

    def cambiar_mes(e):
        value = dd_mes.value
        if not value:
            return
        m = mes_actual["value"]
        nuevo_mes = MESES.index(value) + 1
        mes_actual["value"] = m.replace(month=nuevo_mes, day=1)
        dibujar_mini_calendario()

    def cambiar_year(e):
        value = dd_year.value
        if not value:
            return
        m = mes_actual["value"]
        nuevo_year = int(value)
        mes_actual["value"] = m.replace(year=nuevo_year, day=1)
        dibujar_mini_calendario()

    dd_mes.on_change = cambiar_mes
    dd_year.on_change = cambiar_year

    def mes_anterior(e):
        m = mes_actual["value"]
        if m.month == 1:
            mes_actual["value"] = m.replace(year=m.year - 1, month=12, day=1)
        else:
            mes_actual["value"] = m.replace(month=m.month - 1, day=1)
        dibujar_mini_calendario()

    def mes_siguiente(e):
        m = mes_actual["value"]
        if m.month == 12:
            mes_actual["value"] = m.replace(year=m.year + 1, month=1, day=1)
        else:
            mes_actual["value"] = m.replace(month=m.month + 1, day=1)
        dibujar_mini_calendario()

    btn_mes_anterior = ft.IconButton(
        icon=ft.Icons.CHEVRON_LEFT,
        icon_size=16,
        tooltip="Mes anterior",
        on_click=mes_anterior,
    )
    btn_mes_siguiente = ft.IconButton(
        icon=ft.Icons.CHEVRON_RIGHT,
        icon_size=16,
        tooltip="Mes siguiente",
        on_click=mes_siguiente,
    )

    def semana_anterior(e):
        semana_lunes["value"] -= timedelta(days=7)
        fecha_seleccionada["value"] = semana_lunes["value"]
        mes_actual["value"] = fecha_seleccionada["value"].replace(day=1)
        dibujar_calendario_semanal()
        dibujar_mini_calendario()

    def semana_siguiente(e):
        semana_lunes["value"] += timedelta(days=7)
        fecha_seleccionada["value"] = semana_lunes["value"]
        mes_actual["value"] = fecha_seleccionada["value"].replace(day=1)
        dibujar_calendario_semanal()
        dibujar_mini_calendario()

    def semana_hoy(e):
        fecha_seleccionada["value"] = hoy
        semana_lunes["value"] = hoy - timedelta(days=hoy.weekday())
        mes_actual["value"] = fecha_seleccionada["value"].replace(day=1)
        dibujar_calendario_semanal()
        dibujar_mini_calendario()

    def cambiar_intervalo(minutos: int):
        slot_minutes["value"] = minutos
        dibujar_calendario_semanal()

    intervalo_menu = ft.PopupMenuButton(
        icon=ft.Icons.ACCESS_TIME,
        tooltip="Intervalo de agenda",
        items=[
            ft.PopupMenuItem(text="5 minutos", on_click=lambda e, m=5: cambiar_intervalo(m)),
            ft.PopupMenuItem(text="10 minutos", on_click=lambda e, m=10: cambiar_intervalo(m)),
            ft.PopupMenuItem(text="15 minutos", on_click=lambda e, m=15: cambiar_intervalo(m)),
            ft.PopupMenuItem(text="20 minutos", on_click=lambda e, m=20: cambiar_intervalo(m)),
            ft.PopupMenuItem(text="30 minutos", on_click=lambda e, m=30: cambiar_intervalo(m)),
            ft.PopupMenuItem(text="45 minutos", on_click=lambda e, m=45: cambiar_intervalo(m)),
            ft.PopupMenuItem(text="60 minutos", on_click=lambda e, m=60: cambiar_intervalo(m)),
        ],
    )

    barra_controles = ft.Row(
        [
            ft.IconButton(
                icon=ft.Icons.CHEVRON_LEFT,
                on_click=semana_anterior,
                tooltip="Semana anterior",
            ),
            ft.IconButton(
                icon=ft.Icons.CHEVRON_RIGHT,
                on_click=semana_siguiente,
                tooltip="Semana siguiente",
            ),
            intervalo_menu,
            ft.TextButton("Hoy", on_click=semana_hoy),
            ft.Text("Semana:", weight="bold"),
            texto_semana,
        ],
        alignment=ft.MainAxisAlignment.START,
        spacing=5,
    )

    toggle_btn = ft.IconButton(
        icon=ft.Icons.KEYBOARD_DOUBLE_ARROW_LEFT,
        icon_size=16,
        tooltip="Colapsar panel",
        style=ft.ButtonStyle(shape=ft.CircleBorder(), padding=10),
    )

    panel_izquierdo = ft.Container(
        padding=10,
        bgcolor=ft.Colors.WHITE,
        border_radius=8,
        shadow=ft.BoxShadow(
            blur_radius=8,
            spread_radius=1,
            color=ft.Colors.BLACK12,
            offset=ft.Offset(0, 2),
        ),
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Container(expand=True),
                        toggle_btn,
                    ],
                    alignment=ft.MainAxisAlignment.END,
                ),
                ft.Row(
                    [
                        ft.Container(expand=True),
                        dd_year,
                        ft.Container(expand=True),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        btn_mes_anterior,
                        dd_mes,
                        btn_mes_siguiente,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                mini_calendario_col,
            ],
            spacing=10,
        ),
        width=260,
    )

    def toggle_panel(e):
        panel_expandido["value"] = not panel_expandido["value"]

        if panel_expandido["value"]:
            panel_izquierdo.width = 260
            mini_calendario_col.visible = True
            btn_mes_anterior.visible = True
            btn_mes_siguiente.visible = True
            dd_mes.visible = True
            dd_year.visible = True
            toggle_btn.icon = ft.Icons.KEYBOARD_DOUBLE_ARROW_LEFT
            toggle_btn.tooltip = "Colapsar panel"
        else:
            panel_izquierdo.width = 70
            mini_calendario_col.visible = False
            btn_mes_anterior.visible = False
            btn_mes_siguiente.visible = False
            dd_mes.visible = False
            dd_year.visible = False
            toggle_btn.icon = ft.Icons.KEYBOARD_DOUBLE_ARROW_RIGHT
            toggle_btn.tooltip = "Expandir panel"

        page.update()

    toggle_btn.on_click = toggle_panel

    dibujar_calendario_semanal()
    dibujar_mini_calendario()

    columna_derecha = ft.Column(
        [
            barra_controles,
            ft.Divider(),
            calendario_semanal_col,
        ],
        expand=True,
    )

    return ft.Row(
        [
            panel_izquierdo,
            columna_derecha,
        ],
        expand=True,
    )
