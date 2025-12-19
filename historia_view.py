from datetime import date, datetime
from typing import Dict, Any, List
from .historia_pdf import generar_pdf_historia
from .markdown_editor import MarkdownEditor

import flet as ft

from .db import (
    listar_pacientes,
    obtener_paciente,
    obtener_historia_clinica,
    guardar_historia_clinica,
    listar_sesiones_clinicas,
    guardar_sesion_clinica,
    eliminar_sesion_clinica,
    listar_antecedentes_medicos,
    listar_antecedentes_psicologicos,
)


def build_historia_view(page: ft.Page) -> ft.Control:
    """
    Vista de Historia Clínica:
    - Pestaña 1: Historia clínica (una por paciente)
    - Pestaña 2: Sesiones clínicas (múltiples)
    - Pestaña 3: Generar histórico (PDF por rango / completo)
    """

    pacientes_cache: List[Dict[str, Any]] = [dict(p) for p in listar_pacientes()]

    paciente_actual: Dict[str, Any] = {"value": None}
    historia_actual: Dict[str, Any] = {"id": None}
    sesion_editando: Dict[str, Any] = {"id": None}

    # -------------------- Selección de paciente --------------------

    txt_buscar_paciente = ft.TextField(
        label="Buscar paciente (nombre o documento)",
        width=400,
    )

    resultados_pacientes = ft.Column(spacing=0, tight=True)

    lbl_paciente_seleccionado = ft.Text(
        "Selecciona un paciente para ver su historia clínica.",
        size=20,
        weight="bold",
        color=ft.Colors.BLUE_900,
    )

    def _render_nombre_y_doc(p: Dict[str, Any]) -> str:
        return f"{p['nombre_completo']} ({p['documento']})"

    def _seleccionar_paciente(pac_dict: Dict[str, Any]):
        paciente_actual["value"] = pac_dict
        lbl_paciente_seleccionado.value = _render_nombre_y_doc(pac_dict)
        if lbl_paciente_seleccionado.page is not None:
            lbl_paciente_seleccionado.update()

        resultados_pacientes.controls.clear()
        txt_buscar_paciente.value = ""
        if resultados_pacientes.page is not None:
            resultados_pacientes.update()
        if txt_buscar_paciente.page is not None:
            txt_buscar_paciente.update()

        cargar_historia_desde_bd()

        page.update()

    def _filtrar_pacientes(e=None):
        query = (txt_buscar_paciente.value or "").strip().lower()
        resultados_pacientes.controls.clear()

        if not query or len(query) < 2:
            if resultados_pacientes.page is not None:
                resultados_pacientes.update()
            return

        for p in pacientes_cache:
            texto_busqueda = f"{p['nombre_completo']} {p['documento']}".lower()
            if query in texto_busqueda:
                btn = ft.TextButton(
                    _render_nombre_y_doc(p),
                    on_click=lambda ev, pac=p: _seleccionar_paciente(pac),
                )
                resultados_pacientes.controls.append(btn)

        if resultados_pacientes.page is not None:
            resultados_pacientes.update()

    txt_buscar_paciente.on_change = _filtrar_pacientes

    # -------------------- Controles de historia clínica --------------------

    txt_fecha_apertura = ft.TextField(
        label="Fecha de apertura",
        width=150,
        read_only=True,
    )

    dp_apertura = ft.DatePicker(
        first_date=date(2000, 1, 1),
        last_date=date(2100, 12, 31),
    )

    def _on_change_fecha_apertura(e):
        if dp_apertura.value:
            txt_fecha_apertura.value = dp_apertura.value.strftime("%Y-%m-%d")
            if txt_fecha_apertura.page is not None:
                txt_fecha_apertura.update()

    dp_apertura.on_change = _on_change_fecha_apertura

    if dp_apertura not in page.overlay:
        page.overlay.append(dp_apertura)

    def _abrir_dp_apertura(e):
        dp_apertura.open = True
        page.update()

    txt_motivo = ft.TextField(
        label="Motivo de consulta inicial",
        multiline=True,
        min_lines=2,
        max_lines=5,
        width=600,
    )

    txt_info_adicional = ft.TextField(
        label="Información adicional (acudiente, contexto, etc.)",
        multiline=True,
        min_lines=3,
        max_lines=8,
        width=600,
    )

    txt_antec_med = ft.Text(
        "",
        selectable=True,
        size=12,
        color=ft.Colors.GREY_800,
    )
    txt_antec_psico = ft.Text(
        "",
        selectable=True,
        size=12,
        color=ft.Colors.GREY_800,
    )

    mensaje_historia = ft.Text("", size=12, color=ft.Colors.RED_700)

    def cargar_historia_desde_bd():
        pac = paciente_actual["value"]
        if not pac:
            return

        doc = pac["documento"]

        hist = obtener_historia_clinica(doc)
        if hist:
            historia_actual["id"] = hist["id"]
            txt_fecha_apertura.value = hist["fecha_apertura"] or ""
            txt_motivo.value = hist["motivo_consulta_inicial"] or ""
            txt_info_adicional.value = hist["informacion_adicional"] or ""
        else:
            historia_actual["id"] = None
            txt_fecha_apertura.value = date.today().isoformat()
            txt_motivo.value = ""
            txt_info_adicional.value = ""

        meds = listar_antecedentes_medicos(doc)
        psicos = listar_antecedentes_psicologicos(doc)

        txt_antec_med.value = "\n\n".join(
            f"{a['fecha_registro'][:10]} - {a['descripcion']}" for a in meds
        ) or "Sin antecedentes médicos registrados."
        txt_antec_psico.value = "\n\n".join(
            f"{a['fecha_registro'][:10]} - {a['descripcion']}" for a in psicos
        ) or "Sin antecedentes psicológicos registrados."

        for c in [
            txt_fecha_apertura,
            txt_motivo,
            txt_info_adicional,
            txt_antec_med,
            txt_antec_psico,
        ]:
            if c.page is not None:
                c.update()

        cargar_sesiones()

    def guardar_historia(e):
        pac = paciente_actual["value"]
        if not pac:
            mensaje_historia.value = "Debes seleccionar un paciente primero."
            if mensaje_historia.page is not None:
                mensaje_historia.update()
            return

        doc = pac["documento"]
        fecha_ap = txt_fecha_apertura.value or date.today().isoformat()

        datos = {
            "id": historia_actual["id"],
            "documento_paciente": doc,
            "fecha_apertura": fecha_ap,
            "motivo_consulta_inicial": (txt_motivo.value or "").strip() or None,
            "informacion_adicional": (txt_info_adicional.value or "").strip() or None,
        }

        historia_id = guardar_historia_clinica(datos)
        historia_actual["id"] = historia_id

        mensaje_historia.value = "Historia clínica guardada correctamente."
        page.snack_bar = ft.SnackBar(
            content=ft.Text("Historia clínica guardada."),
        )
        page.snack_bar.open = True
        if mensaje_historia.page is not None:
            mensaje_historia.update()
        page.update()

        cargar_sesiones()

    def generar_pdf_historia_click(e):
        pac = paciente_actual["value"]
        if not pac:
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Debes seleccionar un paciente primero.")
            )
            page.snack_bar.open = True
            page.update()
            return

        try:
            generar_pdf_historia(pac["documento"], abrir=True)
            page.snack_bar = ft.SnackBar(
                content=ft.Text("PDF de historia clínica generado.")
            )
        except Exception as ex:
            page.snack_bar = ft.SnackBar(
                content=ft.Text(f"Error al generar el PDF de historia clínica: {ex}")
            )

        page.snack_bar.open = True
        page.update()

    btn_guardar_historia = ft.ElevatedButton(
        "Guardar historia clínica", icon=ft.Icons.SAVE, on_click=guardar_historia
    )

    btn_pdf_historia = ft.ElevatedButton(
        "Generar PDF historia clínica",
        icon=ft.Icons.PICTURE_AS_PDF,
        on_click=generar_pdf_historia_click,
    )

    seccion_historia = ft.Column(
        [
            ft.Text("Historia clínica", size=18, weight="bold"),
            ft.Text(
                "Registra la historia clínica general del paciente. "
                "Los antecedentes médicos y psicológicos se cargan desde el módulo de Pacientes.",
                size=12,
                color=ft.Colors.GREY_700,
            ),
            ft.Divider(),
            lbl_paciente_seleccionado,
            ft.Row(
                [
                    txt_fecha_apertura,
                    ft.IconButton(
                        icon=ft.Icons.CALENDAR_MONTH,
                        tooltip="Cambiar fecha de apertura",
                        on_click=_abrir_dp_apertura,
                    ),
                ],
                spacing=10,
            ),
            txt_motivo,
            txt_info_adicional,
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text("Antecedentes médicos", weight="bold"),
                            ft.Container(
                                txt_antec_med,
                                padding=10,
                                border=ft.border.all(1, ft.Colors.GREY_300),
                                border_radius=8,
                                width=600,
                            ),
                        ],
                        spacing=5,
                    ),
                    ft.Column(
                        [
                            ft.Text("Antecedentes psicológicos", weight="bold"),
                            ft.Container(
                                txt_antec_psico,
                                padding=10,
                                border=ft.border.all(1, ft.Colors.GREY_300),
                                border_radius=8,
                                width=600,
                            ),
                        ],
                        spacing=5,
                    ),
                ],
                spacing=20,
            ),
            mensaje_historia,
            ft.Row(
                [
                    btn_guardar_historia,
                    btn_pdf_historia,
                ],
                alignment=ft.MainAxisAlignment.END,
            ),
        ],
        spacing=12,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )

    # -------------------- Controles de sesiones --------------------

    txt_fecha_sesion = ft.TextField(
        label="Fecha sesión",
        width=150,
        read_only=True,
    )

    dp_sesion = ft.DatePicker(
        first_date=date(2000, 1, 1),
        last_date=date(2100, 12, 31),
    )

    def _on_change_fecha_sesion(e):
        if dp_sesion.value:
            txt_fecha_sesion.value = dp_sesion.value.strftime("%Y-%m-%d")
            if txt_fecha_sesion.page is not None:
                txt_fecha_sesion.update()

    dp_sesion.on_change = _on_change_fecha_sesion
    if dp_sesion not in page.overlay:
        page.overlay.append(dp_sesion)

    def _abrir_dp_sesion(e):
        dp_sesion.open = True
        page.update()

    txt_titulo_sesion = ft.TextField(
        label="Título / encabezado de la sesión",
        width=500,
    )

    txt_contenido_sesion = ft.TextField(
        label="Contenido de la sesión",
        multiline=True,
        min_lines=4,
        max_lines=12,
        width=800,
    )

    md_editor = MarkdownEditor(
        label="Contenido enriquecido",
        width=800,
        preview_width=350,
        min_lines=4,
        max_lines=12,
        page=page,
    )
    md_editor.visible = False

    switch_markdown = ft.Switch(
        label="Modo enriquecido",
        value=False,
    )

    def toggle_markdown_mode(e):
        if switch_markdown.value:
            md_editor.set_value(txt_contenido_sesion.value)
            md_editor.visible = True
            txt_contenido_sesion.visible = False
        else:
            txt_contenido_sesion.value = md_editor.get_value()
            txt_contenido_sesion.visible = True
            md_editor.visible = False

        txt_contenido_sesion.update()
        md_editor.update()

    switch_markdown.on_change = toggle_markdown_mode

    txt_obs_sesion = ft.TextField(
        label="Observaciones / recomendaciones (opcional)",
        multiline=True,
        min_lines=2,
        max_lines=6,
        width=800,
    )

    mensaje_sesion = ft.Text("", size=12, color=ft.Colors.RED_700)

    tabla_sesiones = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Fecha")),
            ft.DataColumn(ft.Text("Título")),
            ft.DataColumn(ft.Text("Acciones")),
        ],
        rows=[],
        column_spacing=16,
    )

    def limpiar_form_sesion():
        sesion_editando["id"] = None
        txt_fecha_sesion.value = date.today().isoformat()
        txt_titulo_sesion.value = ""
        txt_contenido_sesion.value = ""
        txt_obs_sesion.value = ""

        switch_markdown.value = False
        txt_contenido_sesion.visible = True
        md_editor.visible = False
        md_editor.set_value("")

        for c in [
            txt_fecha_sesion,
            txt_titulo_sesion,
            switch_markdown,
            txt_contenido_sesion,
            md_editor,
            txt_obs_sesion,
        ]:
            if c.page is not None:
                c.update()

    def cargar_sesiones():
        tabla_sesiones.rows.clear()
        if not historia_actual["id"]:
            if tabla_sesiones.page is not None:
                tabla_sesiones.update()
            return

        sesiones = listar_sesiones_clinicas(historia_actual["id"])
        for s in sesiones:
            btn_editar = ft.TextButton(
                "Editar",
                on_click=lambda e, ses=s: cargar_sesion_en_form(ses),
            )
            btn_eliminar = ft.TextButton(
                "Eliminar",
                on_click=lambda e, sid=s["id"]: eliminar_sesion_click(sid),
            )
            tabla_sesiones.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(s["fecha"])),
                        ft.DataCell(ft.Text(s["titulo"] if s["titulo"] else "")),
                        ft.DataCell(ft.Row([btn_editar, btn_eliminar], spacing=5)),
                    ]
                )
            )

        if tabla_sesiones.page is not None:
            tabla_sesiones.update()

    def cargar_sesion_en_form(s: Dict[str, Any]):
        sesion_editando["id"] = s["id"]
        txt_fecha_sesion.value = s["fecha"]
        txt_titulo_sesion.value = s["titulo"] or ""

        contenido = s["contenido"] or ""
        txt_contenido_sesion.value = contenido
        txt_contenido_sesion.update()

        md_editor.set_value(contenido)
        md_editor.update()

        txt_obs_sesion.value = s["observaciones"] or ""
        for c in [
            txt_fecha_sesion,
            txt_titulo_sesion,
            switch_markdown,
            txt_contenido_sesion,
            md_editor,
            txt_obs_sesion,
        ]:
            if c.page is not None:
                c.update()

    def eliminar_sesion_click(sesion_id: int):
        eliminar_sesion_clinica(sesion_id)
        page.snack_bar = ft.SnackBar(
            content=ft.Text("Sesión eliminada correctamente."),
        )
        page.snack_bar.open = True
        page.update()
        cargar_sesiones()

    def guardar_sesion(e):
        pac = paciente_actual["value"]
        if not pac:
            mensaje_sesion.value = "Debes seleccionar un paciente primero."
            if mensaje_sesion.page is not None:
                mensaje_sesion.update()
            return

        if not historia_actual["id"]:
            datos_hist = {
                "id": None,
                "documento_paciente": pac["documento"],
                "fecha_apertura": txt_fecha_apertura.value
                or date.today().isoformat(),
                "motivo_consulta_inicial": (txt_motivo.value or "").strip() or None,
                "informacion_adicional": (txt_info_adicional.value or "").strip()
                or None,
            }
            historia_id = guardar_historia_clinica(datos_hist)
            historia_actual["id"] = historia_id

        fecha_sesion = txt_fecha_sesion.value or date.today().isoformat()

        contenido_texto = (
            md_editor.get_value()
            if switch_markdown.value
            else (txt_contenido_sesion.value or "")
        ).strip()

        if not contenido_texto:
            mensaje_sesion.value = "El contenido de la sesión es obligatorio."
            if mensaje_sesion.page is not None:
                mensaje_sesion.update()
            return

        datos_sesion = {
            "id": sesion_editando["id"],
            "historia_id": historia_actual["id"],
            "fecha": fecha_sesion,
            "titulo": (txt_titulo_sesion.value or "").strip() or None,
            "contenido": (
                md_editor.get_value()
                if switch_markdown.value
                else (txt_contenido_sesion.value or "")
            ).strip(),
            "observaciones": (txt_obs_sesion.value or "").strip() or None,
        }

        guardar_sesion_clinica(datos_sesion)

        page.snack_bar = ft.SnackBar(
            content=ft.Text("Sesión clínica guardada correctamente."),
        )
        page.snack_bar.open = True
        page.update()

        limpiar_form_sesion()
        cargar_sesiones()

    btn_guardar_sesion = ft.ElevatedButton(
        "Guardar sesión",
        icon=ft.Icons.SAVE,
        on_click=guardar_sesion,
    )

    seccion_sesiones = ft.Column(
        [
            ft.Text("Sesiones clínicas", size=18, weight="bold"),
            ft.Text(
                "Registra las sesiones asociadas a la historia clínica del paciente.",
                size=12,
                color=ft.Colors.GREY_700,
            ),
            ft.Divider(),
            lbl_paciente_seleccionado,
            ft.Row(
                [
                    txt_fecha_sesion,
                    ft.IconButton(
                        icon=ft.Icons.CALENDAR_MONTH,
                        tooltip="Cambiar fecha de la sesión",
                        on_click=_abrir_dp_sesion,
                    ),
                ],
                spacing=10,
            ),
            txt_titulo_sesion,
            switch_markdown,
            txt_contenido_sesion,
            md_editor,
            txt_obs_sesion,
            mensaje_sesion,
            ft.Row(
                [
                    ft.TextButton("Nueva sesión", on_click=lambda e: limpiar_form_sesion()),
                    btn_guardar_sesion,
                ],
                alignment=ft.MainAxisAlignment.END,
            ),
            ft.Divider(),
            ft.Text("Sesiones registradas", weight="bold"),
            ft.Container(
                height=260,
                content=ft.Column(
                    [tabla_sesiones],
                    scroll=ft.ScrollMode.AUTO,
                ),
            ),
        ],
        spacing=10,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )

    # -------------------- Controles "Generar histórico" --------------------

    rd_modo_historico = ft.RadioGroup(
        value="todo",
        content=ft.Column(
            [
                ft.Radio(value="todo", label="Todo el histórico"),
                ft.Radio(value="rango", label="Por rango de fechas"),
            ],
            spacing=0,
        ),
    )

    txt_fecha_desde_hist = ft.TextField(
        label="Desde",
        width=150,
        read_only=True,
        dense=True,
    )
    txt_fecha_hasta_hist = ft.TextField(
        label="Hasta",
        width=150,
        read_only=True,
        dense=True,
    )

    dp_desde_hist = ft.DatePicker(
        first_date=date(2000, 1, 1),
        last_date=date(2100, 12, 31),
    )
    dp_hasta_hist = ft.DatePicker(
        first_date=date(2000, 1, 1),
        last_date=date(2100, 12, 31),
    )

    def _on_change_fecha_desde_hist(e):
        if dp_desde_hist.value:
            txt_fecha_desde_hist.value = dp_desde_hist.value.strftime("%Y-%m-%d")
            if txt_fecha_desde_hist.page is not None:
                txt_fecha_desde_hist.update()

    def _on_change_fecha_hasta_hist(e):
        if dp_hasta_hist.value:
            txt_fecha_hasta_hist.value = dp_hasta_hist.value.strftime("%Y-%m-%d")
            if txt_fecha_hasta_hist.page is not None:
                txt_fecha_hasta_hist.update()

    dp_desde_hist.on_change = _on_change_fecha_desde_hist
    dp_hasta_hist.on_change = _on_change_fecha_hasta_hist

    if dp_desde_hist not in page.overlay:
        page.overlay.append(dp_desde_hist)
    if dp_hasta_hist not in page.overlay:
        page.overlay.append(dp_hasta_hist)

    def _abrir_dp_desde_hist(e):
        dp_desde_hist.open = True
        page.update()

    def _abrir_dp_hasta_hist(e):
        dp_hasta_hist.open = True
        page.update()

    def generar_historico_click(e):
        pac = paciente_actual["value"]
        if not pac:
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Debes seleccionar un paciente primero.")
            )
            page.snack_bar.open = True
            page.update()
            return

        modo = rd_modo_historico.value or "todo"

        fecha_desde = None
        fecha_hasta = None

        if modo == "rango":
            if not txt_fecha_desde_hist.value or not txt_fecha_hasta_hist.value:
                page.snack_bar = ft.SnackBar(
                    content=ft.Text("Debes seleccionar el rango de fechas (desde y hasta).")
                )
                page.snack_bar.open = True
                page.update()
                return

            try:
                fecha_desde = datetime.strptime(
                    txt_fecha_desde_hist.value, "%Y-%m-%d"
                ).date()
                fecha_hasta = datetime.strptime(
                    txt_fecha_hasta_hist.value, "%Y-%m-%d"
                ).date()
            except ValueError:
                page.snack_bar = ft.SnackBar(
                    content=ft.Text("Las fechas del histórico no tienen un formato válido.")
                )
                page.snack_bar.open = True
                page.update()
                return

        try:
            if modo == "todo":
                generar_pdf_historia(pac["documento"], abrir=True)
            else:
                generar_pdf_historia(
                    pac["documento"],
                    abrir=True,
                    fecha_desde=fecha_desde,
                    fecha_hasta=fecha_hasta,
                )

            page.snack_bar = ft.SnackBar(
                content=ft.Text("Histórico generado correctamente.")
            )
        except Exception as ex:
            page.snack_bar = ft.SnackBar(
                content=ft.Text(f"Error al generar el histórico: {ex}")
            )

        page.snack_bar.open = True
        page.update()

    seccion_historico = ft.Column(
        [
            ft.Text("Generar histórico de historia clínica", size=18, weight="bold"),
            ft.Text(
                "Genera el PDF de la historia clínica completa o filtrada por rango de fechas, "
                "según las sesiones registradas.",
                size=12,
                color=ft.Colors.GREY_700,
            ),
            ft.Divider(),
            lbl_paciente_seleccionado,
            ft.Divider(),
            ft.Text("Modo de generación", weight="bold"),
            rd_modo_historico,
            ft.Row(
                [
                    ft.Row(
                        [
                            txt_fecha_desde_hist,
                            ft.IconButton(
                                icon=ft.Icons.CALENDAR_MONTH,
                                tooltip="Fecha desde",
                                on_click=_abrir_dp_desde_hist,
                            ),
                        ],
                        spacing=4,
                    ),
                    ft.Row(
                        [
                            txt_fecha_hasta_hist,
                            ft.IconButton(
                                icon=ft.Icons.CALENDAR_MONTH,
                                tooltip="Fecha hasta",
                                on_click=_abrir_dp_hasta_hist,
                            ),
                        ],
                        spacing=4,
                    ),
                ],
                spacing=20,
            ),
            ft.Text(
                "Si eliges 'Todo el histórico', se incluirán todas las sesiones del paciente. "
                "Si eliges 'Por rango de fechas', solo las comprendidas entre las fechas indicadas.",
                size=11,
                color=ft.Colors.GREY_700,
            ),
            ft.Divider(),
            ft.Row(
                [
                    ft.ElevatedButton(
                        "Generar histórico",
                        icon=ft.Icons.PICTURE_AS_PDF,
                        on_click=generar_historico_click,
                    ),
                ],
                alignment=ft.MainAxisAlignment.END,
            ),
        ],
        spacing=12,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )

    # -------------------- Menú lateral y contenido --------------------

    contenido_derecha = ft.Container(expand=True)

    tile_historia = ft.ListTile(
        leading=ft.Icon(ft.Icons.DESCRIPTION),
        title=ft.Text("Historia clínica"),
        selected=True,
        on_click=lambda e: cambiar_seccion("historia"),
    )

    tile_sesiones = ft.ListTile(
        leading=ft.Icon(ft.Icons.LIST),
        title=ft.Text("Sesiones clínicas"),
        selected=False,
        on_click=lambda e: cambiar_seccion("sesiones"),
    )

    tile_historico = ft.ListTile(
        leading=ft.Icon(ft.Icons.PICTURE_AS_PDF),
        title=ft.Text("Generar histórico"),
        selected=False,
        on_click=lambda e: cambiar_seccion("historico"),
    )

    def cambiar_seccion(nombre: str):
        if nombre == "historia":
            contenido_derecha.content = seccion_historia
        elif nombre == "sesiones":
            contenido_derecha.content = seccion_sesiones
        else:
            contenido_derecha.content = seccion_historico

        tile_historia.selected = nombre == "historia"
        tile_sesiones.selected = nombre == "sesiones"
        tile_historico.selected = nombre == "historico"

        if contenido_derecha.page is not None:
            contenido_derecha.update()
        if tile_historia.page is not None:
            tile_historia.update()
            tile_sesiones.update()
            tile_historico.update()

    menu_izq = ft.Container(
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
                ft.Text("Historia clínica", size=16, weight="bold"),
                ft.Divider(),
                tile_historia,
                tile_sesiones,
                tile_historico,
                ft.Divider(),
                ft.Text("Paciente", size=14, weight="bold"),
                txt_buscar_paciente,
                resultados_pacientes,
            ],
            spacing=8,
        ),
    )

    # Sección por defecto
    cambiar_seccion("historia")

    # Prefill si venimos desde Pacientes
    pre_doc = None
    try:
        pre_doc = page.session.get("historia_paciente_documento")
    except Exception:
        pre_doc = getattr(page, "historia_paciente_documento", None)

    if pre_doc:
        fila = obtener_paciente(pre_doc)
        if fila:
            _seleccionar_paciente(dict(fila))
        try:
            page.session.remove("historia_paciente_documento")
        except Exception:
            try:
                delattr(page, "historia_paciente_documento")
            except Exception:
                pass

    raiz = ft.Row(
        [
            menu_izq,
            ft.Container(width=16),
            contenido_derecha,
        ],
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )

    return raiz
