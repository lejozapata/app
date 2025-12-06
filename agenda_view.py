import os
import smtplib
from email.message import EmailMessage
from notificaciones_email import (
    enviar_correo_cita,
    enviar_correo_cancelacion,
    ConfigSMTPIncompleta,
)
import flet as ft
from datetime import date, datetime, timedelta
import threading
import urllib.parse

from db import (
    obtener_configuracion_profesional,
    obtener_horarios_atencion,
    listar_pacientes,
    listar_servicios,
    listar_citas_con_paciente_rango,
    crear_cita,
    actualizar_cita,
    eliminar_cita,
    existe_cita_en_fecha,
    crear_bloqueo,
    listar_bloqueos_rango,
    actualizar_bloqueo,
    eliminar_bloqueo,
    existe_bloqueo_en_fecha,
    obtener_configuracion_profesional,
    listar_empresas_convenio,
    crear_factura_convenio,
    obtener_configuracion_facturacion,
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
      - Click en celda: crear cita.
      - Click en bloque de cita: editar cita.
    """

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

    # DatePicker para seleccionar fecha de la cita
    date_picker = ft.DatePicker()
    page.overlay.append(date_picker)

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


    # ==================== Notificación Whatsapp ====================

    def enviar_whatsapp_confirmacion(e=None):
        import locale
        locale.setlocale(locale.LC_TIME, "Spanish_Spain")
        """Abre WhatsApp con un mensaje de confirmación de la cita actual."""
        pac = reserva.get("paciente")
        if not pac:
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Primero selecciona un paciente."),
                bgcolor=ft.Colors.AMBER_300,
            )
            page.snack_bar.open = True
            page.update()
            return

        tel = (pac.get("telefono") or "").strip()
        if not tel:
            page.snack_bar = ft.SnackBar(
                content=ft.Text("El paciente no tiene teléfono registrado."),
                bgcolor=ft.Colors.AMBER_300,
            )
            page.snack_bar.open = True
            page.update()
            return

        # Dejar solo dígitos del teléfono
        digits = "".join(c for c in tel if c.isdigit())
        if not digits:
            page.snack_bar = ft.SnackBar(
                content=ft.Text("El número de teléfono del paciente no es válido."),
                bgcolor=ft.Colors.AMBER_300,
            )
            page.snack_bar.open = True
            page.update()
            return

        # Asumimos Colombia (+57); ajustable más adelante
        if digits.startswith("57"):
            wa_num = digits
        elif digits.startswith("0"):
            wa_num = "57" + digits.lstrip("0")
        else:
            wa_num = "57" + digits

        # -------- Datos de fecha / hora --------
        fecha_obj = reserva.get("fecha")
        try:
            fecha_str = fecha_obj.strftime("%A %d de %B de %Y")
            # Capitalizar primera letra del día/mes
            fecha_str = fecha_str.capitalize()
        except:
            fecha_str = "la fecha acordada"

        # Hora en formato 12h (ej: 2:00 p. m.)
        try:
            h = int(dd_hora.value)
            m = int(dd_min.value)
            h12 = h if 1 <= h <= 12 else (12 if h == 0 else h - 12)
            sufijo = "a. m." if h < 12 else "p. m."
            hora_hum = f"{h12}:{m:02d} {sufijo}"
        except Exception:
            hora_hum = f"{dd_hora.value}:{dd_min.value}"

        # -------- Servicio / modalidad / valor --------
        srv = reserva.get("servicio") or {}
        nombre_servicio = srv.get("nombre", "").strip()

        modalidad_raw = srv.get("tipo", "")  # presencial / virtual / convenio_empresarial
        modalidad_map = {
            "presencial": "Presencial",
            "virtual": "Virtual",
            "convenio_empresarial": "Convenio empresarial",
        }
        modalidad = modalidad_map.get(modalidad_raw, modalidad_raw or "Sin especificar")

        # Valor (precio)
        valor_str = ""
        try:
            # Limpiamos puntos/comas por si vienen formateados
            valor_num = float(
                txt_precio.value.replace(".", "").replace(",", ".")
            )
            valor_str = f"{valor_num:,.0f}".replace(",", ".")  # 110.000
        except Exception:
            pass

        direccion = cfg.get("direccion") or ""

        # -------- Mensaje de WhatsApp --------
        nombre_paciente = pac.get("nombre_completo", "").strip()

        msg_lines = [
            f"• Hola *{nombre_paciente}*,",
            "",
            "• *Cita confirmada*",
            f"• *Fecha:* {fecha_str}",
            f"• *Hora:* {hora_hum}",
            f"• *Modalidad:* {modalidad}",
        ]

        if nombre_servicio:
            msg_lines.append(f"• *Servicio:* {nombre_servicio}")

        if valor_str:
            msg_lines.append(f"• *Valor:* ${valor_str}")

        if modalidad_raw == "presencial" and direccion:
            msg_lines.append(f"• *Dirección:* {direccion}")

        msg_lines.append("")
        msg_lines.append(
            "Si necesitas reagendar o cancelar, por favor respóndeme por este medio."
        )

        msg = "\n".join(msg_lines)

        url = f"https://wa.me/{wa_num}?text={urllib.parse.quote(msg)}"
        page.launch_url(url)



    # ==================== HELPERS HORARIO ====================

    def minutos_desde_medianoche(hhmm: str) -> int:
        h, m = map(int, hhmm.split(":"))
        return h * 60 + m

    def obtener_dias_semana(lunes: date):
        return [lunes + timedelta(days=i) for i in range(7)]

    # ==================== ESTADO RESERVA / DIÁLOGO ====================

    # Convertimos a dict para poder usar .get()
    servicios_rows = listar_servicios()
    servicios = [dict(s) for s in servicios_rows]

    reserva = {
        "fecha": None,        # date
        "hora_inicio": None,  # (h, m)
        "hora_fin": None,     # (h, m)
        "paciente": None,     # dict
        "servicio": None,     # dict
    }

    cita_editando_id = {"value": None}  # None = nueva, int = editar cita existente
    cita_editando_row = {"value": None}       # row completo de la cita en edición
    paciente_cita_editando = {"value": None}  # paciente de la cita en edición

    # Estado para bloqueos de agenda
    bloqueo_editando_id = {"value": None}  # None = nuevo, int = editar bloqueo existente

    # Último slot clickeado (se usa para saber dónde crear reserva o bloqueo)
    slot_actual = {
        "fecha": None,   # date
        "minuto": None,  # minutos desde medianoche
    }

     # Slot seleccionado para mostrar el botón "+ Agregar"
    slot_agregar = {
        "fecha": None,   # date
        "minuto": None,  # minutos desde medianoche
    }

    # --- Controles del diálogo ---

    titulo_reserva = ft.Text("Nueva reserva", size=20, weight="bold")

    txt_fecha = ft.TextField(
        label="Fecha",
        read_only=True,
        width=200,
    )
    btn_fecha = ft.IconButton(
        icon=ft.Icons.CALENDAR_MONTH,
        tooltip="Cambiar fecha",
    )

    dd_hora = ft.Dropdown(label="Hora inicio", width=110)
    dd_min = ft.Dropdown(label="Minuto inicio", width=110)
    dd_hora_fin = ft.Dropdown(label="Hora fin", width=110)
    dd_min_fin = ft.Dropdown(label="Minuto fin", width=110)

    # ---------- Selector de estado con puntico de color (tipo AgendaPro) ----------

    def build_estado_selector():
        colores = {
            "reservado": "#77D0FA",   # azul
            "confirmado": "#F4C542",  # amarillo
            "no_asistio": "#F28B82",  # rojo claro
        }
        nombres = {
            "reservado": "Reservado",
            "confirmado": "Confirmado",
            "no_asistio": "No asistió",
        }

        estado_text = ft.Text("Reservado")
        indicador = ft.Container(
            width=10,
            height=10,
            border_radius=20,
            bgcolor=colores["reservado"],
        )

        selector = ft.PopupMenuButton(
            content=ft.Row(
                [
                    indicador,
                    estado_text,
                    ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=16),
                ],
                spacing=8,
            ),
            items=[],
            tooltip="Estado de la cita",
        )

        def set_value(valor: str):
            if valor not in colores:
                valor = "reservado"
            selector.data = valor
            estado_text.value = nombres[valor]
            indicador.bgcolor = colores[valor]
            if estado_text.page is not None:
                estado_text.update()
            if indicador.page is not None:
                indicador.update()

        def get_value() -> str:
            return selector.data or "reservado"

        def make_item(valor: str) -> ft.PopupMenuItem:
            return ft.PopupMenuItem(
                content=ft.Row(
                    [
                        ft.Container(
                            width=10,
                            height=10,
                            border_radius=20,
                            bgcolor=colores[valor],
                        ),
                        ft.Text(nombres[valor]),
                    ],
                    spacing=8,
                ),
                on_click=lambda e, v=valor: set_value(v),
            )

        selector.items = [
            make_item("reservado"),
            make_item("confirmado"),
            make_item("no_asistio"),
        ]

        # valor inicial
        selector.data = "reservado"
        # “métodos” auxiliares
        selector.set_value = set_value
        selector.get_value = get_value

        return selector

    dd_estado = build_estado_selector()

    chk_pagado = ft.Checkbox(label="Pagado", value=False)

    chk_notificar_email = ft.Checkbox(
        label="Enviar correo de confirmación al paciente",
        value=False,
        visible=False,  # solo se muestra si el paciente tiene email
    )

    # Boton whatsapp

    btn_whatsapp_confirmacion = ft.ElevatedButton(
        content=ft.Row(
            [
                ft.Image(
                    src="https://cdn-icons-png.flaticon.com/512/3536/3536445.png",
                    width=18,
                    height=18,
                ),
                ft.Text("Enviar WhatsApp de confirmación"),
            ],
            spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        on_click=enviar_whatsapp_confirmacion,
        disabled=True,   # deshabilitado por defecto
        visible=False,   # y oculto por defecto (solo en edición)
    )

    chk_notificar_cancelacion = ft.Switch(
        label="Enviar notificación por correo",
        value=True,
    )

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

    txt_empresa_convenio = ft.TextField(
        label="Empresa (si es convenio)",
        width=320,
        read_only=True,
        disabled=True,
        visible=False,
    )

    txt_precio = ft.TextField(label="Precio", width=160, hint_text="Ej: 120000")
    txt_notas = ft.TextField(
        label="Notas internas (opcional)",
        multiline=True,
        width=450,
        height=100,
    )

    mensaje_error = ft.Text("", color=ft.Colors.RED, visible=False, size=12)

    # --- Manejo de DatePicker para la fecha de la cita ---

    def abrir_datepicker(e):
        if reserva["fecha"]:
            date_picker.value = reserva["fecha"]
        else:
            date_picker.value = hoy
        date_picker.open = True
        page.update()

    def on_fecha_cambiada(e):
        if date_picker.value:
            reserva["fecha"] = date_picker.value
            txt_fecha.value = date_picker.value.strftime("%Y-%m-%d")
            if txt_fecha.page is not None:
                txt_fecha.update()

    btn_fecha.on_click = abrir_datepicker
    txt_fecha.on_tap = abrir_datepicker
    date_picker.on_change = on_fecha_cambiada

    # ----------------- BÚSQUEDA DE PACIENTES (local) -------------------

    def buscar_pacientes_local(texto: str):
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

         # Mostrar / ocultar el checkbox de correo según si el paciente tiene email
        email = (pac.get("email") or "").strip()
        if email:
            chk_notificar_email.visible = True
            # Para nuevas reservas lo dejaremos marcado por defecto,
            # luego en edición lo forzaremos a False.
            chk_notificar_email.value = True
        else:
            chk_notificar_email.visible = False
            chk_notificar_email.value = False

        if ficha_paciente.page is not None:
            ficha_paciente.update()
            resultados_pacientes.update()
            txt_buscar_paciente.update()
            titulo_reserva.update()
            chk_notificar_email.update()

    def quitar_paciente():
        reserva["paciente"] = None
        ficha_paciente.visible = False
        ficha_paciente.controls.clear()

        btn_whatsapp_confirmacion.disabled = True
        btn_whatsapp_confirmacion.visible = False
        if btn_whatsapp_confirmacion.page is not None:
            btn_whatsapp_confirmacion.update()

        titulo_reserva.value = "Nueva reserva"

        chk_notificar_email.visible = False
        chk_notificar_email.value = False

        if ficha_paciente.page is not None:
            ficha_paciente.update()
            titulo_reserva.update()
            chk_notificar_email.update()

    # ----------------- SERVICIO -------------------

    def seleccionar_servicio(e=None):
        sid = dd_servicios.value
        reserva["servicio"] = None
        txt_precio.value = ""

        if not sid:
            txt_empresa_convenio.value = ""
            txt_empresa_convenio.visible = False
            if txt_precio.page is not None:
                txt_precio.update()
            if txt_empresa_convenio.page is not None:
                txt_empresa_convenio.update()
            return

        srv = next((s for s in servicios if s["id"] == int(sid)), None)
        if not srv:
            txt_empresa_convenio.value = ""
            txt_empresa_convenio.visible = False
            if txt_precio.page is not None:
                txt_precio.update()
            if txt_empresa_convenio.page is not None:
                txt_empresa_convenio.update()
            return

        reserva["servicio"] = srv

        try:
            txt_precio.value = str(int(srv["precio"]))
        except Exception:
            txt_precio.value = str(srv["precio"])

        if srv["tipo"] == "convenio_empresarial":
            txt_empresa_convenio.value = srv.get("empresa") or ""
            txt_empresa_convenio.visible = True
        else:
            txt_empresa_convenio.value = ""
            txt_empresa_convenio.visible = False

        if txt_precio.page is not None:
            txt_precio.update()
        if txt_empresa_convenio.page is not None:
            txt_empresa_convenio.update()

    dd_servicios.on_change = seleccionar_servicio

    # ----------------- GUARDAR (CREAR / EDITAR) -------------------

    def guardar_reserva(e):
        mensaje_error.visible = False
        mensaje_error.value = ""

        # Validaciones básicas
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
        hora_inicio_str = f"{dd_hora.value}:{dd_min.value}"
        hora_fin_str = f"{dd_hora_fin.value}:{dd_min_fin.value}"

        srv = reserva["servicio"]
        modalidad = srv["tipo"]  # presencial / virtual / convenio_empresarial

        estado = dd_estado.get_value()
        pagado_flag = 1 if chk_pagado.value else 0

        motivo = f"Servicio: {srv['nombre']} - Valor: {precio_final:,.0f}"
        notas = (txt_notas.value or "").strip()

        datos_cita = {
            "documento_paciente": reserva["paciente"]["documento"],
            "fecha_hora": f"{fecha_str} {hora_inicio_str}",
            "modalidad": modalidad,
            "motivo": motivo,
            "notas": notas,
            "estado": estado,
            "pagado": pagado_flag,
            "precio": precio_final,
        }

        # Validar que no exista otra cita en la misma fecha y hora
        cita_id_actual = cita_editando_id["value"]
        if existe_cita_en_fecha(datos_cita["fecha_hora"], cita_id_actual):
            mensaje_error.value = (
                "Ya existe una cita en esa fecha y hora. "
                "Por favor selecciona otra hora."
            )
            mensaje_error.visible = True
            if mensaje_error.page is not None:
                mensaje_error.update()
            return

        # Validar bloqueo de horario
        if existe_bloqueo_en_fecha(datos_cita["fecha_hora"], None):
            mensaje_error.value = (
                "Este horario está bloqueado en la agenda. "
                "Elimina o mueve el bloqueo antes de agendar un paciente."
            )
            mensaje_error.visible = True
            if mensaje_error.page is not None:
                mensaje_error.update()
            return

        # Guardar en BD
        es_nueva = cita_editando_id["value"] is None
        if es_nueva:
            cita_id = crear_cita(datos_cita)
        else:
            cita_id = cita_editando_id["value"]
            actualizar_cita(cita_id, datos_cita)

        # Enviar correo si el usuario lo pidió y hay paciente (de forma asíncrona)
        if chk_notificar_email.value and reserva.get("paciente"):

            def tarea_correo():
                try:
                    enviar_correo_cita(
                        reserva["paciente"],
                        datos_cita,
                        hora_fin_str,
                        cita_id,
                        cfg_profesional=cfg,
                        es_nueva=es_nueva,
                    )
                    print("Correo de cita enviado correctamente.")
                except ConfigSMTPIncompleta:
                    print(
                        "La reserva se guardó, pero falta configurar el envío de correos (SMTP)."
                    )
                except Exception as ex:
                    print(f"Error al enviar correo de cita: {ex}")

            threading.Thread(target=tarea_correo, daemon=True).start()


        # Cerrar diálogo, refrescar agenda y mostrar snackbar de éxito genérico
        dialogo_reserva.open = False
        page.update()

        dibujar_calendario_semanal()

        page.snack_bar = ft.SnackBar(
            content=ft.Text(
                "Reserva creada exitosamente."
                if es_nueva
                else "Reserva actualizada."
            ),
            bgcolor=ft.Colors.GREEN_300,
        )
        page.snack_bar.open = True
        page.update()


    def cerrar_dialogo(e=None):
        dialogo_reserva.open = False
        page.update()

    # ----------------- CONTENIDO PRINCIPAL DEL DIÁLOGO -------------------

    contenido_reserva = ft.Column(
        [
            ft.Row([txt_fecha, btn_fecha], spacing=5),
            ft.Row([dd_hora, dd_min, dd_hora_fin, dd_min_fin], spacing=10),
            ft.Row([dd_estado, chk_pagado], spacing=10),
            ft.Divider(),
            txt_buscar_paciente,
            resultados_pacientes,
            ficha_paciente,
            ft.Divider(),
            dd_servicios,
            txt_empresa_convenio,
            txt_precio,
            txt_notas,
            chk_notificar_email,
            btn_whatsapp_confirmacion,
            mensaje_error,
        ],
        tight=True,
        spacing=10,
        scroll=ft.ScrollMode.AUTO,
        height=500,
    )

    # ----------------- LÓGICA DE CONFIRMACIÓN DE CANCELACIÓN -------------------

    # Estas funciones usan dialogo_reserva, que se define unas líneas más abajo.
    def restaurar_dialogo_reserva():
        dialogo_reserva.title = titulo_reserva
        dialogo_reserva.content = contenido_reserva

        # Si es una cita nueva (sin id) NO mostramos "Cancelar cita"
        if cita_editando_id["value"] is None:
            dialogo_reserva.actions = [
                ft.TextButton("Cerrar", on_click=cerrar_dialogo),
                ft.ElevatedButton("Guardar reserva", on_click=guardar_reserva),
            ]
        else:
            dialogo_reserva.actions = [
                ft.TextButton("Cerrar", on_click=cerrar_dialogo),
                ft.TextButton(
                    "Cancelar cita",
                    on_click=mostrar_confirmacion_cancelar,
                ),
                ft.ElevatedButton("Guardar reserva", on_click=guardar_reserva),
            ]

        if dialogo_reserva.page is not None:
            dialogo_reserva.update()

        # Solo actualizamos si el diálogo ya está agregado a la página
        if dialogo_reserva.page is not None:
            dialogo_reserva.update()


    def ejecutar_cancelacion(enviar_notificacion: bool = False):
        """Ejecuta realmente la cancelación (eliminación) de la cita."""
        cita_id = cita_editando_id["value"]

        if cita_id is not None:
            eliminar_cita(cita_id)

            # Enviar correo de cancelación si el usuario lo pidió
            if (
                enviar_notificacion
                and paciente_cita_editando["value"] is not None
                and cita_editando_row["value"] is not None
            ):
                pac = paciente_cita_editando["value"]
                cita_row = cita_editando_row["value"]

                datos_cita_email = {
                    "fecha_hora": cita_row["fecha_hora"][:16],
                    "modalidad": cita_row.get("modalidad", ""),
                    "motivo": cita_row.get("motivo", ""),
                }

                def tarea_cancel():
                    try:
                        enviar_correo_cancelacion(
                            pac,
                            datos_cita_email,
                            cfg_profesional=cfg,
                        )
                        print("Correo de cancelación enviado correctamente.")
                    except ConfigSMTPIncompleta:
                        print(
                            "La cita se canceló, pero falta configurar el envío de correos (SMTP)."
                        )
                    except Exception as ex:
                        print(f"Error al enviar correo de cancelación: {ex}")

                threading.Thread(target=tarea_cancel, daemon=True).start()

        dialogo_reserva.open = False
        page.update()

        dibujar_calendario_semanal()

        page.snack_bar = ft.SnackBar(
            content=ft.Text("La cita ha sido cancelada."),
            bgcolor=ft.Colors.RED_300,
        )
        page.snack_bar.open = True
        page.update()


    def mostrar_confirmacion_cancelar(e=None):
        """
        Si es cita nueva: actúa como "cerrar".
        Si es cita existente: reemplaza el contenido del diálogo por una confirmación.
        """
        # Cita nueva -> no hay nada que cancelar, solo cerrar
        if cita_editando_id["value"] is None:
            cerrar_dialogo()
            return

        # Cada vez que abrimos la confirmación, el switch va por defecto en True
        chk_notificar_cancelacion.value = True

        dialogo_reserva.title = ft.Text("Confirmar cancelación")

        dialogo_reserva.content = ft.Column(
            [
                ft.Text(
                    "¿Seguro que deseas cancelar esta cita?\n"
                    "Esta acción no se puede deshacer."
                ),
                chk_notificar_cancelacion,
            ],
            spacing=10,
            tight=True,
        )

        dialogo_reserva.actions = [
            ft.TextButton(
                "No",
                on_click=lambda ev: restaurar_dialogo_reserva(),
            ),
            ft.TextButton(
                "Sí, cancelar",
                on_click=lambda ev: ejecutar_cancelacion(
                    chk_notificar_cancelacion.value
                ),
            ),
        ]

        if dialogo_reserva.page is not None:
            dialogo_reserva.update()


    # ----------------- DIÁLOGO DE BLOQUEO DE HORARIO -------------------

    titulo_bloqueo = ft.Text("Bloquear horario", size=20, weight="bold")

    # Mostramos el horario en un solo campo de texto, solo lectura
    txt_bloqueo_fecha_hora = ft.TextField(
        label="Horario",
        width=250,
        read_only=True,
    )

    txt_bloqueo_motivo = ft.TextField(
        label="Motivo / etiqueta",
        width=400,
        multiline=True,
        min_lines=2,
        max_lines=4,
    )

    mensaje_error_bloqueo = ft.Text("", color=ft.Colors.RED, visible=False, size=12)


    def cerrar_dialogo_bloqueo(e=None):
        dialogo_bloqueo.open = False
        page.update()

    def preparar_bloqueo_nuevo():
        """Prepara el diálogo para crear un nuevo bloqueo en el slot_actual."""
        bloqueo_editando_id["value"] = None
        mensaje_error_bloqueo.value = ""
        mensaje_error_bloqueo.visible = False
        txt_bloqueo_motivo.value = ""

        dia = slot_actual["fecha"]
        minuto = slot_actual["minuto"]

        if dia is None or minuto is None:
            # fallback raro, pero evitamos crashear
            ahora = datetime.now()
            dia = ahora.date()
            minuto = ahora.hour * 60 + ahora.minute

        h = minuto // 60
        mm = minuto % 60

        txt_bloqueo_fecha_hora.value = f"{dia.strftime('%Y-%m-%d')} {h:02d}:{mm:02d}"
        titulo_bloqueo.value = "Bloquear horario"
        actualizar_acciones_dialogo_bloqueo()

    def abrir_dialogo_bloqueo_nuevo():
        """Abre el diálogo de bloqueo para el slot_actual."""
        preparar_bloqueo_nuevo()
        page.dialog = dialogo_bloqueo
        dialogo_bloqueo.open = True
        page.open(dialogo_bloqueo)
        page.update()

    def abrir_editar_bloqueo(bloq_row: dict):
        """Abre el diálogo para editar un bloqueo existente."""
        bloqueo_editando_id["value"] = bloq_row["id"]
        titulo_bloqueo.value = "Editar bloqueo de horario"

        txt_bloqueo_fecha_hora.value = bloq_row["fecha_hora"][:16]
        txt_bloqueo_motivo.value = bloq_row.get("motivo", "")

        mensaje_error_bloqueo.value = ""
        mensaje_error_bloqueo.visible = False

        actualizar_acciones_dialogo_bloqueo()

        page.dialog = dialogo_bloqueo
        dialogo_bloqueo.open = True
        page.open(dialogo_bloqueo)
        page.update()

    def guardar_bloqueo(e=None):
        """Crea o actualiza un bloqueo."""
        mensaje_error_bloqueo.visible = False
        mensaje_error_bloqueo.value = ""

        motivo = (txt_bloqueo_motivo.value or "").strip()
        if not motivo:
            mensaje_error_bloqueo.value = "Debes ingresar un motivo para el bloqueo."
            mensaje_error_bloqueo.visible = True
            if mensaje_error_bloqueo.page is not None:
                mensaje_error_bloqueo.update()
            return

        fecha_hora_str = txt_bloqueo_fecha_hora.value.strip()
        if not fecha_hora_str:
            mensaje_error_bloqueo.value = "Horario inválido."
            mensaje_error_bloqueo.visible = True
            if mensaje_error_bloqueo.page is not None:
                mensaje_error_bloqueo.update()
            return

        # Validación: no debe haber otra cita en ese slot
        if existe_cita_en_fecha(fecha_hora_str, None):
            mensaje_error_bloqueo.value = (
                "Ya existe una cita en este horario. "
                "No se puede crear un bloqueo aquí."
            )
            mensaje_error_bloqueo.visible = True
            if mensaje_error_bloqueo.page is not None:
                mensaje_error_bloqueo.update()
            return

        if bloqueo_editando_id["value"] is None:
            # Validar también que no haya OTRO bloqueo en ese slot
            if existe_bloqueo_en_fecha(fecha_hora_str, None):
                mensaje_error_bloqueo.value = (
                    "Ya existe un bloqueo en este horario."
                )
                mensaje_error_bloqueo.visible = True
                if mensaje_error_bloqueo.page is not None:
                    mensaje_error_bloqueo.update()
                return

            crear_bloqueo(
                {
                    "motivo": motivo,
                    "fecha_hora": fecha_hora_str,
                }
            )
            msg_snack = "Bloqueo creado."
        else:
            # En edición no cambiamos el horario (solo motivo),
            # por lo que no es necesario validar de nuevo contra otros bloqueos.
            actualizar_bloqueo(
                bloqueo_editando_id["value"],
                {
                    "motivo": motivo,
                    "fecha_hora": fecha_hora_str,
                },
            )
            msg_snack = "Bloqueo actualizado."

        dialogo_bloqueo.open = False
        page.update()

        dibujar_calendario_semanal()

        page.snack_bar = ft.SnackBar(
            content=ft.Text(msg_snack),
            bgcolor=ft.Colors.GREY_300,
        )
        page.snack_bar.open = True
        page.update()

    def confirmar_eliminar_bloqueo(e=None):
        """Muestra confirmación antes de eliminar un bloqueo."""
        if bloqueo_editando_id["value"] is None:
            # Si es nuevo y no hay nada guardado, simplemente cerramos
            cerrar_dialogo_bloqueo()
            return

        def cancelar(ev=None):
            dialog_confirm.open = False
            page.update()

        def confirmar(ev=None):
            eliminar_bloqueo(bloqueo_editando_id["value"])
            dialog_confirm.open = False
            page.update()

            dibujar_calendario_semanal()

            page.snack_bar = ft.SnackBar(
                content=ft.Text("Bloqueo eliminado."),
                bgcolor=ft.Colors.RED_300,
            )
            page.snack_bar.open = True
            page.update()

        dialog_confirm = ft.AlertDialog(
            modal=True,
            title=ft.Text("Eliminar bloqueo"),
            content=ft.Text(
                "¿Seguro que deseas eliminar este bloqueo de horario?\n"
                "Esta acción no se puede deshacer."
            ),
            
            actions=[
                ft.TextButton("Cancelar", on_click=cancelar),
                ft.TextButton("Eliminar", on_click=confirmar),
            ],
        )

        # Abrir diálogo de confirmación (cierra el de bloqueo mientras tanto)
        page.open(dialog_confirm)
    
    def actualizar_acciones_dialogo_bloqueo():
        """Configura los botones del diálogo de bloqueo según si es nuevo o edición."""
        if bloqueo_editando_id["value"] is None:
            # Nuevo bloqueo: solo cerrar y guardar
            dialogo_bloqueo.actions = [
                ft.TextButton("Cerrar", on_click=cerrar_dialogo_bloqueo),
                ft.ElevatedButton("Guardar bloqueo", on_click=guardar_bloqueo),
            ]
        else:
            # Edición: permitir eliminar
            dialogo_bloqueo.actions = [
                ft.TextButton("Cerrar", on_click=cerrar_dialogo_bloqueo),
                ft.TextButton(
                    "Cancelar bloqueo",
                    on_click=confirmar_eliminar_bloqueo,
                ),
                ft.ElevatedButton("Guardar bloqueo", on_click=guardar_bloqueo),
            ]

        if dialogo_bloqueo.page is not None:
            dialogo_bloqueo.update()

    dialogo_bloqueo = ft.AlertDialog(
        modal=True,
        title=titulo_bloqueo,
        content=ft.Column(
            [
                txt_bloqueo_fecha_hora,
                txt_bloqueo_motivo,
                mensaje_error_bloqueo,
            ],
            spacing=10,
            tight=True,
        ),
        actions=[],  # se llenan dinámicamente por actualizar_acciones_dialogo_bloqueo()
    )


    # ----------------- DIALOGO -------------------

    dialogo_reserva = ft.AlertDialog(
        modal=True,
        title=titulo_reserva,
        content=contenido_reserva,
        actions=[
            ft.TextButton("Cerrar", on_click=cerrar_dialogo),
            ft.TextButton(
                "Cancelar cita",
                on_click=mostrar_confirmacion_cancelar,
            ),
            ft.ElevatedButton("Guardar reserva", on_click=guardar_reserva),
        ],
    )

    # ----------------- CLICK EN SLOT (NUEVA CITA) -------------------

    # def preparar_reserva_para_slot(dia: date, minuto: int):
    #     """Configura el estado de la reserva para el slot indicado, pero no abre el diálogo."""
    #     h = minuto // 60
    #     mm = minuto % 60

    #     cita_editando_id["value"] = None

    #     reserva["fecha"] = dia
    #     reserva["hora_inicio"] = (h, mm)
    #     reserva["hora_fin"] = (h + 1, mm)

    #     txt_fecha.value = dia.strftime("%Y-%m-%d")

    #     dd_hora.options = [ft.dropdown.Option(f"{x:02d}") for x in range(0, 24)]
    #     dd_min.options = [ft.dropdown.Option(f"{x:02d}") for x in range(0, 60, 5)]
    #     dd_hora_fin.options = [ft.dropdown.Option(f"{x:02d}") for x in range(0, 24)]
    #     dd_min_fin.options = [ft.dropdown.Option(f"{x:02d}") for x in range(0, 60, 5)]

    #     dd_hora.value = f"{h:02d}"
    #     dd_min.value = f"{mm:02d}"
    #     dd_hora_fin.value = f"{h+1:02d}"
    #     dd_min_fin.value = f"{mm:02d}"

    #     reserva["paciente"] = None
    #     ficha_paciente.visible = False
    #     ficha_paciente.controls.clear()

    #     titulo_reserva.value = "Nueva reserva"

    #     txt_buscar_paciente.value = ""
    #     resultados_pacientes.controls.clear()

    #     reserva["servicio"] = None
    #     dd_servicios.value = None
    #     txt_precio.value = ""
    #     txt_notas.value = ""
    #     txt_empresa_convenio.value = ""
    #     txt_empresa_convenio.visible = False

    #     dd_estado.set_value("reservado")
    #     chk_pagado.value = False

    #     mensaje_error.value = ""
    #     mensaje_error.visible = False

    def abrir_reserva_nueva_desde_slot(e=None):
        dia = slot_actual["fecha"]
        minuto = slot_actual["minuto"]
        if dia is None or minuto is None:
            return

        preparar_reserva_para_slot(dia, minuto)

        # aseguramos estado normal del diálogo de reserva
        restaurar_dialogo_reserva()

        page.dialog = dialogo_reserva
        dialogo_reserva.open = True
        page.open(dialogo_reserva)
        page.update()

    def abrir_bloqueo_desde_slot(e=None):
        dia = slot_actual["fecha"]
        minuto = slot_actual["minuto"]
        if dia is None or minuto is None:
            return

        preparar_bloqueo_nuevo()

        page.dialog = dialogo_bloqueo
        dialogo_bloqueo.open = True
        page.open(dialogo_bloqueo)
        page.update()

    def cerrar_dialogo_opcion_slot(e=None):
        dialogo_opcion_slot.open = False
        page.update()

    dialogo_opcion_slot = ft.AlertDialog(
        modal=True,
        title=ft.Text("Agregar"),
        content=ft.Text("¿Qué deseas agregar en este horario?"),
        actions=[
            ft.TextButton("Reserva", on_click=lambda e: (cerrar_dialogo_opcion_slot(), abrir_reserva_nueva_desde_slot())),
            ft.TextButton("Bloquear horario", on_click=lambda e: (cerrar_dialogo_opcion_slot(), abrir_bloqueo_desde_slot())),
            ft.TextButton("Cerrar", on_click=cerrar_dialogo_opcion_slot),
        ],
    )


    # def click_slot(dia: date, minuto: int):
    #     # Guardamos el slot en estado global
    #     slot_actual["fecha"] = dia
    #     slot_actual["minuto"] = minuto

    #     page.dialog = dialogo_opcion_slot
    #     dialogo_opcion_slot.open = True
    #     page.open(dialogo_opcion_slot)
    #     page.update()

    def click_slot(dia: date, minuto: int):
        # Si vuelven a hacer clic en el mismo slot, lo limpiamos
        if slot_agregar["fecha"] == dia and slot_agregar["minuto"] == minuto:
            limpiar_slot_agregar()
        else:
            slot_agregar["fecha"] = dia
            slot_agregar["minuto"] = minuto

        dibujar_calendario_semanal()

    def preparar_reserva_para_slot(dia: date, minuto: int):
        h = minuto // 60
        mm = minuto % 60

        cita_editando_id["value"] = None

        reserva["fecha"] = dia
        reserva["hora_inicio"] = (h, mm)
        reserva["hora_fin"] = (h + 1, mm)

        txt_fecha.value = dia.strftime("%Y-%m-%d")

        dd_hora.options = [ft.dropdown.Option(f"{x:02d}") for x in range(0, 24)]
        dd_min.options = [ft.dropdown.Option(f"{x:02d}") for x in range(0, 60, 5)]
        dd_hora_fin.options = [ft.dropdown.Option(f"{x:02d}") for x in range(0, 24)]
        dd_min_fin.options = [ft.dropdown.Option(f"{x:02d}") for x in range(0, 60, 5)]

        dd_hora.value = f"{h:02d}"
        dd_min.value = f"{mm:02d}"
        dd_hora_fin.value = f"{h+1:02d}"
        dd_min_fin.value = f"{mm:02d}"

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
        txt_empresa_convenio.value = ""
        txt_empresa_convenio.visible = False

        dd_estado.set_value("reservado")
        chk_pagado.value = False

        mensaje_error.value = ""
        mensaje_error.visible = False
        chk_notificar_email.visible = False
        chk_notificar_email.value = False

        btn_whatsapp_confirmacion.visible = False
        btn_whatsapp_confirmacion.disabled = True
        if btn_whatsapp_confirmacion.page is not None:
            btn_whatsapp_confirmacion.update()

    def abrir_reserva_nueva_desde_slot(dia: date, minuto: int):
        preparar_reserva_para_slot(dia, minuto)
        # aseguramos estado normal del diálogo de reserva
        restaurar_dialogo_reserva()
        page.dialog = dialogo_reserva
        dialogo_reserva.open = True
        page.open(dialogo_reserva)
        page.update()

    def abrir_bloqueo_desde_slot(dia: date, minuto: int):
        slot_actual["fecha"] = dia
        slot_actual["minuto"] = minuto
        preparar_bloqueo_nuevo()
        page.dialog = dialogo_bloqueo
        dialogo_bloqueo.open = True
        page.open(dialogo_bloqueo)
        page.update()

    def limpiar_slot_agregar():
        slot_agregar["fecha"] = None
        slot_agregar["minuto"] = None

    # ----------------- ABRIR CITA EXISTENTE (EDITAR) -------------------

    def parsear_servicio_y_precio(motivo: str):
        nombre_serv = ""
        precio = ""
        if motivo and "Servicio:" in motivo:
            try:
                resto = motivo.split("Servicio:", 1)[1].strip()
                partes = resto.split(" - ")
                if partes:
                    nombre_serv = partes[0].replace("Servicio:", "").strip()
                for p in partes:
                    if "Precio" in p:
                        import re

                        precio_num = re.sub(r"[^\d]", "", p)
                        if precio_num:
                            precio = precio_num
                        break
            except Exception:
                pass
        return nombre_serv, precio

    def abrir_editar_cita(cita_row: dict):
        cita_editando_id["value"] = cita_row["id"]
        cita_editando_row["value"] = cita_row

        dt = datetime.strptime(cita_row["fecha_hora"][:16], "%Y-%m-%d %H:%M")
        dia = dt.date()
        h = dt.hour
        mm = dt.minute

        reserva["fecha"] = dia
        reserva["hora_inicio"] = (h, mm)
        reserva["hora_fin"] = (h + 1, mm)

        txt_fecha.value = dia.strftime("%Y-%m-%d")

        dd_hora.options = [ft.dropdown.Option(f"{x:02d}") for x in range(0, 24)]
        dd_min.options = [ft.dropdown.Option(f"{x:02d}") for x in range(0, 60, 5)]
        dd_hora_fin.options = [ft.dropdown.Option(f"{x:02d}") for x in range(0, 24)]
        dd_min_fin.options = [ft.dropdown.Option(f"{x:02d}") for x in range(0, 60, 5)]

        dd_hora.value = f"{h:02d}"
        dd_min.value = f"{mm:02d}"
        dd_hora_fin.value = f"{h+1:02d}"
        dd_min_fin.value = f"{mm:02d}"

        # Paciente (viene ya junto en el SELECT)
        pac = {
            "documento": cita_row["documento_paciente"],
            "nombre_completo": cita_row["nombre_completo"],
            "telefono": cita_row.get("telefono", ""),
            "email": cita_row.get("email", ""),
        }
        paciente_cita_editando["value"] = pac
        seleccionar_paciente(pac)

        # En edición: mostramos y habilitamos el botón de WhatsApp
        btn_whatsapp_confirmacion.visible = True
        btn_whatsapp_confirmacion.disabled = False
        if btn_whatsapp_confirmacion.page is not None:
            btn_whatsapp_confirmacion.update()

        # En edición: si tiene email, mostramos el checkbox pero desmarcado
        email = (pac.get("email") or "").strip()
        if email:
            chk_notificar_email.visible = True
            chk_notificar_email.value = False
        else:
            chk_notificar_email.visible = False
            chk_notificar_email.value = False

        # Servicio y precio desde "motivo"
        nombre_serv, precio_motivo = parsear_servicio_y_precio(cita_row.get("motivo", ""))

        dd_servicios.value = None
        reserva["servicio"] = None
        for s in servicios:
            if s["nombre"] == nombre_serv:
                dd_servicios.value = str(s["id"])
                reserva["servicio"] = s
                break

        # Actualizar precio y empresa según el servicio
        seleccionar_servicio(None)

        # Sobrescribir precio con el valor guardado en la cita
        precio_db = cita_row.get("precio")
        if precio_db is not None:
            try:
                txt_precio.value = str(int(precio_db))
            except Exception:
                txt_precio.value = str(precio_db)
        elif precio_motivo:
            txt_precio.value = precio_motivo

        estado_raw = (cita_row.get("estado") or "reservado").lower()
        if estado_raw.startswith("confirm"):
            dd_estado.set_value("confirmado")
        elif estado_raw.startswith("no_asist"):
            dd_estado.set_value("no_asistio")
        else:
            dd_estado.set_value("reservado")

        chk_pagado.value = bool(cita_row.get("pagado"))

        txt_notas.value = cita_row.get("notas") or ""

        if chk_notificar_email.page is not None:
            chk_notificar_email.update()

        mensaje_error.value = ""
        mensaje_error.visible = False

        titulo_reserva.value = f"Reserva de {pac['nombre_completo']}"

        # Aseguramos que el diálogo esté en modo "edición normal"
        restaurar_dialogo_reserva()

        page.dialog = dialogo_reserva
        dialogo_reserva.open = True
        page.open(dialogo_reserva)
        page.update()

    # ----------------- CELDAS / COLORES DE CITA -------------------

    def color_por_estado(estado: str):
        e = (estado or "").lower()
        if e.startswith("confirm"):
            return ft.Colors.AMBER_200
        if e.startswith("no_asist"):
            return ft.Colors.RED_200
        return ft.Colors.LIGHT_BLUE_200  # reservado / agendada / default
    
    def color_borde_por_estado(estado: str):
        e = (estado or "").lower()
        if e.startswith("confirm"):
            # un poco más oscuro que el fondo amarillo
            return ft.Colors.AMBER_400
        if e.startswith("no_asist"):
            # más oscuro que el rojo claro
            return ft.Colors.RED_400
        # reservado / default (azul)
        return ft.Colors.LIGHT_BLUE_400

    def construir_celda(
        d: date,
        m: int,
        citas_celda: list[dict],
        bloqueos_celda: list[dict],
    ) -> ft.Container:
        info = horarios_map.get(d.weekday())
        bgcolor = ft.Colors.GREY_200

        if info:
            inicio_min = minutos_desde_medianoche(info["hora_inicio"])
            fin_min = minutos_desde_medianoche(info["hora_fin"])
            if not info["habilitado"] or m < inicio_min or m >= fin_min:
                bgcolor = ft.Colors.GREY_300
        else:
            bgcolor = ft.Colors.GREY_300

        bloques = []
        for cita_row in citas_celda:
            nombre = cita_row["nombre_completo"]
            estado = cita_row.get("estado") or ""
            pagado = cita_row.get("pagado")
            dt = datetime.strptime(cita_row["fecha_hora"][:16], "%Y-%m-%d %H:%M")
            hora_txt = dt.strftime("%H:%M")

            nombre_serv, _ = parsear_servicio_y_precio(cita_row.get("motivo", ""))

            # Precio: columna numérica > motivo
            precio_db = cita_row.get("precio")
            precio_line = ""
            if precio_db is not None:
                try:
                    precio_line = f"{float(precio_db):,.0f}"
                except Exception:
                    precio_line = str(precio_db)
            else:
                _, precio_motivo = parsear_servicio_y_precio(cita_row.get("motivo", ""))
                if precio_motivo:
                    precio_line = precio_motivo

            estado_label = (
                "Reservado"
                if estado in ("", "agendada", "reservado")
                else "Confirmado"
                if estado.startswith("confirm")
                else "No asistió"
                if estado.startswith("no_asist")
                else estado
            )

            tooltip_lines = [
                f"Paciente: {nombre}",
                f"Servicio: {nombre_serv}" if nombre_serv else "",
                f"Hora: {hora_txt}",
                f"Estado: {estado_label}",
            ]
            if precio_line:
                tooltip_lines.append(f"Precio: {precio_line}")
            tooltip_lines.extend(
                [
                    "Pagado" if pagado else "No pagado",
                    f"Teléfono: {cita_row.get('telefono','')}",
                    f"Email: {cita_row.get('email','')}",
                ]
            )
            tooltip = "\n".join(filter(None, tooltip_lines))

            bloque = ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            nombre,
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            nombre_serv or cita_row.get("modalidad", ""),
                            size=10,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(hora_txt, size=10),
                    ],
                    spacing=0,
                    expand=True,  # ocupa la altura del contenedor
                ),
                bgcolor=color_por_estado(estado),
                padding=6,
                border_radius=6,
                alignment=ft.alignment.center_left,
                tooltip=tooltip,
                expand=True,  # hace que la cita “llene” casi todo el slot
                border=ft.border.only(
                    left=ft.BorderSide(4, color_borde_por_estado(estado)),
                ),
                on_click=lambda e, cr=dict(cita_row): abrir_editar_cita(cr),
            )
            bloques.append(bloque)

              # ---- Bloqueos de horario en este slot ----
        for bloq in bloqueos_celda or []:
            dtb = datetime.strptime(bloq["fecha_hora"][:16], "%Y-%m-%d %H:%M")
            hora_txt = dtb.strftime("%H:%M")
            motivo = bloq.get("motivo", "")

            tooltip_bloq = f"Bloqueo de horario\n{hora_txt}\n{motivo}"

            bloque_bloq = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        hora_txt,
                        size=10,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Text(
                        motivo,
                        size=10,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
                spacing=0,
                expand=True,
            ),
            bgcolor=ft.Colors.GREY_400,  # más oscuro para que resalte
            padding=4,
            border_radius=6,
            opacity=0.95,
            border=ft.border.only(
                left=ft.BorderSide(4, ft.Colors.BLACK54),
            ),
            alignment=ft.alignment.center_left,
            tooltip=tooltip_bloq,
            expand=True,  # hace que el bloqueo use casi toda la celda
            on_click=lambda e, br=dict(bloq): abrir_editar_bloqueo(br),
        )
            bloques.append(bloque_bloq)

    # Si hay bloqueos en este slot, el fondo NO debe ser clickeable
    # (solo se puede interactuar con el bloqueo mismo)
        if bloqueos_celda:
            cell_on_click = None
        else:
            cell_on_click = lambda e, dia=d, minuto=m: click_slot(dia, minuto)

     # --------- Slot vacío seleccionado para agregar ---------
        es_slot_agregar = (
            not citas_celda
            and not bloqueos_celda
            and slot_agregar["fecha"] == d
            and slot_agregar["minuto"] == m
        )

        if es_slot_agregar:
            def on_reserva(e):
                limpiar_slot_agregar()
                abrir_reserva_nueva_desde_slot(d, m)

            def on_bloqueo(e):
                limpiar_slot_agregar()
                abrir_bloqueo_desde_slot(d, m)

            def on_cerrar(e=None):
                limpiar_slot_agregar()
                dibujar_calendario_semanal()

            popup_agregar = ft.PopupMenuButton(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.ADD, size=14),
                        ft.Text(
                            "Agregar",
                            size=12,
                            color=ft.Colors.BLUE_700,
                            weight=ft.FontWeight.W_500,
                        ),
                    ],
                    spacing=4,
                    tight=True,
                ),
                items=[
                    ft.PopupMenuItem(
                        icon=ft.Icons.EVENT,
                        text="Reserva",
                        on_click=on_reserva,
                    ),
                    ft.PopupMenuItem(
                        icon=ft.Icons.BLOCK,
                        text="Bloquear horario",
                        on_click=on_bloqueo,
                    ),
                ],
            )

            btn_cerrar = ft.IconButton(
                icon=ft.Icons.CLOSE,
                icon_size=14,
                tooltip="Cerrar",
                style=ft.ButtonStyle(
                    padding=0,
                    shape=ft.CircleBorder(),
                ),
                on_click=on_cerrar,
            )

            return ft.Container(
                width=160,   # el mismo ancho que el resto de slots
                height=50,
                bgcolor=bgcolor,
                border=ft.border.all(0.5, ft.Colors.GREY_400),
                padding=4,
                content=ft.Row(
                    [
                        popup_agregar,
                        btn_cerrar,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )



        return ft.Container(
        width=160,
        height=50,
        bgcolor=bgcolor,
        border=ft.border.all(0.5, ft.Colors.GREY_400),
        padding=1,
        content=ft.Column(
            bloques,
            spacing=2,
            expand=True,
        ),
        on_click=cell_on_click,
    )

    # ----------------- AGENDA SEMANAL -------------------

    def dibujar_calendario_semanal():
        dias = obtener_dias_semana(semana_lunes["value"])
        intervalo = slot_minutes["value"]
        start_min = START_HOUR * 60
        end_min = END_HOUR * 60
        minutos = list(range(start_min, end_min + 1, intervalo))

        inicio_dt = datetime.combine(dias[0], datetime.min.time())
        fin_dt = datetime.combine(dias[-1], datetime.max.time())
        citas_rows = listar_citas_con_paciente_rango(
            inicio_dt.strftime("%Y-%m-%d %H:%M"),
            fin_dt.strftime("%Y-%m-%d %H:%M"),
        )
        citas_rows = [dict(r) for r in citas_rows]

         # --------- Bloqueos en el mismo rango ---------
        bloqueos_rows = listar_bloqueos_rango(
            inicio_dt.strftime("%Y-%m-%d %H:%M"),
            fin_dt.strftime("%Y-%m-%d %H:%M"),
        )
        bloqueos_rows = [dict(b) for b in bloqueos_rows]

        bloqueos_por_celda: dict[tuple[date, int], list[dict]] = {}
        for b in bloqueos_rows:
            dtb = datetime.strptime(b["fecha_hora"][:16], "%Y-%m-%d %H:%M")
            fecha_d = dtb.date()
            total_min = dtb.hour * 60 + dtb.minute
            if total_min < start_min or total_min > end_min:
                continue
            slot_idx = (total_min - start_min) // intervalo
            slot_min = start_min + slot_idx * intervalo
            key = (fecha_d, slot_min)
            bloqueos_por_celda.setdefault(key, []).append(b)

        citas_por_celda: dict[tuple[date, int], list[dict]] = {}
        for c in citas_rows:
            dt = datetime.strptime(c["fecha_hora"][:16], "%Y-%m-%d %H:%M")
            fecha_d = dt.date()
            total_min = dt.hour * 60 + dt.minute
            if total_min < start_min or total_min > end_min:
                continue
            slot_idx = (total_min - start_min) // intervalo
            slot_min = start_min + slot_idx * intervalo
            key = (fecha_d, slot_min)
            citas_por_celda.setdefault(key, []).append(c)

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
                cells.append(
                    construir_celda(
                        d,
                        m,
                        citas_por_celda.get((d, m), []),
                        bloqueos_por_celda.get((d, m), []),
                    )
                )
            cells.append(ft.Container(width=10))
            filas.append(ft.Row(cells))

        calendario_semanal_col.controls = filas
        page.update()

    # ----------------- MINI CALENDARIO Y NAVEGACIÓN -------------------

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
            fila = celdas[i: i + 7]
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

    # ----------------- CONTROLES MINI CALENDARIO -------------------

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
