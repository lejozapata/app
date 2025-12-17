import re
import flet as ft
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, available_timezones

from db import (
    obtener_configuracion_profesional,
    guardar_configuracion_profesional,
    obtener_horarios_atencion,
    guardar_horarios_atencion,
    listar_servicios,
    crear_servicio,
    actualizar_servicio,
    eliminar_servicio,
    obtener_configuracion_facturacion,
    guardar_configuracion_facturacion,
    listar_empresas_convenio,
    obtener_configuracion_gmail,
    guardar_configuracion_gmail,
)

BANCOS_CO = [
    "Bancolombia",
    "Banco de Bogotá",
    "Davivienda",
    "Banco de Occidente",
    "Banco Popular",
    "BBVA Colombia",
    "Scotiabank Colpatria",
    "Banco Caja Social",
    "Banco AV Villas",
    "Itaú",
    "Banco Agrario",
    "Banco Falabella",
    "Banco Pichincha",
    "Bancoomeva",
    "Banco GNB Sudameris",
    "Citibank",
    "Nequi",
    "Daviplata",
    "RappiPay",
]


def formatear_telefono_display(telefono: str | None) -> str:
    """
    Recibe un teléfono y lo devuelve con formato básico (XXX XXX XXXX).
    Si no hay teléfono, devuelve cadena vacía.
    """
    if not telefono:
        return ""

    digits = re.sub(r"\D", "", telefono)

    # Limitar a 10 dígitos (ej. celular colombiano)
    digits = digits[:10]

    # Aplica formato XXX XXX XXXX
    if len(digits) <= 3:
        return digits
    elif len(digits) <= 6:
        return f"{digits[:3]} {digits[3:]}"
    else:
        return f"{digits[:3]} {digits[3:6]} {digits[6:]}"


