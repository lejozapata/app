import flet as ft
from datetime import date, timedelta

from db import (
    obtener_configuracion_profesional,
    obtener_horarios_atencion,
    listar_pacientes,
    listar_servicios,
    crear_cita,
)

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


def build_agenda_view(page: ft.Page) -> ft.Control:
    """
    Vista de Agenda:
      - Panel izquierdo: mini calendario mensual, selector de mes/año, botón colapsable.
      - Panel derecho: agenda semanal (rango horario según configuración).
      - Click en una celda: abre diálogo de "Nueva reserva".
    """

    # ==================== ESTADO BÁSICO ====================

    hoy = date.today()

    fecha_seleccionada = {"value": hoy}
    semana_lunes = {"value": hoy - timedelta(days=hoy.weekday())}
    mes_actual = {"value": fecha_seleccionada["value"].replace(day=1)}
    slot_minutes = {"value": 60}

    calendario_semanal_col = ft.Column(
        expand=True,
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
    )
    mini_calendario_col = ft.Column(spacing=5)
    texto_semana = ft.Text(weight="bold")

    panel_expandido = {"value": True}

    # ==================== CONFIG / HORARIOS ====================

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

    # ==================== AYUDAS HORARIO ====================

    def minutos_desde_medianoche(hhmm: str) -> int:
        h, m = map(int, hhmm.split(":"))
        return h * 60 + m

    def obtener_dias_semana(lunes: date):
        return [lunes + timedelta(days=i) for i in range(7)]

    # ==================== RESERVA / DIÁLOGO ====================

    servicios = listar_servicios()
    reserva = {
        "fecha": None,       # date
        "hora_inicio": None,  # (h, m)
        "hora_fin": None,     # (h, m)
        "paciente": None,    # dict
        "servicio": None,    # dict
    }

    # --- Controles del diálogo ---
    titulo_reserva = ft.Text("Nueva reserva", size=20, weight="bold")

    txt_fecha = ft.TextField(label="Fecha", read_only=True, width=200)

    dd_hora = ft.Dropdown(label="Hora inicio", width=110)
    dd_min = ft.Dropdown(label="Minuto inicio", width=110)
    dd_hora_fin = ft.Dropdown(label="Hora fin", width=110)
    dd_min_fin = ft.Dropdown(label="Minuto fin", width=110)

    # NUEVO: estado de la cita
    dd_estado = ft.Dropdown(
        label="Estado",
        width=200,
        options=[
            ft.dropdown.Option("reservado", "Reservado"),
            ft.dropdown.Option("confirmado", "Confirmado"),
            ft.dropdown.Option("no_asistio", "No asistió"),
        ],
        value="reservado",
    )

    # NUEVO: flag de pago
    chk_pagado = ft.Checkbox(label="Pagado", value=False)

    txt_buscar_paciente = ft.TextField(
        label="Buscar paciente (nombre, documento, teléfono o email)",
        width=420,
    )
    resultados_pacientes = ft.Column(spacing=4)
    ficha_paciente = ft.Column(visible=False)

    dd_servicios = ft.Dropdown(
        label="Servicio",
        width=320,
        options=[
            ft.dropdown.Option(str(s["id"]), f"{s['nombre']} ({s['tipo']})")
            for s in servicios
        ],
    )
    txt_precio = ft.TextField(label="Precio", width=160, hint_text="Ej: 120000")
    txt_notas = ft.TextField(
        label="Notas internas (opcional)",
        multiline=True,
        width=450,
        height=100,
    )

    mensaje_error = ft.Text("", color=ft.Colors.RED, visible=False, size=12)

    # ----------------- BÚSQUEDA DE PACIENTES (local) -------------------

    def buscar_pacientes_local(texto: str) -> list[dict]:
        texto = (texto or "").strip().lower()
        if not texto:
            return []

        filas = listar_pacientes()
        resultados = []
        for row in filas:
            p = dict(row)
            doc = str(p.get("documento") or "")
            nombre = (p.get("nombre_completo") or "")
            tel = str(p.get("telefono") or "")
            email = (p.get("email") or "")

            if (
                texto in doc.lower()
                or texto in nombre.lower()
                or texto in tel.lower()
                or texto in email.lower()
            ):
                resultados.append(p)

        return resultados

    def actualizar_resultados_pacientes(e=None):
        q = txt_buscar_paciente.value
        resultados = buscar_pacientes_local(q)

        resultados_pacientes.controls.clear()
        if not resultados:
            if q.strip():
                resultados_pacientes.controls.append(
                    ft.Text("Sin resultados para esa búsqueda.", size=12, italic=True)
                )
        else:
            for p in resultados:
                resultados_pacientes.controls.append(
                    ft.ListTile(
                        dense=True,
                        title=ft.Text(p["nombre_completo"]),
                        subtitle=ft.Text(
                            f"{p['documento']} - {p.get('telefono','')} - {p.get('email','')}"
                        ),
                        on_click=lambda e, pac=p: seleccionar_paciente(pac),
                    )
                )

        if resultados_pacientes.page is not None:
            resultados_pacientes.update()

    txt_buscar_paciente.on_change = actualizar_resultados_pacientes

    def seleccionar_paciente(pac: dict):
        reserva["paciente"] = pac

        ficha_paciente.controls = [
            ft.Text("Paciente seleccionado:", weight="bold"),
            ft.Text(f"Nombre: {pac['nombre_completo']}"),
            ft.Text(f"Documento: {pac['documento']}"),
            ft.Text(f"Teléfono: {pac.get('telefono','')}"),
            ft.Text(f"Correo: {pac.get('email','')}"),
            ft.TextButton(
                "Cambiar paciente",
                on_click=lambda e: quitar_paciente(),
            ),
        ]
        ficha_paciente.visible = True

        resultados_pacientes.controls.clear()

        txt_buscar_paciente.value = ""

        titulo_reserva.value = f"Reserva de {pac['nombre_completo']}"

        # Solo actualizamos si el diálogo ya está montado
        if ficha_paciente.page is not None:
            ficha_paciente.update()
            resultados_pacientes.update()
            txt_buscar_paciente.update()
            titulo_reserva.update()

    def quitar_paciente():
        reserva["paciente"] = None
        ficha_paciente.visible = False
        ficha_paciente.controls.clear()

        titulo_reserva.value = "Nueva reserva"

        if ficha_paciente.page is not None:
            ficha_paciente.update()
            titulo_reserva.update()

    # ----------------- SERVICIO -------------------

    def seleccionar_servicio(e=None):
        sid = dd_servicios.value
        reserva["servicio"] = None
        txt_precio.value = ""

        if not sid:
            if txt_precio.page is not None:
                txt_precio.update()
            return

        srv = next((s for s in servicios if s["id"] == int(sid)), None)
        if not srv:
            if txt_precio.page is not None:
                txt_precio.update()
            return

        reserva["servicio"] = srv
        try:
            txt_precio.value = str(int(srv["precio"]))
        except Exception:
            txt_precio.value = str(srv["precio"])

        if txt_precio.page is not None:
            txt_precio.update()

    dd_servicios.on_change = seleccionar_servicio

    # ----------------- GUARDAR RESERVA -------------------

    def guardar_reserva(e):
        mensaje_error.visible = False
        mensaje_error.value = ""

        if not reserva["paciente"]:
            mensaje_error.value = "Debes seleccionar un paciente."
            mensaje_error.visible = True
            if mensaje_error.page is not None:
                mensaje_error.update()
            return

        if not reserva["servicio"]:
            mensaje_error.value = "Debes seleccionar un servicio."
            mensaje_error.visible = True
            if mensaje_error.page is not None:
                mensaje_error.update()
            return

        try:
            precio_final = float(txt_precio.value)
        except Exception:
            mensaje_error.value = "Precio inválido."
            mensaje_error.visible = True
            if mensaje_error.page is not None:
                mensaje_error.update()
            return

        fecha_obj = reserva["fecha"]
        if not fecha_obj:
            mensaje_error.value = "Fecha inválida."
            mensaje_error.visible = True
            if mensaje_error.page is not None:
                mensaje_error.update()
            return

        fecha_str = fecha_obj.strftime("%Y-%m-%d")
        hora_str = f"{dd_hora.value}:{dd_min.value}"
        srv = reserva["servicio"]
        modalidad = srv["tipo"]  # presencial / virtual / convenio_empresarial

        estado = dd_estado.value or "reservado"
        pagado_flag = 1 if chk_pagado.value else 0

        motivo = f"Servicio: {srv['nombre']} - Precio: {precio_final:,.0f}"
        notas = (txt_notas.value or "").strip()

        cita = {
            "documento_paciente": reserva["paciente"]["documento"],
            "fecha_hora": f"{fecha_str} {hora_str}",
            "modalidad": modalidad,
            "motivo": motivo,
            "notas": notas,
            "estado": estado,
            "pagado": pagado_flag,
        }

        crear_cita(cita)

        dialogo_reserva.open = False
        page.update()

        page.snack_bar = ft.SnackBar(
            content=ft.Text("Reserva creada exitosamente."),
            bgcolor=ft.Colors.GREEN_300,
        )
        page.snack_bar.open = True
        page.update()

    def cerrar_dialogo(e=None):
        dialogo_reserva.open = False
        page.update()

    # ----------------- DIALOGO NUEVA RESERVA -------------------

    dialogo_reserva = ft.AlertDialog(
        modal=True,
        title=titulo_reserva,
        content=ft.Column(
            [
                txt_fecha,
                ft.Row([dd_hora, dd_min, dd_hora_fin, dd_min_fin], spacing=10),
                ft.Row([dd_estado, chk_pagado], spacing=10),
                ft.Divider(),
                txt_buscar_paciente,
                resultados_pacientes,
                ficha_paciente,
                ft.Divider(),
                dd_servicios,
                txt_precio,
                txt_notas,
                mensaje_error,
            ],
            tight=True,
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            height=500,
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=cerrar_dialogo),
            ft.ElevatedButton("Guardar reserva", on_click=guardar_reserva),
        ],
    )

    # ----------------- CLICK EN SLOT (FIX IMPORTANTE) -------------------

    def click_slot(dia: date, minuto: int):
        """
        Al hacer click en una celda de la agenda:
          - Configuramos el estado de la reserva
          - Cargamos fecha/hora en los controles
          - NO hacemos .update() de controles individuales aquí
          - Abrimos el diálogo y luego hacemos page.update()
        """
        h = minuto // 60
        mm = minuto % 60

        reserva["fecha"] = dia
        reserva["hora_inicio"] = (h, mm)
        reserva["hora_fin"] = (h + 1, mm)

        # Fecha
        txt_fecha.value = dia.strftime("%Y-%m-%d")

        # Opciones de hora/minuto
        dd_hora.options = [ft.dropdown.Option(f"{x:02d}") for x in range(0, 24)]
        dd_min.options = [ft.dropdown.Option(f"{x:02d}") for x in range(0, 60, 5)]
        dd_hora_fin.options = [ft.dropdown.Option(f"{x:02d}") for x in range(0, 24)]
        dd_min_fin.options = [ft.dropdown.Option(f"{x:02d}") for x in range(0, 60, 5)]

        dd_hora.value = f"{h:02d}"
        dd_min.value = f"{mm:02d}"
        dd_hora_fin.value = f"{h+1:02d}"
        dd_min_fin.value = f"{mm:02d}"

        # Reset paciente/servicio/notas/errores/estado/pago
        reserva["paciente"] = None
        ficha_paciente.visible = False
        ficha_paciente.controls.clear()

        titulo_reserva.value = "Nueva reserva"

        txt_buscar_paciente.value = ""
        resultados_pacientes.controls.clear()

        reserva["servicio"] = None
        dd_servicios.value = None
        txt_precio.value = ""
        txt_notas.value = ""

        dd_estado.value = "reservado"
        chk_pagado.value = False

        mensaje_error.value = ""
        mensaje_error.visible = False

        # AHORA sí abrimos el diálogo y actualizamos la página
        page.dialog = dialogo_reserva
        dialogo_reserva.open = True
        # Mismo patrón que en admin_view
        page.open(dialogo_reserva)
        page.update()

    # ----------------- CELDA DE AGENDA -------------------

    def construir_celda(d: date, m: int) -> ft.Container:
        info = horarios_map.get(d.weekday())
        bgcolor = ft.Colors.GREY_200

        if info:
            inicio_min = minutos_desde_medianoche(info["hora_inicio"])
            fin_min = minutos_desde_medianoche(info["hora_fin"])
            if not info["habilitado"] or m < inicio_min or m >= fin_min:
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

    # ----------------- AGENDA SEMANAL -------------------

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

    # ----------------- MINI CALENDARIO -------------------

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

    # ----------------- NAVEGACIÓN MINI CALENDARIO -------------------

    today_year = hoy.year
    year_min = today_year - 4
    year_max = today_year + 1

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

    def cambiar_mes(e=None):
        if not dd_mes.value:
            return
        nuevo_mes = MESES.index(dd_mes.value) + 1
        mes_actual["value"] = mes_actual["value"].replace(month=nuevo_mes, day=1)
        dibujar_mini_calendario()

    def cambiar_year(e=None):
        if not dd_year.value:
            return
        nuevo_year = int(dd_year.value)
        mes_actual["value"] = mes_actual["value"].replace(year=nuevo_year, day=1)
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

    # ----------------- NAVEGACIÓN SEMANAL -------------------

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

    # ----------------- PANEL IZQUIERDO -------------------

    toggle_btn = ft.IconButton(
        icon=ft.Icons.KEYBOARD_DOUBLE_ARROW_LEFT,
        icon_size=16,
        tooltip="Colapsar panel",
        style=ft.ButtonStyle(shape=ft.CircleBorder(), padding=10),
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

    # ----------------- RENDER INICIAL -------------------

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
