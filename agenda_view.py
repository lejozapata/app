import flet as ft
from datetime import datetime, timedelta, date
from db import listar_citas_rango   # lo usaremos después


# ---------------------------
# Días de la semana para el calendario
# ---------------------------

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
# ---------------------------
# Vista de Agenda / Calendario
# ---------------------------

def build_agenda_view(page: ft.Page):

    # ========= Estado inicial =========
    hoy = date.today()

    fecha_seleccionada = {"value": hoy}
    semana_lunes = {"value": hoy - timedelta(days=hoy.weekday())}
    mes_actual = {"value": fecha_seleccionada["value"].replace(day=1)}

    # Contenedores a actualizar
    calendario_semanal_col = ft.Column(expand=True)
    mini_calendario_col = ft.Column(spacing=5)
    texto_semana = ft.Text(weight="bold")

    # Estado del panel izquierdo (expandido / colapsado)
    panel_expandido = {"value": True}

    # ---------- Helpers de fechas ----------

    def obtener_dias_semana(lunes: date):
        return [lunes + timedelta(days=i) for i in range(7)]

    # ---------- Click en un slot horario (por ahora solo info) ----------

    def click_slot(dia: date, hora: int):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(
                f"Click en {dia.strftime('%Y-%m-%d')} {hora:02d}:00"
            ),
            bgcolor=ft.Colors.BLUE_200,
        )
        page.snack_bar.open = True
        page.update()

    # ---------- Renderizar agenda semanal (derecha) ----------

    def dibujar_calendario_semanal():
        dias = obtener_dias_semana(semana_lunes["value"])
        horas = list(range(8, 21))
        filas = []

        inicio = dias[0]
        fin = dias[-1]
        texto_semana.value = (
            f"{DIAS_SEMANA[inicio.weekday()]} {inicio.day:02d}/{inicio.month:02d}/{inicio.year} "
            f"- {DIAS_SEMANA[fin.weekday()]} {fin.day:02d}/{fin.month:02d}/{fin.year}"
        )

        # Encabezado de días
        encabezado = ft.Row(
            [
                ft.Container(width=70),  # columna de horas
                *[
                    ft.Container(
                        content=ft.Text(
                            f"{DIAS_SEMANA[d.weekday()]} {d.day:02d}/{d.month:02d}",
                            weight="bold",
                        ),
                        alignment=ft.alignment.center,
                        width=130,
                        padding=5,
                    )
                    for d in dias
                ],
                ft.Container(width=10),
            ]
        )
        filas.append(encabezado)

        # Cuerpo horario
        for h in horas:
            fila = ft.Row(
                [
                    ft.Container(
                        width=70,
                        content=ft.Text(f"{h:02d}:00"),
                        alignment=ft.alignment.center_right,
                        padding=5,
                    ),
                    *[
                        ft.Container(
                            width=130,
                            height=50,
                            bgcolor=ft.Colors.GREY_200,
                            border=ft.border.all(0.5, ft.Colors.GREY_400),
                            alignment=ft.alignment.center,
                            on_click=lambda e, dia=d, hora=h: click_slot(dia, hora),
                        )
                        for d in dias
                    ],
                    ft.Container(width=10),
                ]
            )
            filas.append(fila)

        calendario_semanal_col.controls = filas
        page.update()

    # ---------- Renderizar mini calendario mensual (izquierda) ----------

    def dibujar_mini_calendario():
        m = mes_actual["value"]
        year = m.year
        month = m.month

        # Cabecera mes / año
        encabezado = ft.Row(
            [
                ft.Text(f"{MESES[month-1]} {year}", weight="bold"),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        )

        fila_dias = ft.Row(
            [
                ft.Text("L", size=11),
                ft.Text("M", size=11),
                ft.Text("X", size=11),
                ft.Text("J", size=11),
                ft.Text("V", size=11),
                ft.Text("S", size=11),
                ft.Text("D", size=11),
            ],
            alignment=ft.MainAxisAlignment.SPACE_AROUND,
        )

        primer_dia_mes = date(year, month, 1)
        offset = primer_dia_mes.weekday()  # 0 = lunes
        if month == 12:
            siguiente_mes = date(year + 1, 1, 1)
        else:
            siguiente_mes = date(year, month + 1, 1)
        dias_en_mes = (siguiente_mes - timedelta(days=1)).day

        celdas = []

        # Huecos antes del primer día
        for _ in range(offset):
            celdas.append(ft.Container(width=28, height=24))

        # Días del mes
        for dia_num in range(1, dias_en_mes + 1):
            fecha_dia = date(year, month, dia_num)
            es_hoy = (fecha_dia == hoy)
            es_sel = (fecha_dia == fecha_seleccionada["value"])

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
            filas_semanas.append(
                ft.Row(
                    celdas[i:i + 7],
                    alignment=ft.MainAxisAlignment.SPACE_AROUND,
                    spacing=0,
                )
            )

        mini_calendario_col.controls = [encabezado, fila_dias, *filas_semanas]
        page.update()

    # ---------- Sync: elegir día en mini calendario ----------

    def seleccionar_dia(fecha: date):
        fecha_seleccionada["value"] = fecha
        semana_lunes["value"] = fecha - timedelta(days=fecha.weekday())
        mes_actual["value"] = fecha.replace(day=1)
        dibujar_calendario_semanal()
        dibujar_mini_calendario()

    # ---------- Navegación de mes ----------

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

         # Botones de navegación de mes y colapso
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

    toggle_btn = ft.IconButton(
        icon=ft.Icons.KEYBOARD_DOUBLE_ARROW_LEFT,
        icon_size=16,
        tooltip="Colapsar panel",
    )

    # ---------- Navegación de semana ----------

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

    # ---------- Botón de colapso dentro del panel izquierdo ----------

    toggle_btn = ft.IconButton(
        icon=ft.Icons.KEYBOARD_DOUBLE_ARROW_LEFT,
        icon_size=16,
        tooltip="Colapsar panel",
    )

    def toggle_panel(e):
        panel_expandido["value"] = not panel_expandido["value"]

        if panel_expandido["value"]:
            # EXPANDIDO: ancho normal, calendario visible, botones de mes visibles
            panel_izquierdo.width = 260
            mini_calendario_col.visible = True
            btn_mes_anterior.visible = True
            btn_mes_siguiente.visible = True
            toggle_btn.icon = ft.Icons.KEYBOARD_DOUBLE_ARROW_LEFT
            toggle_btn.tooltip = "Colapsar panel"
        else:
            # COLAPSADO: panel angosto, solo botón de toggle
            panel_izquierdo.width = 70  # si quieres más o menos, ajusta aquí
            mini_calendario_col.visible = False
            btn_mes_anterior.visible = False
            btn_mes_siguiente.visible = False
            toggle_btn.icon = ft.Icons.KEYBOARD_DOUBLE_ARROW_RIGHT
            toggle_btn.tooltip = "Expandir panel"

        page.update()

    toggle_btn.on_click = toggle_panel

    # ---------- Panel izquierdo (tarjeta blanca con sombra) ----------

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
                    [btn_mes_anterior, btn_mes_siguiente, toggle_btn],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                mini_calendario_col,
            ],
            spacing=10,
        ),
        width=260,
    )


    # ---------- Barra superior de la agenda semanal ----------

    barra_controles = ft.Row(
        [
            ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, on_click=semana_anterior),
            ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, on_click=semana_siguiente),
            ft.TextButton("Hoy", on_click=semana_hoy),
            ft.Text("Semana:", weight="bold"),
            texto_semana,
        ],
        alignment=ft.MainAxisAlignment.START,
        spacing=5,
    )

    # ---------- Render inicial ----------

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