def build_timezone_options() -> list[ft.dropdown.Option]:
    """Genera opciones de zona horaria basadas en zoneinfo.

    Filtra zonas de América y construye etiquetas tipo:
      (GMT-05:00) Bogota
    """
    now_utc = datetime.now(timezone.utc)
    opciones: list[ft.dropdown.Option] = []

    try:
        for tz_name in sorted(available_timezones()):
            if not tz_name.startswith("America/"):
                continue

            tz = ZoneInfo(tz_name)
            offset = now_utc.astimezone(tz).utcoffset()
            if offset is None:
                continue

            total_minutes = int(offset.total_seconds() // 60)
            sign = "+" if total_minutes >= 0 else "-"
            total_minutes = abs(total_minutes)
            hours, minutes = divmod(total_minutes, 60)

            label = f"(GMT{sign}{hours:02d}:{minutes:02d}) {tz_name.split('/')[-1].replace('_', ' ')}"
            opciones.append(ft.dropdown.Option(tz_name, label))
    except Exception:
        # Fallback sencillo si hay algún problema con zoneinfo
        opciones = [ft.dropdown.Option("America/Bogota", "(GMT-05:00) Bogota")]

    # Asegurar al menos Bogotá
    if not any("Bogota" in o.text or "Bogotá" in o.text for o in opciones):
        opciones.insert(0, ft.dropdown.Option("America/Bogota", "(GMT-05:00) Bogota"))

    return opciones


def build_admin_view(page: ft.Page) -> ft.Control:
    """Vista de administración / configuración."""

    # ---------------- Cargar datos desde BD ---------

    cfg = obtener_configuracion_profesional()
    horarios = obtener_horarios_atencion()
    cfg_fact = obtener_configuracion_facturacion()
    cfg_gmail = obtener_configuracion_gmail()

    seccion_activa = {"value": "profesional"}  # "profesional" | "servicios"

    # -------- Formateo de teléfono mientras se escribe --------

    def formatear_numero_telefono(e):
        e.control.value = formatear_telefono_display(e.control.value)
        e.control.update()

    # =====================================================================
    #                         SECCIÓN PROFESIONAL
    # =====================================================================

    # -------- Datos básicos del profesional --------

    txt_nombre = ft.TextField(
        label="Nombre del profesional",
        value=cfg.get("nombre_profesional") or "",
        width=400,
    )

    txt_direccion = ft.TextField(
        label="Dirección del local",
        value=cfg.get("direccion") or "",
        width=500,
    )

    zona_opciones = build_timezone_options()

    cfg_tz = cfg.get("zona_horaria")
    if cfg_tz and any(o.key == cfg_tz for o in zona_opciones):
        tz_value = cfg_tz
    else:
        tz_value = next(
            (o.key for o in zona_opciones if "Bogota" in o.key or "Bogotá" in o.key),
            zona_opciones[0].key,
        )

    dd_zona_horaria = ft.Dropdown(
        label="Zona horaria",
        width=300,
        options=zona_opciones,
        value=tz_value,
    )

    telefono_cfg = cfg.get("telefono") or ""

    txt_telefono = ft.TextField(
        label="Teléfono",
        value=formatear_telefono_display(telefono_cfg),
        width=250,
        on_change=formatear_numero_telefono,
    )

    txt_email = ft.TextField(
        label="Email",
        value=cfg.get("email") or "",
        width=300,
    )


    # -------- Envío de correos (Gmail) --------

    txt_gmail_user = ft.TextField(
        label="Correo Gmail para enviar notificaciones",
        value=(cfg_gmail.get("gmail_user") or ""),
        width=350,
        helper_text="Debe ser una cuenta Gmail con clave de aplicación (App Password).",
    )

    txt_gmail_app_password = ft.TextField(
        label="Clave de aplicación de Gmail",
        value="",  # No precargamos el secreto por seguridad
        width=350,
        password=True,
        can_reveal_password=False,
        helper_text=(
            "Ya hay una clave guardada. Deja este campo en blanco para conservarla."
            if cfg_gmail.get("tiene_password") else
            "En Gmail: Seguridad -> Contraseñas de aplicaciones."
        ),
    )

    sw_habilitar_email = ft.Switch(
        label="Habilitar envío de correos (Gmail)",
        value=bool(cfg_gmail.get("habilitado")),
    )


    # -------- Información complementaria para facturación --------

    dd_banco = ft.Dropdown(
        label="Banco",
        width=300,
        options=[ft.dropdown.Option(b) for b in BANCOS_CO],
        value=cfg_fact.get("banco") if cfg_fact.get("banco") in BANCOS_CO else None,
    )

    chk_benef_mismo = ft.Checkbox(
        label="El beneficiario es el mismo profesional",
        value=bool(
            cfg_fact.get("beneficiario")
            and cfg_fact.get("beneficiario") == (cfg.get("nombre_profesional") or "")
        ),
    )

    txt_beneficiario = ft.TextField(
        label="Beneficiario",
        value=cfg_fact.get("beneficiario") or (cfg.get("nombre_profesional") or ""),
        width=400,
    )

    txt_nit_cc = ft.TextField(
        label="NIT / CC para facturar",
        value=cfg_fact.get("nit") or "",
        width=250,
    )

    dd_forma_pago = ft.Dropdown(
        label="Forma de pago",
        width=250,
        options=[
            ft.dropdown.Option("Transferencia bancaria"),
            ft.dropdown.Option("Efectivo"),
            ft.dropdown.Option("Cheque"),
        ],
        value=cfg_fact.get("forma_pago") or "Transferencia bancaria",
    )

    txt_numero_cuenta = ft.TextField(
        label="Número de cuenta",
        value=cfg_fact.get("numero_cuenta") or "",
        width=250,
    )

    def actualizar_beneficiario_desde_profesional():
        if chk_benef_mismo.value:
            txt_beneficiario.value = txt_nombre.value.strip()
            txt_beneficiario.disabled = True
        else:
            txt_beneficiario.disabled = False
        if txt_beneficiario.page is not None:
            txt_beneficiario.update()

    def on_cambio_chk_benef(e):
        actualizar_beneficiario_desde_profesional()

    chk_benef_mismo.on_change = on_cambio_chk_benef

    def on_cambio_nombre_prof(e):
        if chk_benef_mismo.value:
            txt_beneficiario.value = txt_nombre.value.strip()
            if txt_beneficiario.page is not None:
                txt_beneficiario.update()

    txt_nombre.on_change = on_cambio_nombre_prof

    def actualizar_estado_numero_cuenta():
        es_transferencia = (dd_forma_pago.value or "").strip().lower() == "transferencia bancaria"

        # Número de cuenta
        txt_numero_cuenta.disabled = not es_transferencia
        txt_numero_cuenta.visible  = es_transferencia
        if not es_transferencia:
            txt_numero_cuenta.value = ""  # opcional, para evitar guardar basura

        # Banco
        dd_banco.disabled = not es_transferencia
        dd_banco.visible  = es_transferencia
        if not es_transferencia:
            dd_banco.value = None  # opcional

        if txt_numero_cuenta.page is not None:
            txt_numero_cuenta.update()
        if dd_banco.page is not None:
            dd_banco.update()

    def on_cambio_forma_pago(e):
        actualizar_estado_numero_cuenta()

    dd_forma_pago.on_change = on_cambio_forma_pago

    # Inicializar estados de beneficiario y cuenta
    actualizar_beneficiario_desde_profesional()
    actualizar_estado_numero_cuenta()

    # -------- Horario por día --------

    nombres_dias = [
        "Lunes",
        "Martes",
        "Miércoles",
        "Jueves",
        "Viernes",
        "Sábado",
        "Domingo",
    ]

    filas_horario: list[dict] = []

    opciones_horas = [f"{h:02d}" for h in range(0, 24)]
    opciones_minutos = [f"{m:02d}" for m in range(0, 60, 5)]

    horarios_por_dia = {h["dia"]: h for h in horarios}

    def parse_hora(hora_str: str):
        try:
            hh, mm = hora_str.split(":")
            return hh, mm
        except Exception:
            return "08", "00"

    for dia_idx, nombre_dia in enumerate(nombres_dias):
        h_conf = horarios_por_dia.get(
            dia_idx,
            {"habilitado": False, "hora_inicio": "08:00", "hora_fin": "17:00"},
        )
        ini_hh, ini_mm = parse_hora(h_conf["hora_inicio"])
        fin_hh, fin_mm = parse_hora(h_conf["hora_fin"])

        sw_activo = ft.Switch(value=h_conf["habilitado"])

        dd_ini_hora = ft.Dropdown(
            width=80,
            text_style=ft.TextStyle(size=14),
            options=[ft.dropdown.Option(h) for h in opciones_horas],
            value=ini_hh,
            menu_height=250,
        )
        dd_ini_min = ft.Dropdown(
            width=80,
            text_style=ft.TextStyle(size=14),
            options=[ft.dropdown.Option(m) for m in opciones_minutos],
            value=ini_mm,
            menu_height=250,
        )
        dd_fin_hora = ft.Dropdown(
            width=80,
            text_style=ft.TextStyle(size=14),
            options=[ft.dropdown.Option(h) for h in opciones_horas],
            value=fin_hh,
            menu_height=250,
        )
        dd_fin_min = ft.Dropdown(
            width=80,
            text_style=ft.TextStyle(size=14),
            options=[ft.dropdown.Option(m) for m in opciones_minutos],
            value=fin_mm,
            menu_height=250,
        )

        cont_ini_dd = ft.Row([dd_ini_hora, dd_ini_min], spacing=5, width=200)
        cont_fin_dd = ft.Row([dd_fin_hora, dd_fin_min], spacing=5, width=200)

        lbl_ini_cerrado = ft.Text("Cerrado", width=200, color=ft.Colors.GREY_600)
        lbl_fin_cerrado = ft.Text("Cerrado", width=200, color=ft.Colors.GREY_600)

        fila = {
            "dia": dia_idx,
            "nombre": nombre_dia,
            "switch": sw_activo,
            "ini_hora": dd_ini_hora,
            "ini_min": dd_ini_min,
            "fin_hora": dd_fin_hora,
            "fin_min": dd_fin_min,
            "cont_ini_dd": cont_ini_dd,
            "cont_fin_dd": cont_fin_dd,
            "lbl_ini_cerrado": lbl_ini_cerrado,
            "lbl_fin_cerrado": lbl_fin_cerrado,
        }

        def actualizar_visibilidad(e=None, fila_ref=fila):
            activo = fila_ref["switch"].value
            fila_ref["cont_ini_dd"].visible = activo
            fila_ref["cont_fin_dd"].visible = activo
            fila_ref["lbl_ini_cerrado"].visible = not activo
            fila_ref["lbl_fin_cerrado"].visible = not activo
            if page is not None and page.controls:
                page.update()

        sw_activo.on_change = lambda e, fila_ref=fila: actualizar_visibilidad(
            e, fila_ref=fila_ref
        )
        actualizar_visibilidad(fila_ref=fila)

        filas_horario.append(fila)

    filas_visual_horario: list[ft.Control] = []
    filas_visual_horario.append(
        ft.Row(
            [
                ft.Text("Día", width=120, weight="bold"),
                ft.Text("Estado", width=80, weight="bold"),
                ft.Text("Inicio de la jornada", width=200, weight="bold"),
                ft.Text("Fin de la jornada", width=200, weight="bold"),
            ],
            spacing=10,
        )
    )

    for f in filas_horario:
        filas_visual_horario.append(
            ft.Row(
                [
                    ft.Text(f["nombre"], width=120),
                    ft.Container(f["switch"], width=80),
                    ft.Stack([f["cont_ini_dd"], f["lbl_ini_cerrado"]], width=200),
                    ft.Stack([f["cont_fin_dd"], f["lbl_fin_cerrado"]], width=200),
                ],
                spacing=10,
            )
        )

    def hora_a_minutos(hora_str: str) -> int:
        try:
            hh, mm = hora_str.split(":")
            return int(hh) * 60 + int(mm)
        except Exception:
            return 0

    mensaje_profesional = ft.Text(
        "",
        color=ft.Colors.GREEN_700,
        size=12,
    )

    async def limpiar_mensaje_profesional():
        await asyncio.sleep(3)
        mensaje_profesional.value = ""
        if mensaje_profesional.page is not None:
            mensaje_profesional.update()

    def guardar_profesional(e):
        dias_activos = [str(f["dia"]) for f in filas_horario if f["switch"].value]
        dias_str = ",".join(dias_activos) if dias_activos else ""

        horas_inicio = []
        horas_fin = []
        lista_horarios = []

        for f in filas_horario:
            ini = f"{f['ini_hora'].value or '08'}:{f['ini_min'].value or '00'}"
            fin = f"{f['fin_hora'].value or '17'}:{f['fin_min'].value or '00'}"

            lista_horarios.append(
                {
                    "dia": f["dia"],
                    "habilitado": f["switch"].value,
                    "hora_inicio": ini,
                    "hora_fin": fin,
                }
            )

            if f["switch"].value:
                horas_inicio.append(ini)
                horas_fin.append(fin)

        if horas_inicio and horas_fin:
            hora_inicio_global = min(horas_inicio, key=hora_a_minutos)
            hora_fin_global = max(horas_fin, key=hora_a_minutos)
        else:
            hora_inicio_global = cfg.get("hora_inicio") or "07:00"
            hora_fin_global = cfg.get("hora_fin") or "21:00"

        telefono_raw = txt_telefono.value or ""
        telefono_limpio = re.sub(r"\D", "", telefono_raw)

        nuevo_cfg = {
            "nombre_profesional": txt_nombre.value.strip() or None,
            "hora_inicio": hora_inicio_global,
            "hora_fin": hora_fin_global,
            "dias_atencion": dias_str or "1,2,3,4,5",
            "direccion": txt_direccion.value.strip() or None,
            "zona_horaria": dd_zona_horaria.value,
            "telefono": telefono_limpio or None,
            "email": txt_email.value.strip() or None,
        }

        guardar_configuracion_profesional(nuevo_cfg)
        guardar_horarios_atencion(lista_horarios)

        # ---- Configuración de facturación ----
        cfg_fact_actual = obtener_configuracion_facturacion()

        cfg_fact_guardar = {
            "prefijo_factura": cfg_fact_actual.get("prefijo_factura", "PS"),
            "ultimo_consecutivo": cfg_fact_actual.get("ultimo_consecutivo", 0),
            "banco": dd_banco.value,
            "beneficiario": (txt_beneficiario.value or "").strip() or None,
            "nit": (txt_nit_cc.value or "").strip() or None,
            "numero_cuenta": (
                (txt_numero_cuenta.value or "").strip()
                if dd_forma_pago.value == "Transferencia bancaria"
                else None
            ),
            "forma_pago": dd_forma_pago.value,
            "notas": cfg_fact_actual.get("notas"),
        }

        guardar_configuracion_facturacion(cfg_fact_guardar)

        # ---- Configuración Gmail (notificaciones) ----
        cfg_gmail_guardar = {
            "gmail_user": (txt_gmail_user.value or "").strip() or None,
            "gmail_app_password": (txt_gmail_app_password.value or "").strip() or None,
            "habilitado": bool(sw_habilitar_email.value),
        }
        guardar_configuracion_gmail(cfg_gmail_guardar)

        page.snack_bar = ft.SnackBar(
            content=ft.Text("Configuración de horario y facturación guardada.")
        )
        page.snack_bar.open = True

        mensaje_profesional.value = "Información del profesional guardada correctamente."
        if mensaje_profesional.page is not None:
            mensaje_profesional.update()

        page.run_task(limpiar_mensaje_profesional)
        page.update()

    seccion_profesional = ft.Column(
        [
            ft.Text("Configuración del profesional", size=18, weight="bold"),
            ft.Text(
                "Define tu información de contacto y el horario de atención por día.",
                size=12,
                color=ft.Colors.GREY_700,
            ),
            ft.Divider(),
            txt_nombre,
            ft.Row([txt_direccion], spacing=10),
            ft.Row([dd_zona_horaria, txt_telefono, txt_email], spacing=10),

            ft.Divider(),
            ft.Text("Notificaciones por correo (Gmail)", weight="bold"),
            ft.Text(
                "Configura el correo Gmail y su clave de aplicación para enviar confirmaciones y cancelaciones.",
                size=12,
                color=ft.Colors.GREY_700,
            ),
            ft.Row([txt_gmail_user, txt_gmail_app_password], spacing=10),
            ft.Row([sw_habilitar_email], spacing=10),
            ft.Divider(),
            ft.Text("Información complementaria para facturación", weight="bold"),
            ft.Text(
                "Estos datos se usarán en las facturas y para mostrar la información bancaria al paciente.",
                size=12,
                color=ft.Colors.GREY_700,
            ),
            ft.Row([dd_forma_pago, dd_banco], spacing=10),
            ft.Row([chk_benef_mismo], spacing=10),
            ft.Row([txt_beneficiario, txt_nit_cc], spacing=10),
            ft.Row([txt_numero_cuenta], spacing=10),
            ft.Divider(),
            ft.Text("Horario de inicio y fin de la jornada", weight="bold"),
            ft.Text(
                "Selecciona los días de atención y el horario.",
                size=12,
                color=ft.Colors.GREY_700,
            ),
            ft.Container(
            content=ft.Column(filas_visual_horario, spacing=8),
            padding=10,
            border=ft.border.all(1, ft.Colors.GREY_300),
            border_radius=8,
        ),
        mensaje_profesional,
        ft.Container(
            content=ft.Row(
                [ft.ElevatedButton("Guardar cambios", on_click=guardar_profesional)],
                #alignment=ft.MainAxisAlignment.END,
            ),
            padding=ft.padding.only(bottom=32, top=4),
        ),
    ],
    spacing=15,
    scroll=ft.ScrollMode.AUTO,
    )

    # =====================================================================
    #                         SECCIÓN SERVICIOS
    # =====================================================================

    servicios_table = ft.Column(spacing=10)

    # --- Controles del diálogo de Nuevo Servicio ---

    empresas_convenio = listar_empresas_convenio(True)

    txt_srv_nombre = ft.TextField(label="Nombre del servicio", width=300)

    dd_srv_empresa = ft.Dropdown(
        label="Empresa (si es convenio)",
        width=300,
        disabled=True,
        options=[ft.dropdown.Option(emp["nombre"]) for emp in empresas_convenio],
    )

    def on_cambio_tipo(e):
        # Si es convenio, habilitamos "Empresa", si no, la deshabilitamos
        if dd_srv_tipo.value == "convenio":
            dd_srv_empresa.disabled = False
        else:
            dd_srv_empresa.disabled = True
            dd_srv_empresa.value = ""
        # Solo actualizar si el control ya está montado en la página (diálogo abierto)
        if dd_srv_empresa.page is not None:
            dd_srv_empresa.update()

    dd_srv_tipo = ft.Dropdown(
        label="Tipo",
        width=200,
        options=[ft.dropdown.Option('particular','Particular'), ft.dropdown.Option('convenio','Convenio')],
        on_change=on_cambio_tipo,
    )

    txt_srv_precio = ft.TextField(
        label="Precio",
        width=200,
        hint_text="Ej: 120000",
    )

    # Texto de error dentro del diálogo
    srv_error_text = ft.Text(
        "",
        color=ft.Colors.RED_700,
        size=12,
        visible=False,
    )

    def mostrar_error_servicio(msg: str):
        srv_error_text.value = msg
        srv_error_text.visible = True
        if srv_error_text.page is not None:
            srv_error_text.update()

    # Diálogo principal para crear / editar servicio
    dlg_nuevo_servicio = ft.AlertDialog(
        modal=True,
        content=ft.Column(
            [
                srv_error_text,
                txt_srv_nombre,
                dd_srv_tipo,
                txt_srv_precio,
                dd_srv_empresa,
            ],
            tight=True,
            spacing=10,
        ),
    )

    # Diálogo de confirmación de eliminación
    dlg_confirmar_eliminar = ft.AlertDialog(modal=True)

    def cerrar_dialogo(e=None):
        dlg_nuevo_servicio.open = False
        page.update()

    def cerrar_confirmar_eliminar(e=None):
        dlg_confirmar_eliminar.open = False
        page.update()

    def eliminar_servicio_confirmado(e, servicio_id: int):
        eliminar_servicio(servicio_id)
        dlg_confirmar_eliminar.open = False
        page.update()
        refrescar_servicios()
        page.snack_bar = ft.SnackBar(content=ft.Text("Servicio eliminado."))
        page.snack_bar.open = True
        page.update()

    def confirmar_eliminar_servicio(servicio):
        nombre = servicio["nombre"]
        dlg_confirmar_eliminar.title = ft.Text("Eliminar servicio")
        dlg_confirmar_eliminar.content = ft.Text(
            f"¿Seguro que deseas eliminar el servicio \"{nombre}\"?"
        )
        dlg_confirmar_eliminar.actions = [
            ft.TextButton("Cancelar", on_click=cerrar_confirmar_eliminar),
            ft.ElevatedButton(
                "Eliminar",
                on_click=lambda e, sid=servicio["id"]: eliminar_servicio_confirmado(
                    e, sid
                ),
            ),
        ]
        page.dialog = dlg_confirmar_eliminar
        dlg_confirmar_eliminar.open = True
        page.open(dlg_confirmar_eliminar)
        page.update()

    def refrescar_servicios():
        servicios_table.controls.clear()
        filas = listar_servicios()
        if not filas:
            servicios_table.controls.append(
                ft.Text("No hay servicios configurados todavía.", italic=True)
            )
        else:
            servicios_table.controls.append(
                ft.Row(
                    [
                        ft.Text("Nombre", weight="bold", width=220),
                        ft.Text("Tipo", weight="bold", width=140),
                        ft.Text("Precio", weight="bold", width=100),
                        ft.Text("Empresa", weight="bold", width=180),
                        ft.Container(width=120),
                    ],
                    spacing=10,
                )
            )

            for s in filas:
                precio = s["precio"]
                try:
                    precio_txt = f"${precio:,.0f}"
                except Exception:
                    precio_txt = str(precio)

                fila = ft.Row(
                    [
                        ft.Text(s["nombre"], width=220),
                        ft.Text(s.get("modalidad") or s.get("tipo",""), width=140),
                        ft.Text(precio_txt, width=100),
                        ft.Text(s["empresa"] or "", width=180),
                        ft.Row(
                            [
                                ft.IconButton(
                                    icon=ft.Icons.EDIT,
                                    tooltip="Editar servicio",
                                    on_click=lambda e, servicio=s: editar_servicio_handler(
                                        servicio
                                    ),
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.DELETE,
                                    tooltip="Eliminar",
                                    on_click=lambda e, servicio=s: confirmar_eliminar_servicio(
                                        servicio
                                    ),
                                ),
                            ],
                            spacing=5,
                            width=120,
                        ),
                    ],
                    spacing=10,
                )
                servicios_table.controls.append(fila)

        if servicios_table.page is not None:
            servicios_table.update()

    def editar_servicio_handler(servicio):
        # Limpiar errores previos
        srv_error_text.value = ""
        srv_error_text.visible = False

        # Cargar datos en campos
        txt_srv_nombre.value = servicio["nombre"]
        dd_srv_tipo.value = servicio.get("modalidad") or servicio.get("tipo")
        txt_srv_precio.value = str(int(servicio["precio"]))

        if (servicio.get("modalidad") or servicio.get("tipo")) == "convenio":
            dd_srv_empresa.disabled = False
            dd_srv_empresa.value = servicio["empresa"] or ""
        else:
            dd_srv_empresa.disabled = True
            dd_srv_empresa.value = ""

        # Cambiamos apariencia del diálogo
        dlg_nuevo_servicio.title = ft.Text("Editar servicio")

        # Cambiamos acciones
        dlg_nuevo_servicio.actions = [
            ft.TextButton("Cancelar", on_click=cerrar_dialogo),
            ft.ElevatedButton(
                "Actualizar",
                on_click=lambda e, servicio=servicio: actualizar_servicio_handler(
                    e, servicio
                ),
            ),
        ]

        # Abrir diálogo
        dlg_nuevo_servicio.open = True
        page.open(dlg_nuevo_servicio)
        page.update()

    def actualizar_servicio_handler(e, servicio):
        nombre = (txt_srv_nombre.value or "").strip()
        modalidad = dd_srv_tipo.value or "particular"
        empresa = (dd_srv_empresa.value or "").strip()

        if not nombre:
            mostrar_error_servicio("El nombre del servicio es obligatorio.")
            return

        if modalidad == "convenio" and not empresa:
            mostrar_error_servicio(
                "Debes ingresar el nombre de la empresa del convenio."
            )
            return

        try:
            precio = float(
                (txt_srv_precio.value or "").replace(".", "").replace(",", "").strip()
            )
            if precio <= 0:
                raise ValueError()
        except Exception:
            mostrar_error_servicio("Precio inválido. Usa solo números.")
            return

        activo = servicio["activo"] if "activo" in servicio.keys() else 1

        actualizar_servicio(
            servicio["id"],
            nombre=nombre,
            modalidad=modalidad,
            precio=precio,
            empresa=empresa if modalidad == "convenio" else None,
            activo=activo,
        )

        dlg_nuevo_servicio.open = False
        page.update()

        refrescar_servicios()

        page.snack_bar = ft.SnackBar(content=ft.Text("Servicio actualizado."))
        page.snack_bar.open = True
        page.update()

    def guardar_nuevo_servicio(e):
        nombre = (txt_srv_nombre.value or "").strip()
        modalidad = dd_srv_tipo.value or "particular"
        empresa = (dd_srv_empresa.value or "").strip()

        # Limpiar error previo
        srv_error_text.value = ""
        srv_error_text.visible = False

        # Validar nombre
        if not nombre:
            mostrar_error_servicio("El nombre del servicio es obligatorio.")
            return

        # Validar tipo
        if modalidad not in ("particular", "convenio"):
            mostrar_error_servicio("Selecciona una modalidad de servicio válida.")
            return

        # Validar empresa sólo si es convenio
        if modalidad == "convenio" and not empresa:
            mostrar_error_servicio(
                "Para convenios empresariales debes indicar la empresa."
            )
            return

        # Validar precio
        try:
            precio = float(
                (txt_srv_precio.value or "").replace(".", "").replace(",", "").strip()
            )
        except Exception:
            mostrar_error_servicio("Precio inválido. Usa solo números.")
            return

        if precio <= 0:
            mostrar_error_servicio("El precio debe ser mayor que 0.")
            return

        crear_servicio(
            nombre=nombre,
            modalidad=modalidad,
            precio=precio,
            empresa=empresa or None,
        )

        cerrar_dialogo()
        refrescar_servicios()
        page.snack_bar = ft.SnackBar(content=ft.Text("Servicio creado."))
        page.snack_bar.open = True
        page.update()

    def abrir_nuevo_servicio(e):
        # Limpiar campos y errores
        txt_srv_nombre.value = ""
        dd_srv_tipo.value = "particular"
        txt_srv_precio.value = ""
        dd_srv_empresa.value = ""
        dd_srv_empresa.disabled = True
        srv_error_text.value = ""
        srv_error_text.visible = False

        dlg_nuevo_servicio.title = ft.Text("Nuevo servicio")

        dlg_nuevo_servicio.actions = [
            ft.TextButton("Cancelar", on_click=cerrar_dialogo),
            ft.ElevatedButton("Guardar", on_click=guardar_nuevo_servicio),
        ]

        dlg_nuevo_servicio.open = True
        page.open(dlg_nuevo_servicio)
        page.update()

    seccion_servicios = ft.Column(
        [
            ft.Text("Servicios", size=18, weight="bold"),
            ft.Text(
                "Configura los tipos de consulta y sus precios. Estos aparecerán al agendar una cita.",
                size=12,
                color=ft.Colors.GREY_700,
            ),
            ft.Divider(),
            ft.Row(
                [
                    ft.ElevatedButton(
                        "Nuevo servicio", icon=ft.Icons.ADD, on_click=abrir_nuevo_servicio
                    ),
                ],
                alignment=ft.MainAxisAlignment.END,
            ),
            servicios_table,
        ],
        spacing=15,
        scroll=ft.ScrollMode.AUTO,
    )

    refrescar_servicios()

    # =====================================================================
    #                 CONTENEDOR DE SECCIONES + MENÚ IZQ
    # =====================================================================

    contenido_derecha = ft.Container(expand=True)

    tile_profesional = ft.ListTile(
        leading=ft.Icon(ft.Icons.PERSON),
        title=ft.Text("Información del Profesional"),
        selected=True,
        on_click=lambda e: cambiar_seccion("profesional"),
    )

    tile_servicios = ft.ListTile(
        leading=ft.Icon(ft.Icons.MEDICAL_SERVICES),
        title=ft.Text("Servicios"),
        selected=False,
        on_click=lambda e: cambiar_seccion("servicios"),
    )

    def cambiar_seccion(nueva: str):
        seccion_activa["value"] = nueva
        if nueva == "profesional":
            contenido_derecha.content = seccion_profesional
        elif nueva == "servicios":
            contenido_derecha.content = seccion_servicios

        if nueva != "profesional":
            mensaje_profesional.value = ""

        tile_profesional.selected = nueva == "profesional"
        tile_servicios.selected = nueva == "servicios"

        if contenido_derecha.page is not None:
            contenido_derecha.update()
        if tile_profesional.page is not None:
            tile_profesional.update()
            tile_servicios.update()

    cambiar_seccion("profesional")

    menu_izquierdo = ft.Container(
        width=230,
        bgcolor=ft.Colors.WHITE,
        padding=10,
        border_radius=8,
        shadow=ft.BoxShadow(
            blur_radius=8,
            spread_radius=1,
            color=ft.Colors.BLACK12,
            offset=ft.Offset(0, 2),
        ),
        content=ft.Column(
            [
                ft.Text("Configuración", size=16, weight="bold"),
                ft.Divider(),
                tile_profesional,
                tile_servicios,
            ],
            spacing=5,
        ),
    )

    return ft.Row(
        [
            menu_izquierdo,
            ft.Container(width=16),
            contenido_derecha,
        ],
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
