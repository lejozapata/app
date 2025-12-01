import re
import flet as ft
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
)


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
            offset = tz.utcoffset(now_utc)
            if offset is None:
                continue

            total_min = int(offset.total_seconds() // 60)
            sign = "+" if total_min >= 0 else "-"
            total_min = abs(total_min)
            hh = total_min // 60
            mm = total_min % 60

            ciudad = tz_name.split("/")[-1].replace("_", " ")
            label = f"(GMT{sign}{hh:02d}:{mm:02d}) {ciudad}"
            opciones.append(ft.dropdown.Option(label))
    except Exception:
        # Si algo falla, dejamos una lista mínima
        opciones = [ft.dropdown.Option("(GMT-05:00) Bogota")]

    if not opciones:
        opciones = [ft.dropdown.Option("(GMT-05:00) Bogota")]

    return opciones


def formatear_telefono_display(numero: str) -> str:
    # Deja solo dígitos
    digits = "".join(filter(str.isdigit, numero or ""))

    # Limita a 10
    digits = digits[:10]

    # Aplica formato XXX XXX XXXX
    if len(digits) <= 3:
        return digits
    elif len(digits) <= 6:
        return f"{digits[:3]} {digits[3:]}"
    else:
        return f"{digits[:3]} {digits[3:6]} {digits[6:]}"


def build_admin_view(page: ft.Page) -> ft.Control:
    """Vista de administración / configuración."""

    # ---------------- Cargar datos desde BD ----------------

    cfg = obtener_configuracion_profesional()
    horarios = obtener_horarios_atencion()

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
            # Mientras build_admin_view se está ejecutando, el control aún no está en page:
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

        page.snack_bar = ft.SnackBar(
            content=ft.Text("Configuración de horario guardada.")
        )
        page.snack_bar.open = True
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
            ft.ElevatedButton("Guardar cambios", on_click=guardar_profesional),
        ],
        spacing=15,
        scroll=ft.ScrollMode.AUTO,
    )

    # =====================================================================
    #                         SECCIÓN SERVICIOS
    # =====================================================================

    servicios_table = ft.Column(spacing=10)

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
                fila = ft.Row(
                    [
                        ft.Text(s["nombre"], width=220),
                        ft.Text(s["tipo"], width=140),
                        ft.Text(f"${s['precio']:,.0f}", width=100),
                        ft.Text(s["empresa"] or "", width=180),
                        ft.Row(
                            [
                                ft.IconButton(
                                    icon=ft.Icons.EDIT,
                                    tooltip="Editar servicio",
                                    on_click=lambda e, servicio=s: editar_servicio_handler(servicio),
                                    ),
                                ft.IconButton(
                                    icon=ft.Icons.DELETE,
                                    tooltip="Eliminar",
                                    on_click=lambda e, sid=s["id"]: eliminar_servicio_handler(
                                        sid
                                    ),
                                ),
                            ],
                            spacing=0,
                        ),
                    ],
                    spacing=10,
                )
                servicios_table.controls.append(fila)

        if servicios_table.page is not None:
            servicios_table.update()

    def eliminar_servicio_handler(servicio_id: int):
        eliminar_servicio(servicio_id)
        refrescar_servicios()

    def editar_servicio_handler(servicio):
        # Cargar datos en campos
        txt_srv_nombre.value = servicio["nombre"]
        dd_srv_tipo.value = servicio["tipo"]
        txt_srv_precio.value = str(int(servicio["precio"]))
    
        if servicio["tipo"] == "convenio_empresarial":
            txt_srv_empresa.disabled = False
            txt_srv_empresa.value = servicio["empresa"] or ""
        else:
            txt_srv_empresa.disabled = True
            txt_srv_empresa.value = ""

        # Cambiamos apariencia del diálogo
        dlg_nuevo_servicio.title = ft.Text("Editar servicio")

        # Cambiamos acciones
        dlg_nuevo_servicio.actions = [
            ft.TextButton("Cancelar", on_click=cerrar_dialogo),
            ft.ElevatedButton(
            "Actualizar",
            on_click=lambda e, servicio=servicio: actualizar_servicio_handler(e, servicio),
            ),
        ]

        # Abrir diálogo
        dlg_nuevo_servicio.open = True
        page.open(dlg_nuevo_servicio)
        page.update()

    def actualizar_servicio_handler(e, servicio):
        nombre = (txt_srv_nombre.value or "").strip()
        tipo = dd_srv_tipo.value or "presencial"
        empresa = (txt_srv_empresa.value or "").strip()

        if not nombre:
            page.snack_bar = ft.SnackBar(content=ft.Text("El nombre del servicio es obligatorio."))
            page.snack_bar.open = True
            page.update()
            return

        if tipo == "convenio_empresarial" and not empresa:
            page.snack_bar = ft.SnackBar(
            content=ft.Text("Debes ingresar el nombre de la empresa del convenio.")
            )
            page.snack_bar.open = True
            page.update()
            return

        try:
            precio = float(
            (txt_srv_precio.value or "").replace(".", "").replace(",", "").strip()
            )
            if precio <= 0:
                raise ValueError()
        except Exception:
            page.snack_bar = ft.SnackBar(content=ft.Text("Precio inválido."))
            page.snack_bar.open = True
            page.update()
            return

        # Conservamos el estado actual del servicio (activo / inactivo)
        activo = servicio["activo"] if "activo" in servicio.keys() else 1

        actualizar_servicio(
        servicio["id"],
        nombre=nombre,
        tipo=tipo,
        precio=precio,
        empresa=empresa if tipo == "convenio_empresarial" else None,
        activo=activo,
    )

        dlg_nuevo_servicio.open = False
        page.update()

        refrescar_servicios()

        page.snack_bar = ft.SnackBar(content=ft.Text("Servicio actualizado."))
        page.snack_bar.open = True
        page.update()



    # --- Controles del diálogo de Nuevo Servicio ---

    txt_srv_nombre = ft.TextField(label="Nombre del servicio", width=300)

    txt_srv_empresa = ft.TextField(
        label="Empresa (si es convenio)", width=300, disabled=True
    )

    def on_cambio_tipo(e):
        # Si es convenio, habilitamos "Empresa", si no, la deshabilitamos
        if dd_srv_tipo.value == "convenio_empresarial":
            txt_srv_empresa.disabled = False
        else:
            txt_srv_empresa.disabled = True
            txt_srv_empresa.value = ""
        # Solo actualizar si el control ya está montado en la página (diálogo abierto)
        if txt_srv_empresa.page is not None:
            txt_srv_empresa.update()

    dd_srv_tipo = ft.Dropdown(
        label="Tipo",
        width=200,
        options=[
            ft.dropdown.Option("presencial"),
            ft.dropdown.Option("virtual"),
            ft.dropdown.Option("convenio_empresarial"),
        ],
        on_change=on_cambio_tipo,
    )

    txt_srv_precio = ft.TextField(
        label="Precio",
        width=200,
        hint_text="Ej: 120000",
    )

    # Diálogo con contenido (los 4 campos)
    dlg_nuevo_servicio = ft.AlertDialog(
        modal=True,
        content=ft.Column(
        [
            txt_srv_nombre,
            dd_srv_tipo,
            txt_srv_precio,
            txt_srv_empresa,
        ],
        tight=True,
        spacing=10,
    ),
    )

    def cerrar_dialogo(e=None):
        dlg_nuevo_servicio.open = False
        page.update()

    def guardar_nuevo_servicio(e):
        nombre = (txt_srv_nombre.value or "").strip()
        tipo = dd_srv_tipo.value or "presencial"
        empresa = (txt_srv_empresa.value or "").strip()

        # Validar nombre
        if not nombre:
            page.snack_bar = ft.SnackBar(
                content=ft.Text("El nombre del servicio es obligatorio.")
            )
            page.snack_bar.open = True
            page.update()
            return

        # Validar tipo
        if tipo not in ("presencial", "virtual", "convenio_empresarial"):
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Selecciona un tipo de servicio válido.")
            )
            page.snack_bar.open = True
            page.update()
            return

        # Validar empresa sólo si es convenio
        if tipo == "convenio_empresarial" and not empresa:
            page.snack_bar = ft.SnackBar(
                content=ft.Text(
                    "Para convenios empresariales debes indicar el nombre de la empresa."
                )
            )
            page.snack_bar.open = True
            page.update()
            return

        # Validar precio
        try:
            precio = float(
                (txt_srv_precio.value or "").replace(".", "").replace(",", "").strip()
            )
        except Exception:
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Precio inválido. Usa solo números.")
            )
            page.snack_bar.open = True
            page.update()
            return

        if precio <= 0:
            page.snack_bar = ft.SnackBar(
                content=ft.Text("El precio debe ser mayor que 0.")
            )
            page.snack_bar.open = True
            page.update()
            return

        crear_servicio(
            nombre=nombre,
            tipo=tipo,
            precio=precio,
            empresa=empresa or None,
        )

        cerrar_dialogo()
        refrescar_servicios()
        page.snack_bar = ft.SnackBar(content=ft.Text("Servicio creado."))
        page.snack_bar.open = True
        page.update()

    def abrir_nuevo_servicio(e):
        txt_srv_nombre.value = ""
        dd_srv_tipo.value = "presencial"
        txt_srv_precio.value = ""
        txt_srv_empresa.value = ""
        txt_srv_empresa.disabled = True

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

    def cambiar_seccion(nueva: str):
        seccion_activa["value"] = nueva
        if nueva == "profesional":
            contenido_derecha.content = seccion_profesional
        elif nueva == "servicios":
            contenido_derecha.content = seccion_servicios

        # Aquí es donde antes fallaba: sólo actualizamos si ya está montado en la página
        if contenido_derecha.page is not None:
            contenido_derecha.update()

    # Seteamos contenido inicial sin forzar update
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
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.PERSON),
                    title=ft.Text("Información del Profesional"),
                    selected=True,
                    on_click=lambda e: cambiar_seccion("profesional"),
                ),
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.MEDICAL_SERVICES),
                    title=ft.Text("Servicios"),
                    on_click=lambda e: cambiar_seccion("servicios"),
                ),
            ],
            spacing=5,
        ),
    )

    # LAYOUT FINAL
    return ft.Row(
        [
            menu_izquierdo,
            ft.Container(width=16),
            contenido_derecha,
        ],
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
#-----------------------------------------------------------------------------------