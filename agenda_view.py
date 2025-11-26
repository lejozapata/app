import flet as ft
from datetime import date, timedelta

# ---------------------------------------------------------
# Constantes de texto para días y meses (en español)
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# Vista principal de agenda
# ---------------------------------------------------------

def build_agenda_view(page: ft.Page) -> ft.Control:
    """
    Construye la vista de Agenda:
      - Panel izquierdo: mini calendario mensual, selector de mes/año, botón colapsable.
      - Panel derecho: agenda semanal (Lunes–Domingo, 08:00–20:00).
    La función devuelve un ft.Control (Row) que se inserta en el body del main.
    """

    # ==================== ESTADO BÁSICO ====================

    hoy = date.today()

    # Día seleccionado en el mini calendario
    fecha_seleccionada = {"value": hoy}

    # Lunes de la semana actualmente visible en la agenda semanal
    semana_lunes = {"value": hoy - timedelta(days=hoy.weekday())}

    # Primer día del mes actualmente visible en el mini calendario
    mes_actual = {"value": fecha_seleccionada["value"].replace(day=1)}

    # Controles que vamos a actualizar dinámicamente
    calendario_semanal_col = ft.Column(
        expand=True, 
        spacing=0,
        scroll=ft.ScrollMode.AUTO,   # 👈 agrega scroll vertical
        )
    mini_calendario_col = ft.Column(spacing=5)
    texto_semana = ft.Text(weight="bold")

    # Panel izquierdo expandido/colapsado
    panel_expandido = {"value": True}

    # Intervalo de cada bloque de la agenda en minutos (por defecto 60)
    slot_minutes = {"value": 60}

    # Rango horario visible (7:00 a 21:00)
    START_HOUR = 7
    END_HOUR = 21

    # ==================== DROPDOWNS MES / AÑO ====================

    # Rango de años disponibles en el selector
    year_min = hoy.year - 4
    year_max = hoy.year + 1

   # Dropdown para seleccionar el MES (Enero, Febrero, ...)
    dd_mes = ft.Dropdown(
        width=140,
        dense=True,
        border_width=0,
        text_style=ft.TextStyle(
            size=13,
            weight=ft.FontWeight.BOLD,
        ),
        text_align=ft.TextAlign.CENTER,
        options=[ft.dropdown.Option(mes) for mes in MESES],  # value = "Enero", etc.
    )

    # Dropdown para seleccionar el AÑO (2020, 2021, ...)
    dd_year = ft.Dropdown(
        width=100,
        dense=True,
        border_width=0,
        text_style=ft.TextStyle(
            size=14,
            weight=ft.FontWeight.BOLD,
        ),
        text_align=ft.TextAlign.CENTER,
        options=[ft.dropdown.Option(str(y)) for y in range(year_min, year_max + 1)],
    )

    # ==================== HELPERS DE FECHAS ====================

    def obtener_dias_semana(lunes: date):
        """Devuelve una lista [lunes, martes, ..., domingo] para la semana de 'lunes'."""
        return [lunes + timedelta(days=i) for i in range(7)]

    # ==================== AGENDA SEMANAL (DERECHA) ====================

    def click_slot(dia: date, minuto: int):
        """
        Acción al hacer click en un bloque vacío de la agenda.
        De momento solo muestra un mensaje; luego aquí abriremos el modal de "Nueva cita".
        """
        h = minuto // 60
        mm = minuto % 60
        page.snack_bar = ft.SnackBar(
            content=ft.Text(f"Click en {dia.strftime('%Y-%m-%d')} {h:02d}:{mm:02d}"),
            bgcolor=ft.Colors.BLUE_200,
        )
        page.snack_bar.open = True
        page.update()

    def dibujar_calendario_semanal():
        """
        Redibuja completamente la agenda semanal usando el intervalo actual (slot_minutes["value"]).
        El rango horario va de START_HOUR a END_HOUR (incluyendo el último punto, ej. 21:00).
        """
        dias = obtener_dias_semana(semana_lunes["value"])

        # Generar lista de minutos desde START_HOUR hasta END_HOUR
        intervalo = slot_minutes["value"]
        start_min = START_HOUR * 60
        end_min = END_HOUR * 60
        minutos = list(range(start_min, end_min + 1, intervalo))

        filas = []

        # Texto resumen de la semana (ej. 'Lunes 24/11/2025 - Domingo 30/11/2025')
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
                        width=150,
                        padding=5,
                    )
                    for d in dias
                ],
                ft.Container(width=10),
            ]
        )
        filas.append(encabezado)

        # Filas para cada bloque de tiempo
        for m in minutos:
            h = m // 60
            mm = m % 60
            etiqueta_hora = f"{h:02d}:{mm:02d}"

            fila = ft.Row(
                [
                    # Columna de hora (07:00, 07:05, 07:10, ..., 21:00)
                    ft.Container(
                        width=80,
                        content=ft.Text(etiqueta_hora),
                        alignment=ft.alignment.center_right,
                        padding=5,
                    ),
                    # 7 columnas (una por día de la semana)
                    *[
                        ft.Container(
                            width=150,
                            height=50,  # un poco más bajo para que quepan más filas
                            bgcolor=ft.Colors.GREY_200,
                            border=ft.border.all(0.5, ft.Colors.GREY_400),
                            alignment=ft.alignment.center,
                            on_click=lambda e, dia=d, minuto=m: click_slot(dia, minuto),
                        )
                        for d in dias
                    ],
                    ft.Container(width=10),
                ]
            )
            filas.append(fila)

        calendario_semanal_col.controls = filas
        page.update()

    # ==================== MINI CALENDARIO (IZQUIERDA) ====================

    def dibujar_mini_calendario():
        """
        Redibuja el mini calendario mensual con:
          - letras de los días (L M X J V S D)
          - días del mes actual
          - día seleccionado resaltado
          - día de hoy con borde
        Además sincroniza los dropdowns dd_mes y dd_year.
        """
        m = mes_actual["value"]
        year = m.year
        month = m.month

        # Mantener dropdowns sincronizados
        dd_mes.value = MESES[month - 1]  # "Enero", "Febrero", etc.
        dd_year.value = str(year)

        # Cabecera de letras de días
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

        # Cálculo del número de días y desplazamiento del primer día del mes
        primer_dia_mes = date(year, month, 1)
        offset = primer_dia_mes.weekday()  # 0 = Lunes

        # Determinar cuántos días tiene el mes
        if month == 12:
            siguiente_mes = date(year + 1, 1, 1)
        else:
            siguiente_mes = date(year, month + 1, 1)
        dias_en_mes = (siguiente_mes - timedelta(days=1)).day

        celdas = []

        # Huecos antes del primer día (para alinear con el día de la semana correcto)
        for _ in range(offset):
            celdas.append(ft.Container(width=28, height=24))

        # Celdas de días del mes
        for dia_num in range(1, dias_en_mes + 1):
            fecha_dia = date(year, month, dia_num)
            es_hoy = (fecha_dia == hoy)
            es_sel = (fecha_dia == fecha_seleccionada["value"])

            bgcolor = None
            border = None
            text_color = None
            weight = None

            # Día seleccionado: fondo morado y texto blanco
            if es_sel:
                bgcolor = ft.Colors.DEEP_PURPLE_200
                text_color = ft.Colors.WHITE
                weight = "bold"

            # Día actual: borde negro
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

        # Agrupar celdas en filas de 7 (una por semana)
        filas_semanas = []
        for i in range(0, len(celdas), 7):
            fila = celdas[i:i + 7]

            # Si la última fila tiene menos de 7 columnas, rellenamos con vacíos
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
        """
        Cuando el usuario hace click en un día del mini calendario:
          - actualizamos el día seleccionado,
          - movemos la semana de la agenda al lunes de esa semana,
          - actualizamos el mes visible.
        """
        fecha_seleccionada["value"] = fecha
        semana_lunes["value"] = fecha - timedelta(days=fecha.weekday())
        mes_actual["value"] = fecha.replace(day=1)
        dibujar_calendario_semanal()
        dibujar_mini_calendario()

    # ==================== NAVEGACIÓN MES (DROPDOWN Y FLECHAS) ====================

    def cambiar_mes(e):
        """Handler cuando cambia el dropdown de mes."""
        value = dd_mes.value
        if not value:
            return

        m = mes_actual["value"]

        # dd_mes.value es "Enero", "Febrero", etc.
        try:
            nuevo_mes = MESES.index(value) + 1
        except ValueError:
            return  # No debería pasar

        mes_actual["value"] = m.replace(month=nuevo_mes, day=1)
        dibujar_mini_calendario()

    def cambiar_year(e):
        """Handler cuando cambia el dropdown de año."""
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
        """Flecha '<' de mes en el panel izquierdo."""
        m = mes_actual["value"]
        if m.month == 1:
            mes_actual["value"] = m.replace(year=m.year - 1, month=12, day=1)
        else:
            mes_actual["value"] = m.replace(month=m.month - 1, day=1)
        dibujar_mini_calendario()

    def mes_siguiente(e):
        """Flecha '>' de mes en el panel izquierdo."""
        m = mes_actual["value"]
        if m.month == 12:
            mes_actual["value"] = m.replace(year=m.year + 1, month=1, day=1)
        else:
            mes_actual["value"] = m.replace(month=m.month + 1, day=1)
        dibujar_mini_calendario()

    # Botones de cambio de mes
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

    # ==================== NAVEGACIÓN SEMANA (DERECHA) ====================

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

    intervalo_menu = ft.PopupMenuButton(
        icon=ft.Icons.ACCESS_TIME,
        tooltip="Intervalo de agenda",
        items=[
            ft.PopupMenuItem(
                text="5 minutos",
                on_click=lambda e, m=5: cambiar_intervalo(m),
            ),
            ft.PopupMenuItem(
                text="10 minutos",
                on_click=lambda e, m=10: cambiar_intervalo(m),
            ),
            ft.PopupMenuItem(
                text="15 minutos",
                on_click=lambda e, m=15: cambiar_intervalo(m),
            ),
            ft.PopupMenuItem(
                text="20 minutos",
                on_click=lambda e, m=20: cambiar_intervalo(m),
            ),
            ft.PopupMenuItem(
                text="30 minutos",
                on_click=lambda e, m=30: cambiar_intervalo(m),
            ),
            ft.PopupMenuItem(
                text="45 minutos",
                on_click=lambda e, m=45: cambiar_intervalo(m),
            ),
            ft.PopupMenuItem(
                text="60 minutos",
                on_click=lambda e, m=60: cambiar_intervalo(m),
            ),
        ],
    )

    # Barra superior sobre la agenda semanal
    barra_controles = ft.Row(
        [
            ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, on_click=semana_anterior, tooltip="Semana anterior"),
            ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, on_click=semana_siguiente, tooltip="Semana siguiente"),
            intervalo_menu,  # 👈 aquí va el reloj / menú de intervalos
            ft.TextButton("Hoy", on_click=semana_hoy),
            ft.Text("Semana:", weight="bold"),
            texto_semana,
        ],
        alignment=ft.MainAxisAlignment.START,
        spacing=5,
    )

    # ==================== BOTÓN DE COLAPSE DEL PANEL IZQUIERDO ====================

    toggle_btn = ft.IconButton(
        icon=ft.Icons.KEYBOARD_DOUBLE_ARROW_LEFT,
        icon_size=16,
        tooltip="Colapsar panel",
        style=ft.ButtonStyle(
            shape=ft.CircleBorder(),
            padding=10,
        ),
    )

    # Definimos panel_izquierdo aquí porque toggle_panel lo necesita
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
                # Fila 1: botón de colapse alineado a la derecha
                ft.Row(
                    [
                        ft.Container(expand=True),
                        toggle_btn,
                    ],
                    alignment=ft.MainAxisAlignment.END,
                ),

                # Fila 3: YEAR centrado  [ 2025 ▼ ]
                ft.Row(
                    [
                        ft.Container(expand=True),
                        dd_year,
                        ft.Container(expand=True),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                # Fila 2: controles de MES con flechas  < [Mes] >
                ft.Row(
                    [
                        btn_mes_anterior,
                        dd_mes,
                        btn_mes_siguiente,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),

                

                # Fila 4: mini calendario
                mini_calendario_col,
            ],
            spacing=10,
        ),
        width=260,
    )

    def toggle_panel(e):
        """
        Colapsa / expande el panel izquierdo.
        - En modo colapsado solo se ve una "oreja" con el botón de colapse.
        """
        panel_expandido["value"] = not panel_expandido["value"]

        if panel_expandido["value"]:
            # EXPANDIDO
            panel_izquierdo.width = 260
            mini_calendario_col.visible = True
            btn_mes_anterior.visible = True
            btn_mes_siguiente.visible = True
            dd_mes.visible = True
            dd_year.visible = True
            toggle_btn.icon = ft.Icons.KEYBOARD_DOUBLE_ARROW_LEFT
            toggle_btn.tooltip = "Colapsar panel"
        else:
            # COLAPSADO
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

    def cambiar_intervalo(minutos: int):
        """
        Cambia el tamaño de los bloques de la agenda (en minutos)
        y redibuja la agenda semanal.
        """
        slot_minutes["value"] = minutos
        dibujar_calendario_semanal()

    # ==================== RENDER INICIAL ====================

    # Dibujar por primera vez el mini calendario y la agenda semanal
    dibujar_calendario_semanal()
    dibujar_mini_calendario()

    # Panel derecho con barra de controles + agenda
    columna_derecha = ft.Column(
        [
            barra_controles,
            ft.Divider(),
            calendario_semanal_col,
        ],
        expand=True,
    )

    # Layout final: panel izquierdo + agenda
    return ft.Row(
        [
            panel_izquierdo,
            columna_derecha,
        ],
        expand=True,
    )
# ---------------------------------------------------------