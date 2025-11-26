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
    hoy = datetime.now().date()

    # Día seleccionado (se marca en el mini calendario)
    fecha_seleccionada_ref: ft.Ref[date] = ft.Ref[date]()
    fecha_seleccionada_ref.current = hoy

    # Lunes de la semana visible en la grilla
    semana_lunes_ref: ft.Ref[date] = ft.Ref[date]()
    semana_lunes_ref.current = hoy - timedelta(days=hoy.weekday())

    # Primer día del mes visible en el mini calendario
    mes_actual_ref: ft.Ref[date] = ft.Ref[date]()
    mes_actual_ref.current = fecha_seleccionada_ref.current.replace(day=1)

    # Contenedores a actualizar
    calendario_semanal_col = ft.Column(expand=True)
    mini_calendario_col = ft.Column()

        # Panel izquierdo (mini calendario) como contenedor colapsable
    panel_visible = {"value": True}  # usamos dict para que sea mutable en closures

    panel_izquierdo = ft.Container(
        content=mini_calendario_col,
        width=220,
        padding=10,
        visible=True,
    )

    # Botón para colapsar / expandir panel izquierdo
    toggle_btn = ft.IconButton(icon=ft.Icons.KEYBOARD_DOUBLE_ARROW_LEFT)

    # ---------- Colapsar calendario ----------

    def toggle_panel(e):
        panel_visible["value"] = not panel_visible["value"]
        panel_izquierdo.visible = panel_visible["value"]
        toggle_btn.icon = (
            ft.Icons.KEYBOARD_DOUBLE_ARROW_LEFT if panel_visible["value"] else ft.Icons.KEYBOARD_DOUBLE_ARROW_RIGHT
        )
        page.update()

    toggle_btn.on_click = toggle_panel


    # Texto del rango de semana
    texto_semana = ft.Text(weight="bold")

    # ---------- Helpers de fechas ----------

    def obtener_dias_semana(lunes: date):
        return [lunes + timedelta(days=i) for i in range(7)]

    # ---------- Agenda semanal (derecha) ----------

    def dibujar_calendario_semanal():
        dias = obtener_dias_semana(semana_lunes_ref.current)
        horas = list(range(8, 21))
        filas = []

        inicio = dias[0]
        fin = dias[-1]
        texto_semana.value = (
            f"{DIAS_SEMANA[inicio.weekday()]} {inicio.day:02d}/{inicio.month:02d}/{inicio.year} "
            f"- {DIAS_SEMANA[fin.weekday()]} {fin.day:02d}/{fin.month:02d}/{fin.year}"
        )

        encabezado = ft.Row(
            [
                ft.Container(width=70),
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
        page.update()  # 👈 REFRESCA LA UI


    def click_slot(dia: date, hora: int):
        # Aquí luego abrimos el diálogo de "Nueva cita"
        page.snack_bar = ft.SnackBar(
            content=ft.Text(
                f"Click en {dia.strftime('%Y-%m-%d')} {hora:02d}:00"
            ),
            bgcolor=ft.Colors.BLUE_200,
        )
        page.snack_bar.open = True

    # ---------- Mini calendario mensual (izquierda) ----------

    def dibujar_mini_calendario():
        mes_actual = mes_actual_ref.current
        year = mes_actual.year
        month = mes_actual.month

        encabezado = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.CHEVRON_LEFT,
                    icon_size=16,
                    tooltip="Mes anterior",
                    on_click=mes_anterior,
                ),
                ft.Text(f"{MESES[month-1]} {year}", weight="bold"),
                ft.IconButton(
                    icon=ft.Icons.CHEVRON_RIGHT,
                    icon_size=16,
                    tooltip="Mes siguiente",
                    on_click=mes_siguiente,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
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
            es_hoy = (fecha_dia == hoy)
            es_sel = (fecha_dia == fecha_seleccionada_ref.current)

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
        page.update()  # 👈 REFRESCA LA UI


    # ---------- Sync mini-calendario <-> semana ----------

    def seleccionar_dia(fecha: date):
        fecha_seleccionada_ref.current = fecha
        semana_lunes_ref.current = fecha - timedelta(days=fecha.weekday())
        mes_actual_ref.current = fecha.replace(day=1)
        dibujar_calendario_semanal()
        dibujar_mini_calendario()

    def mes_anterior(e):
        m = mes_actual_ref.current
        if m.month == 1:
            mes_actual_ref.current = m.replace(year=m.year - 1, month=12, day=1)
        else:
            mes_actual_ref.current = m.replace(month=m.month - 1, day=1)
        dibujar_mini_calendario()

    def mes_siguiente(e):
        m = mes_actual_ref.current
        if m.month == 12:
            mes_actual_ref.current = m.replace(year=m.year + 1, month=1, day=1)
        else:
            mes_actual_ref.current = m.replace(month=m.month + 1, day=1)
        dibujar_mini_calendario()

    def semana_anterior(e):
        semana_lunes_ref.current -= timedelta(days=7)
        fecha_seleccionada_ref.current = semana_lunes_ref.current
        mes_actual_ref.current = fecha_seleccionada_ref.current.replace(day=1)
        dibujar_calendario_semanal()
        dibujar_mini_calendario()

    def semana_siguiente(e):
        semana_lunes_ref.current += timedelta(days=7)
        fecha_seleccionada_ref.current = semana_lunes_ref.current
        mes_actual_ref.current = fecha_seleccionada_ref.current.replace(day=1)
        dibujar_calendario_semanal()
        dibujar_mini_calendario()

    def semana_hoy(e):
        fecha_seleccionada_ref.current = hoy
        semana_lunes_ref.current = hoy - timedelta(days=hoy.weekday())
        mes_actual_ref.current = fecha_seleccionada_ref.current.replace(day=1)
        dibujar_calendario_semanal()
        dibujar_mini_calendario()

    # Barra superior de la agenda semanal
    barra_controles = ft.Row(
        [
            toggle_btn,  # 👈 colapsar / expandir panel izquierdo
            ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, on_click=semana_anterior),
            ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, on_click=semana_siguiente),
            ft.TextButton("Hoy", on_click=semana_hoy),
            ft.Text("Semana:", weight="bold"),
            texto_semana,
        ],
        alignment=ft.MainAxisAlignment.START,
        spacing=5,
    )

    # Dibujar estado inicial
    dibujar_calendario_semanal()
    dibujar_mini_calendario()

    # Layout final: mini calendario izquierda, agenda derecha
    columna_derecha = ft.Column(
        [
            barra_controles,
            ft.Divider(),
            calendario_semanal_col,
        ],
        expand=True,
    )

    return ft.Column(
        [
            # Barra superior común a toda la vista
            # (ya incluye el botón de colapse)
            # barra_controles y Divider ya están dentro de columna_derecha,
            # así que aquí solo armamos fila principal.
            ft.Row(
                [
                    panel_izquierdo,
                    columna_derecha,
                ],
                expand=True,
            )
        ],
        expand=True,
    )

