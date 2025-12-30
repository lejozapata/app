from datetime import date, datetime
from typing import Dict, Any, List

import flet as ft

import asyncio
import time
import re
import sqlite3

from .historia_pdf import generar_pdf_historia
from .markdown_editor import MarkdownEditor
from .cie11_api import CIE11Client

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
    listar_citas_por_paciente,
    # Diagnósticos
    listar_diagnosticos_historia,
    agregar_diagnostico_historia,
    eliminar_diagnostico_historia,
    get_connection,
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
    
    
    # helper para verificar si ya existe sesión vinculada a una cita
    def existe_sesion_para_cita(cita_id: int, excluir_sesion_id: int | None = None) -> bool:
        """
        True si ya existe una sesión clínica vinculada a esa cita_id.
        excluir_sesion_id sirve para permitir editar la misma sesión sin bloquear.
        """
        try:
            conn = get_connection()
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            if excluir_sesion_id:
                cur.execute(
                    "SELECT 1 FROM sesiones_clinicas WHERE cita_id = ? AND id <> ? LIMIT 1;",
                    (cita_id, excluir_sesion_id),
                )
            else:
                cur.execute(
                    "SELECT 1 FROM sesiones_clinicas WHERE cita_id = ? LIMIT 1;",
                    (cita_id,),
                )

            row = cur.fetchone()
            conn.close()
            return row is not None
        except Exception:
            return False
    

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

    # -------------------- Diagnósticos CIE (CIE-11 por API) --------------------

    cie11_client = None

    def _get_cie11():
        nonlocal cie11_client
        if cie11_client is None:
            cie11_client = CIE11Client(language="es")
        return cie11_client

    def strip_html(s: str) -> str:
        return re.sub(r"<[^>]+>", "", s or "")

    # debounce state (DEBE ir antes de los handlers)
    _last_search = {"q": "", "ts": 0.0}
    _pending_task = {"task": None}

    dx_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Sistema")),
            ft.DataColumn(ft.Text("Código")),
            ft.DataColumn(ft.Text("Título")),
            ft.DataColumn(ft.Text("Acciones")),
        ],
        rows=[],
        column_spacing=14,
    )

    def cargar_diagnosticos():
        dx_table.rows.clear()
        if not historia_actual["id"]:
            if dx_table.page is not None:
                dx_table.update()
            return

        dxs = [dict(r) for r in listar_diagnosticos_historia(historia_actual["id"])]
        for d in dxs:
            dx_id = d["id"]
            sistema = d["sistema"]
            codigo = d["codigo"]
            titulo = d.get("titulo") or ""

            btn_quitar = ft.TextButton(
                "Quitar",
                on_click=lambda e, _id=dx_id: (
                    eliminar_diagnostico_historia(_id),
                    cargar_diagnosticos(),
                ),
            )

            dx_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(sistema)),
                        ft.DataCell(ft.Text(codigo)),
                        ft.DataCell(ft.Text(titulo)),
                        ft.DataCell(btn_quitar),
                    ]
                )
            )

        if dx_table.page is not None:
            dx_table.update()

    txt_buscar_dx = ft.TextField(
        label="Buscar diagnóstico (código o texto)",
        expand=True,
    )

    chk_codigo = ft.Checkbox(label="Código", value=True)
    chk_titulo = ft.Checkbox(label="Título", value=True)
    chk_desc = ft.Checkbox(label="Descripción", value=True)

    resultados_list = ft.ListView(expand=True, spacing=6, padding=10)

    lbl_hint_busqueda = ft.Text(
        "Escribe un término (p. ej. 'ansiedad', 'depresivo', 'insomnio') y presiona Buscar.",
        size=12,
        color=ft.Colors.GREY_600,
    )

    def ejecutar_busqueda_dx(e=None):
        q_raw = (txt_buscar_dx.value or "").strip()
        q = q_raw.strip()
        q_upper = q.upper()

        def parece_codigo_cie11(s: str) -> bool:
            # Ejemplos: MB29, MB28.A, 6A70.3, HA60
            return bool(re.match(r"^[A-Z0-9]{2,5}(\.[A-Z0-9]{1,4})?$", (s or "").strip().upper()))

        def render_sin_resultados(mensaje: str, sugerencias: list[str] | None = None):
            resultados_list.controls.clear()
            msg = mensaje
            if sugerencias:
                msg += f" Sugerencias: {', '.join(sugerencias)}."
            resultados_list.controls.append(ft.Text(msg, color=ft.Colors.GREY_600))
            resultados_list.update()

        def _add_factory(code: str, title: str, _uri: str):
            def _add(_e):
                pac = paciente_actual["value"]
                if not pac:
                    page.snack_bar = ft.SnackBar(content=ft.Text("Selecciona un paciente primero."))
                    page.snack_bar.open = True
                    page.update()
                    return

                # Si no hay historia creada aún, crearla automáticamente
                if not historia_actual["id"]:
                    datos_hist = {
                        "id": None,
                        "documento_paciente": pac["documento"],
                        "fecha_apertura": txt_fecha_apertura.value or date.today().isoformat(),
                        "motivo_consulta_inicial": (txt_motivo.value or "").strip() or None,
                        "informacion_adicional": (txt_info_adicional.value or "").strip() or None,
                    }
                    historia_id = guardar_historia_clinica(datos_hist)
                    historia_actual["id"] = historia_id

                if not code:
                    page.snack_bar = ft.SnackBar(content=ft.Text("Este ítem no tiene código codificable."))
                    page.snack_bar.open = True
                    page.update()
                    return

                try:
                    agregar_diagnostico_historia(historia_actual["id"], "CIE-11", code, title, _uri)
                except Exception as ex:
                    page.snack_bar = ft.SnackBar(content=ft.Text(f"No se pudo agregar: {ex}"))
                    page.snack_bar.open = True
                    page.update()
                    return

                cargar_diagnosticos()
                dlg_dx.open = False
                page.snack_bar = ft.SnackBar(content=ft.Text("Diagnóstico agregado."))
                page.snack_bar.open = True
                page.update()

            return _add  # <-- CRÍTICO

        # ---- Reset UI ----
        resultados_list.controls.clear()
        resultados_list.controls.append(lbl_hint_busqueda)

        if not q:
            resultados_list.update()
            return

        # ---- Caso 1: parece código ----
        if parece_codigo_cie11(q_upper):
            try:
                ent = _get_cie11().lookup_code(q_upper)  # <-- AQUÍ el cambio clave
            except Exception as ex:
                render_sin_resultados(f"Error en búsqueda CIE-11: {ex}")
                return

            if not ent:
                render_sin_resultados("Código no encontrado. Verifica el código o prueba buscar por texto.")
                return

            codigo = (ent.code or q_upper).upper()
            titulo = strip_html(ent.title or "")
            uri = ent.uri

            resultados_list.controls.clear()
            fila = ft.Container(
                padding=10,
                border=ft.border.all(1, ft.Colors.GREY_300),
                border_radius=8,
                content=ft.Row(
                    [
                        ft.Container(width=90, content=ft.Text(codigo, weight="bold")),
                        ft.Container(expand=True, content=ft.Text(titulo)),
                        ft.ElevatedButton("Agregar", on_click=_add_factory(codigo, titulo, uri)),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
            resultados_list.controls.append(fila)
            resultados_list.update()
            return

        # ---- Caso 2: texto normal ----
        # Evita búsquedas demasiado cortas
        q_norm = (q or "").strip()
        q_is_acronym = q_norm.isalpha() and q_norm.isupper() and 2 <= len(q_norm) <= 6

        # Permitir acrónimos cortos (VIH, TB, TOC), o texto normal >= 3
        min_len = 2 if q_is_acronym else 3
        if len(q_norm) < min_len:
            resultados_list.controls.clear()
            resultados_list.controls.append(
                ft.Text(
                    f"Escribe al menos {min_len} caracteres para buscar.",
                    color=ft.Colors.GREY_600,
                )
            )
            resultados_list.update()
            return

        try:
            res = _get_cie11().search(q)
            res = res[:50]
        except Exception as ex:
            resultados_list.controls.clear()
            resultados_list.controls.append(
                ft.Text(f"Error en búsqueda CIE-11: {ex}", color=ft.Colors.RED_700)
            )
            resultados_list.update()
            return

        if not res:
            sugerencias = []
            if q.lower().startswith("depre"):
                sugerencias = ["depresion", "depresivo", "depresivos", "distimia"]
            render_sin_resultados("Sin resultados. Prueba otro término.", sugerencias)
            return

        resultados_list.controls.clear()

        for ent in res:
            codigo = ent.code or ""
            titulo = strip_html(ent.title or "")
            uri = ent.uri

            fila = ft.Container(
                padding=10,
                border=ft.border.all(1, ft.Colors.GREY_300),
                border_radius=8,
                content=ft.Row(
                    [
                        ft.Container(width=90, content=ft.Text(codigo, weight="bold")),
                        ft.Container(expand=True, content=ft.Text(titulo)),
                        ft.ElevatedButton("Agregar", on_click=_add_factory(codigo, titulo, uri)),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
            resultados_list.controls.append(fila)

        resultados_list.update()

    # --- búsqueda en vivo con debounce ---
    _last_search = {"q": "", "ts": 0.0}
    _pending_task = {"task": None}

    async def _debounced_search():
        await asyncio.sleep(0.35)
        ejecutar_busqueda_dx()

    def _on_change_buscar_dx(e):
        q = (txt_buscar_dx.value or "").strip()

        q_norm = (q or "").strip()
        q_is_acronym = q_norm.isalpha() and q_norm.isupper() and 2 <= len(q_norm) <= 6
        min_len = 2 if q_is_acronym else 3

        if len(q_norm) < min_len:
            resultados_list.controls.clear()
            resultados_list.controls.append(lbl_hint_busqueda)
            resultados_list.update()
            return

        now = time.time()
        if q == _last_search["q"] and (now - _last_search["ts"]) < 0.4:
            return

        _last_search["q"] = q
        _last_search["ts"] = now

        # Cancelar tarea anterior
        t = _pending_task.get("task")
        if t:
            try:
                t.cancel()
            except Exception:
                pass

        # ✅ NOTA: se pasa la función async, NO se llama
        _pending_task["task"] = page.run_task(_debounced_search)

    # IMPORTANTE: asignar el handler después de definirlo
    txt_buscar_dx.on_change = _on_change_buscar_dx
    txt_buscar_dx.on_submit = ejecutar_busqueda_dx
    
    # Dialogo de búsqueda de diagnósticos

    dlg_dx = ft.AlertDialog(
        modal=True,
        title=ft.Text("Agregar diagnóstico (CIE-11)"),
        content=ft.Column(
            [
                ft.Row([txt_buscar_dx], alignment=ft.MainAxisAlignment.START),
                ft.Row([chk_codigo, chk_titulo, chk_desc], spacing=10),
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Buscar",
                            icon=ft.Icons.SEARCH,
                            on_click=ejecutar_busqueda_dx,
                        )
                    ],
                    alignment=ft.MainAxisAlignment.END,
                ),
                ft.Container(
                    height=380,
                    width=920,
                    padding=10,
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    border_radius=8,
                    content=resultados_list,
                ),
            ],
            tight=True,
        ),
        actions=[
            ft.TextButton(
                "Cerrar",
                on_click=lambda e: (
                    setattr(dlg_dx, "open", False),
                    page.update(),
                ),
            )
        ],
    )

    def abrir_dialogo_dx(e):
        if dlg_dx not in page.overlay:
            page.overlay.append(dlg_dx)

        # Reset UI del diálogo cada vez
        txt_buscar_dx.value = ""
        resultados_list.controls.clear()
        resultados_list.controls.append(lbl_hint_busqueda)

        dlg_dx.open = True
        page.update()

    def abrir_catalogo_cie11(e):
        try:
            # si tu CIE11Client ya está instanciado, esto te da el release real
            release = _get_cie11().release_id
        except Exception:
            release = "2025-01"

        url = f"https://icd.who.int/browse/{release}/mms/es"
        page.launch_url(url)

    btn_agregar_dx = ft.ElevatedButton(
        "Agregar diagnóstico CIE",
        icon=ft.Icons.ADD,
        on_click=abrir_dialogo_dx,
    )

    btn_info_cie11 = ft.IconButton(
        icon=ft.Icons.HELP_OUTLINE, # TAMBIEN SIRVE Icons.INFO/INFO_OUTLINE
        icon_color=ft.Colors.BLUE_600,
        icon_size=18,
        tooltip="Abrir catálogo CIE-11 (OMS)",
        on_click=abrir_catalogo_cie11,
    )

    # Row de acciones
    acciones_dx = ft.Row(
        [
            btn_agregar_dx,
            ft.Container(width=2),
            btn_info_cie11,
        ],
        alignment=ft.MainAxisAlignment.START,
        spacing=0,
    )

    # -------------------- Cargar historia --------------------

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

        cargar_diagnosticos()
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
        page.snack_bar = ft.SnackBar(content=ft.Text("Historia clínica guardada."))
        page.snack_bar.open = True
        if mensaje_historia.page is not None:
            mensaje_historia.update()
        page.update()

        cargar_diagnosticos()
        cargar_sesiones()

    def generar_pdf_historia_click(e):
        pac = paciente_actual["value"]
        if not pac:
            page.snack_bar = ft.SnackBar(content=ft.Text("Debes seleccionar un paciente primero."))
            page.snack_bar.open = True
            page.update()
            return

        try:
            generar_pdf_historia(pac["documento"], abrir=True)
            page.snack_bar = ft.SnackBar(content=ft.Text("PDF de historia clínica generado."))
        except Exception as ex:
            page.snack_bar = ft.SnackBar(content=ft.Text(f"Error al generar el PDF de historia clínica: {ex}"))

        page.snack_bar.open = True
        page.update()

    btn_guardar_historia = ft.ElevatedButton(
        "Guardar historia clínica",
        icon=ft.Icons.SAVE,
        on_click=guardar_historia,
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

            # ===================== DIAGNÓSTICOS =====================
            ft.Text("Diagnósticos (CIE)", weight="bold"),
            ft.Text(
                "Registra uno o varios diagnósticos en la historia clínica general.",
                size=11,
                color=ft.Colors.GREY_700,
            ),
            ft.Row(
                [acciones_dx],
                alignment=ft.MainAxisAlignment.START,
                spacing=10,
            ),
            ft.Container(
                padding=10,
                border=ft.border.all(1, ft.Colors.GREY_300),
                border_radius=8,
                content=ft.Column([dx_table], scroll=ft.ScrollMode.AUTO),
            ),
            # =========================================================

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
                        wrap=True,
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
                        wrap=True,
                    ),
                ],
                spacing=20,
            ),
            mensaje_historia,

            ft.Container(
                padding=ft.padding.only(bottom=6),
                content=ft.Row(
                    [btn_guardar_historia, btn_pdf_historia],
                    alignment=ft.MainAxisAlignment.START,
                    spacing=10,
                    wrap=True,   # si no cabe, baja a la siguiente línea
                ),
            ),

            # colchón para que el scroll nunca “se coma” el footer
            ft.Container(height=24),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            )
    

    # -------------------- Controles de sesiones --------------------

    txt_fecha_sesion = ft.TextField(
        label="Fecha sesión",
        width=150,
        read_only=True,
    )
    
    # ---- Vincular con cita ----
    switch_vincular_cita = ft.Switch(
        label="Vincular con cita agendada",
        value=False,
    )

    dd_citas = ft.Dropdown(
        label="Seleccionar cita",
        width=500,
        visible=False,
    )

    dp_sesion = ft.DatePicker(
        first_date=date(2000, 1, 1),
        last_date=date(2100, 12, 31),
    )
    
    def _on_toggle_vincular(e):
        dd_citas.visible = switch_vincular_cita.value
        if switch_vincular_cita.value:
            cargar_citas_paciente()
        if dd_citas.page:
            dd_citas.update()

    switch_vincular_cita.on_change = _on_toggle_vincular

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
        
        switch_vincular_cita.value = False
        dd_citas.visible = False
        dd_citas.value = None

        for c in [
            txt_fecha_sesion,
            txt_titulo_sesion,
            switch_markdown,
            txt_contenido_sesion,
            md_editor,
            txt_obs_sesion,
            switch_vincular_cita,
            dd_citas,
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

        for idx, s in enumerate(sesiones or [], start=1):
            s_dict = dict(s)  # sqlite3.Row -> dict

            sesion_id = s_dict["id"]

            btn_editar = ft.TextButton(
                "Editar",
                on_click=lambda e, ses=s: cargar_sesion_en_form(ses),
            )
            btn_eliminar = ft.TextButton(
                "Eliminar",
                on_click=lambda e, sid=sesion_id: eliminar_sesion_click(sid),
            )

            # ---------------------------------------------
            # Fecha a mostrar:
            # - Si hay cita_id => usar citas.fecha_hora (con hora real)
            # - Si NO hay cita_id => usar sesiones_clinicas.fecha (solo fecha)
            # ---------------------------------------------
            fecha_txt = s_dict.get("fecha") or ""
            cita_id = s_dict.get("cita_id")

            if cita_id:
                try:
                    conn = get_connection()
                    conn.row_factory = sqlite3.Row
                    cur = conn.cursor()
                    cur.execute("SELECT fecha_hora FROM citas WHERE id = ? LIMIT 1;", (cita_id,))
                    row_cita = cur.fetchone()
                    conn.close()

                    if row_cita and row_cita["fecha_hora"]:
                        try:
                            fecha_txt = datetime.fromisoformat(str(row_cita["fecha_hora"])).strftime("%Y-%m-%d %H:%M")
                        except Exception:
                            fecha_txt = str(row_cita["fecha_hora"])
                    else:
                        # Si no encontramos la cita, al menos mostramos la fecha de la sesión
                        fecha_txt = s_dict.get("fecha") or ""
                except Exception:
                    # fallback silencioso
                    fecha_txt = s_dict.get("fecha") or ""
            else:
                # Sesión manual: NO inventar 00:00
                fecha_txt = s_dict.get("fecha") or ""

            tabla_sesiones.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(f"Cita {idx} - Fecha: {fecha_txt}")),
                        ft.DataCell(ft.Text(s_dict.get("titulo") or "")),
                        ft.DataCell(ft.Row([btn_editar, btn_eliminar], spacing=5)),
                    ]
                )
            )

        if tabla_sesiones.page is not None:
            tabla_sesiones.update()

        cargar_citas_paciente()
            
    def _row_to_dict(r):
        try:
            return dict(r)
        except Exception:
            return r  # ya es dict

    def cargar_citas_paciente():
        dd_citas.options.clear()
        dd_citas.value = None

        pac = paciente_actual["value"]
        if not pac:
            if dd_citas.page:
                dd_citas.update()
            return

        citas = listar_citas_por_paciente(pac["documento"])

        # ✅ set de citas que ya tienen sesión
        citas_con_sesion = set()
        try:
            conn = get_connection()
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                """
                SELECT cita_id
                FROM sesiones_clinicas
                WHERE cita_id IS NOT NULL;
                """
            )
            for r in cur.fetchall():
                try:
                    citas_con_sesion.add(int(r["cita_id"]))
                except Exception:
                    pass
            conn.close()
        except Exception:
            pass

        for r in citas or []:
            c = dict(r)
            cita_id = c.get("id")
            if not cita_id:
                continue

            fecha = c.get("fecha_hora") or c.get("inicio") or c.get("fecha") or ""
            canal = (c.get("canal") or "").strip()

            # si tu campo "servicio" trae "Servicio: X - Valor: Y", aquí NO lo uses para HC
            # mejor canal + fecha
            label_base = " · ".join(x for x in [str(fecha), canal] if str(x).strip())

            ya_tiene = int(cita_id) in citas_con_sesion

            # ✅ Marca visual
            label = f"✅ {label_base}" if ya_tiene else label_base

            opt = ft.dropdown.Option(key=str(cita_id), text=label)

            # (Opcional) bloquear selección si ya tiene sesión
            # OJO: depende de tu versión de flet si Option soporta `disabled`
            try:
                opt.disabled = ya_tiene and (str(cita_id) != str(dd_citas.value or ""))
            except Exception:
                pass

            dd_citas.options.append(opt)

        if dd_citas.page:
            dd_citas.update()

    def cargar_sesion_en_form(s):
        # ✅ s puede ser sqlite3.Row o dict
        s = dict(s) if not isinstance(s, dict) else s

        sesion_editando["id"] = s.get("id")

        # --- datos básicos ---
        txt_fecha_sesion.value = s.get("fecha") or date.today().isoformat()
        txt_titulo_sesion.value = s.get("titulo") or ""

        contenido = s.get("contenido") or ""
        txt_contenido_sesion.value = contenido
        md_editor.set_value(contenido)

        txt_obs_sesion.value = s.get("observaciones") or ""

        # --- reset estado vinculación ---
        switch_vincular_cita.value = False
        dd_citas.visible = False
        dd_citas.value = None

        # --- cargar citas del paciente antes de setear dd ---
        cargar_citas_paciente()

        # --- vinculación si aplica ---
        cita_id = s.get("cita_id")
        if cita_id:
            switch_vincular_cita.value = True
            dd_citas.visible = True

            # asignar solo si existe en options
            cid = str(cita_id)
            if any(opt.key == cid for opt in dd_citas.options):
                dd_citas.value = cid
            else:
                # si no está en el dropdown (por ejemplo filtro de citas), lo dejamos visible pero sin value
                dd_citas.value = None

        # --- refrescar UI ---
        for c in [
            txt_fecha_sesion,
            txt_titulo_sesion,
            switch_markdown,
            txt_contenido_sesion,
            md_editor,
            txt_obs_sesion,
            switch_vincular_cita,
            dd_citas,
        ]:
            if c.page:
                c.update()


    def eliminar_sesion_click(sesion_id: int):
        eliminar_sesion_clinica(sesion_id)
        page.snack_bar = ft.SnackBar(content=ft.Text("Sesión eliminada correctamente."))
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
                "fecha_apertura": txt_fecha_apertura.value or date.today().isoformat(),
                "motivo_consulta_inicial": (txt_motivo.value or "").strip() or None,
                "informacion_adicional": (txt_info_adicional.value or "").strip() or None,
            }
            historia_id = guardar_historia_clinica(datos_hist)
            historia_actual["id"] = historia_id

        fecha_sesion = txt_fecha_sesion.value or date.today().isoformat()

        contenido_texto = (
            md_editor.get_value() if switch_markdown.value else (txt_contenido_sesion.value or "")
        ).strip()

        if not contenido_texto:
            mensaje_sesion.value = "El contenido de la sesión es obligatorio."
            if mensaje_sesion.page is not None:
                mensaje_sesion.update()
            return

        cita_id = None
        if switch_vincular_cita.value:
            if not dd_citas.value:
                mensaje_sesion.value = "Debes seleccionar una cita."
                mensaje_sesion.update()
                return
            cita_id = int(dd_citas.value)
            
        # ✅ Evitar duplicar: una cita solo puede tener 1 sesión clínica
        if cita_id is not None:
            if existe_sesion_para_cita(cita_id, excluir_sesion_id=sesion_editando["id"]):
                mensaje_sesion.value = "Esta cita ya tiene una sesión clínica creada. Edita la sesión existente."
                if mensaje_sesion.page:
                    mensaje_sesion.update()
                return

        datos_sesion = {
            "id": sesion_editando["id"],
            "historia_id": historia_actual["id"],
            "fecha": fecha_sesion,
            "titulo": (txt_titulo_sesion.value or "").strip(),
            "contenido": contenido_texto,
            "observaciones": (txt_obs_sesion.value or "").strip(),
            "cita_id": cita_id,
        }

        guardar_sesion_clinica(datos_sesion)

        page.snack_bar = ft.SnackBar(content=ft.Text("Sesión clínica guardada correctamente."))
        page.snack_bar.open = True
        page.update()

        limpiar_form_sesion()
        cargar_sesiones()

    btn_guardar_sesion = ft.ElevatedButton(
        "Guardar sesión",
        icon=ft.Icons.SAVE,
        on_click=guardar_sesion,
    )
    
    def _on_cita_selected(e):
        if not dd_citas.value:
            return

        pac = paciente_actual["value"]
        if not pac:
            return

        # Buscar la cita seleccionada
        citas = listar_citas_por_paciente(pac["documento"])
        sel = None

        for r in citas or []:
            c = dict(r)  # sqlite3.Row -> dict
            if str(c.get("id")) == str(dd_citas.value):
                sel = c
                break

        if not sel:
            return

        # --- Fecha de la sesión ---
        fecha = sel.get("fecha_hora") or sel.get("fecha") or ""
        if fecha:
            txt_fecha_sesion.value = str(fecha)[:10]

        # --- Construcción segura del título ---
        def clean(val):
            if not val:
                return ""
            val = str(val)
            # eliminar precios, monedas y números sueltos
            val = re.sub(r"\$?\s*\d+(\.\d+)?", "", val)
            val = val.replace("COP", "").replace("USD", "")
            return val.strip()

        servicio = clean(
            sel.get("servicio_nombre")
            or sel.get("servicio")
            or sel.get("tipo_servicio")
            or ""
        )

        canal = clean(
            sel.get("canal")
            or sel.get("modalidad")
            or ""
        )

        partes = [p for p in [servicio, canal] if p]

        titulo_sugerido = "Sesión"
        if partes:
            titulo_sugerido = "Sesión · " + " · ".join(partes)

        # Solo autocompletar si el usuario no ha escrito nada
        if not (txt_titulo_sesion.value or "").strip():
            txt_titulo_sesion.value = titulo_sugerido

        # refrescar UI
        if txt_fecha_sesion.page:
            txt_fecha_sesion.update()
        if txt_titulo_sesion.page:
            txt_titulo_sesion.update()
            
    dd_citas.on_change = _on_cita_selected

    dd_citas.on_change = _on_cita_selected

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

            # Fecha
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

            # ✅ NUEVO: Switch + selector de citas (el DD se oculta solo si switch OFF)
            switch_vincular_cita,
            dd_citas,

            # Resto del formulario
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
                alignment=ft.MainAxisAlignment.START,
            ),
            ft.Divider(),
            ft.Text("Sesiones registradas", weight="bold"),
            ft.Container(
                height=260,
                content=ft.Column([tabla_sesiones], scroll=ft.ScrollMode.AUTO),
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
            page.snack_bar = ft.SnackBar(content=ft.Text("Debes seleccionar un paciente primero."))
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
                fecha_desde = datetime.strptime(txt_fecha_desde_hist.value, "%Y-%m-%d").date()
                fecha_hasta = datetime.strptime(txt_fecha_hasta_hist.value, "%Y-%m-%d").date()
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

            page.snack_bar = ft.SnackBar(content=ft.Text("Histórico generado correctamente."))
        except Exception as ex:
            page.snack_bar = ft.SnackBar(content=ft.Text(f"Error al generar el histórico: {ex}"))

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
                alignment=ft.MainAxisAlignment.START,
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

    contenido_derecha_scroll_x = ft.Row(
        [contenido_derecha],
        scroll=ft.ScrollMode.AUTO,   # <-- scroll horizontal
        expand=True,
    )

    raiz = ft.Row(
        [
            menu_izq,
            ft.Container(width=16),
            contenido_derecha_scroll_x,
        ],
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )

    return raiz
