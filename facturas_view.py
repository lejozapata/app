import os
from datetime import date
from typing import Dict, Any, Optional

import flet as ft

from .facturas_pdf import generar_pdf_factura
from .db import (
    listar_empresas_convenio,
    listar_pacientes,
    crear_factura_convenio,
    listar_facturas_convenio,
    obtener_factura_convenio,
    actualizar_factura_convenio,
    eliminar_factura_convenio,
    guardar_empresa_convenio,
    actualizar_estado_factura_convenio,
    obtener_configuracion_facturacion,
    eliminar_empresa_convenio,  # <- debe retornar (bool, msg)
)


def build_facturas_view(page: ft.Page) -> ft.Control:
    page.padding = 10

    # ---------------------------------------------------------------------
    # Estado global de navegación en esta vista
    # ---------------------------------------------------------------------
    seccion_activa = {"value": "creacion"}

    # ---------------------------------------------------------------------
    # Datos base desde BD
    # ---------------------------------------------------------------------
    empresas_cache = listar_empresas_convenio()
    pacientes_cache = listar_pacientes()

    # ---------------------------------------------------------------------
    # =============== 1. SECCIÓN: CREACIÓN DE FACTURAS ====================
    # ---------------------------------------------------------------------

    # --- Empresa del convenio ---
    dd_empresas = ft.Dropdown(
        label="Empresa del convenio",
        width=350,
        options=[ft.dropdown.Option(str(e["id"]), e["nombre"]) for e in empresas_cache],
    )

    # --- Fecha factura ---
    txt_fecha = ft.TextField(
        label="Fecha factura",
        value=date.today().isoformat(),
        width=160,
        read_only=True,
    )

    dp_fecha = ft.DatePicker(
        first_date=date(2020, 1, 1),
        last_date=date(2100, 12, 31),
    )

    def _on_change_fecha(e):
        if dp_fecha.value:
            txt_fecha.value = dp_fecha.value.strftime("%Y-%m-%d")
            if txt_fecha.page is not None:
                txt_fecha.update()

    dp_fecha.on_change = _on_change_fecha

    # Registrar el datepicker en el overlay de la página
    try:
        if dp_fecha not in page.overlay:
            page.overlay.append(dp_fecha)
    except Exception:
        page.overlay.append(dp_fecha)

    def _abrir_datepicker(e):
        dp_fecha.open = True
        if page is not None:
            page.update()

    # --- Paciente: búsqueda simple en memoria ---
    txt_buscar_paciente = ft.TextField(
        label="Buscar paciente (nombre o documento)",
        width=350,
    )

    resultados_pacientes = ft.Column(spacing=0, tight=True)

    txt_paciente_documento = ft.TextField(
        label="Documento del paciente",
        width=200,
        read_only=True,
    )
    txt_paciente_nombre = ft.TextField(
        label="Nombre del paciente",
        width=350,
        read_only=True,
    )

    def _seleccionar_paciente(pac_row):
        txt_paciente_nombre.value = pac_row["nombre_completo"]
        txt_paciente_documento.value = pac_row["documento"]
        txt_buscar_paciente.value = ""
        resultados_pacientes.controls.clear()
        page.update()

    def _filtrar_pacientes(e=None):
        query = (txt_buscar_paciente.value or "").strip().lower()
        resultados_pacientes.controls.clear()

        if not query or len(query) < 2:
            page.update()
            return

        for p in pacientes_cache:
            nombre = p["nombre_completo"]
            doc = p["documento"]
            texto_busqueda = f"{nombre} {doc}".lower()
            if query in texto_busqueda:
                btn = ft.TextButton(
                    f"{nombre} ({doc})",
                    on_click=lambda ev, pac=p: _seleccionar_paciente(pac),
                )
                resultados_pacientes.controls.append(btn)

        page.update()

    txt_buscar_paciente.on_change = _filtrar_pacientes

    # --- Detalle factura (MÚLTIPLES ÍTEMS) ---
    items_controls = []  # [{"desc": TextField, "cant": TextField, "vu": TextField}]
    items_column = ft.Column(spacing=8)

    dd_iva_porcentaje = ft.Dropdown(
        label="IVA %",
        width=120,
        options=[
            ft.dropdown.Option("0", "0%"),
            ft.dropdown.Option("5", "5%"),
            ft.dropdown.Option("19", "19%"),
        ],
        value="0",
    )

    txt_subtotal = ft.TextField(label="Subtotal", read_only=True, width=150)
    txt_iva = ft.TextField(label="IVA", read_only=True, width=150)
    txt_total = ft.TextField(label="Total", read_only=True, width=150)

    txt_forma_pago = ft.TextField(
        label="Forma de pago",
        value="Transferencia bancaria",
        width=250,
    )

    # --- Forma de pago por defecto desde Admin (configuración_facturación) ---
    try:
        cfg_fact = obtener_configuracion_facturacion()
        forma_cfg = (cfg_fact.get("forma_pago") or "").strip()
        if forma_cfg:
            txt_forma_pago.value = forma_cfg
    except Exception:
        pass

    lbl_mensaje = ft.Text("", color=ft.Colors.RED_400)

    # ================== HELPERS NUMÉRICOS ==================
    def _parse_float(s: str) -> float:
        # acepta "1.234" o "1234" o "1,5"
        return float((s or "0").replace(".", "").replace(",", "."))

    def _fmt_money(v: float) -> str:
        try:
            return f"{v:,.0f}".replace(",", ".")
        except Exception:
            return str(v)

    # ================== RECÁLCULO TOTALES ==================
    def _recalcular_totales(e=None):
        try:
            porc = float(dd_iva_porcentaje.value or "0")
            subtotal_val = 0.0

            for it in items_controls:
                cant = _parse_float(it["cant"].value)
                vu = _parse_float(it["vu"].value)
                if cant < 0 or vu < 0:
                    raise ValueError("negativos")
                subtotal_val += cant * vu

        except Exception:
            lbl_mensaje.value = "Error en formato numérico de ítems / IVA."
            page.update()
            return

        iva_val = subtotal_val * porc / 100.0
        total_val = subtotal_val + iva_val

        txt_subtotal.value = _fmt_money(subtotal_val)
        txt_iva.value = _fmt_money(iva_val)
        txt_total.value = _fmt_money(total_val)
        lbl_mensaje.value = ""
        page.update()

    dd_iva_porcentaje.on_change = _recalcular_totales

    # ================== AGREGAR ÍTEM ==================
    def _add_item(desc="Consulta Psicológica", cant="1", vu=""):
        desc_tf = ft.TextField(label="Descripción", value=desc, width=420)
        cant_tf = ft.TextField(label="Cant.", value=cant, width=80)
        vu_tf = ft.TextField(label="V. Unit", value=vu, width=140)

        def _remove(_e):
            items_controls[:] = [x for x in items_controls if x["desc"] != desc_tf]
            items_column.controls[:] = [r for r in items_column.controls if r.data != desc_tf]
            _recalcular_totales()
            page.update()

        del_btn = ft.IconButton(icon=ft.Icons.DELETE, tooltip="Quitar ítem", on_click=_remove)

        row = ft.Row([desc_tf, cant_tf, vu_tf, del_btn], spacing=10, wrap=True)
        row.data = desc_tf

        cant_tf.on_change = _recalcular_totales
        vu_tf.on_change = _recalcular_totales

        items_controls.append({"desc": desc_tf, "cant": cant_tf, "vu": vu_tf})
        items_column.controls.append(row)

    # --- Prefill cuando venimos desde la agenda (facturar convenio) ---
    prefill = None
    try:
        prefill = page.session.get("facturar_desde_agenda")
    except Exception:
        prefill = getattr(page, "facturar_desde_agenda", None)

    # Estado para edición
    factura_editando_id: Optional[int] = None

    # --- Tabla de facturas existentes ---
    facturas_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Número")),
            ft.DataColumn(ft.Text("Fecha")),
            ft.DataColumn(ft.Text("Empresa")),
            # ft.DataColumn(ft.Text("Paciente")),
            ft.DataColumn(ft.Text("Total")),
            ft.DataColumn(ft.Text("Estado")),
            ft.DataColumn(ft.Text("Acciones")),
        ],
        rows=[],
        expand=True,
    )

    def _generar_pdf_desde_ui(factura_id: int):
        try:
            ruta = generar_pdf_factura(factura_id, abrir=True, force=True)
            page.snack_bar = ft.SnackBar(
                content=ft.Text(f"PDF generado: {os.path.basename(ruta)}"),
                bgcolor=ft.Colors.GREEN_300,
            )
            page.snack_bar.open = True
            page.update()
        except Exception as ex:
            page.snack_bar = ft.SnackBar(
                content=ft.Text(f"Error al generar el PDF: {ex}"),
                bgcolor=ft.Colors.RED_300,
            )
            page.snack_bar.open = True
            page.update()

    def _toggle_estado_factura(factura_id: int, estado_actual: str):
        nuevo = "pendiente" if (estado_actual == "pagada") else "pagada"
        try:
            actualizar_estado_factura_convenio(factura_id, nuevo)
        except Exception as ex:
            page.snack_bar = ft.SnackBar(
                content=ft.Text(f"Error al actualizar factura: {ex}"),
                bgcolor=ft.Colors.RED_300,
            )
            page.snack_bar.open = True
            page.update()
            return
        _cargar_facturas()

    def _cargar_facturas():
        facturas = sorted(
            listar_facturas_convenio(),
            key=lambda f: f.get("numero", ""),
            reverse=True,
        )
        facturas_table.rows.clear()

        for f in facturas:
            fid = f["id"]
            numero = f["numero"]
            fecha_f = f["fecha"]
            empresa = f.get("empresa_nombre") or ""
            total = f.get("total", 0)
            estado = f.get("estado") or ""

            try:
                total_txt = f"${total:,.0f}".replace(",", ".")
            except Exception:
                total_txt = str(total)

            btn_pdf = ft.IconButton(
                icon=ft.Icons.PICTURE_AS_PDF,
                tooltip="Generar PDF",
                on_click=lambda e, fid=fid: _generar_pdf_desde_ui(fid),
            )

            if estado == "pagada":
                btn_pagada = ft.IconButton(
                    icon=ft.Icons.UNDO,
                    tooltip="Volver a pendiente",
                    on_click=lambda e, fid=fid, est=estado: _toggle_estado_factura(fid, est),
                )
            else:
                btn_pagada = ft.IconButton(
                    icon=ft.Icons.CHECK_CIRCLE,
                    tooltip="Marcar como pagada",
                    on_click=lambda e, fid=fid, est=estado: _toggle_estado_factura(fid, est),
                )

            btn_edit = ft.IconButton(
                icon=ft.Icons.EDIT,
                tooltip="Editar",
                on_click=lambda e, fid=fid: _editar_factura(fid),
            )

            btn_del = ft.IconButton(
                icon=ft.Icons.DELETE,
                tooltip="Borrar",
                on_click=lambda e, fid=fid, num=numero: _confirmar_borrar(fid, num),
            )

            acciones = ft.Row(controls=[btn_pagada, btn_pdf, btn_edit, btn_del], spacing=4)

            facturas_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(numero))),
                        ft.DataCell(ft.Text(fecha_f)),
                        ft.DataCell(
                            ft.Container(
                                width=240,
                                content=ft.Text(empresa, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),
                            )
                        ),
                        ft.DataCell(ft.Text(total_txt)),
                        ft.DataCell(ft.Text(estado)),
                        ft.DataCell(acciones),
                    ]
                )
            )

        page.update()

    # --- Botón para limpiar paciente ---
    def _limpiar_paciente(e=None):
        txt_paciente_documento.value = ""
        txt_paciente_nombre.value = ""
        txt_buscar_paciente.value = ""
        resultados_pacientes.controls.clear()
        page.update()

    btn_limpiar_paciente = ft.TextButton("Quitar paciente", icon=ft.Icons.CLEAR, on_click=_limpiar_paciente)

    # --- Guardar factura en BD ---
    def _guardar_factura(e):
        nonlocal factura_editando_id
        lbl_mensaje.value = ""

        if not dd_empresas.value:
            lbl_mensaje.value = "Selecciona una empresa de convenio."
            page.update()
            return

        # construir items desde UI
        items = []
        subtotal_items = 0.0

        for it in items_controls:
            desc = (it["desc"].value or "").strip()
            if not desc:
                continue

            try:
                cant = _parse_float(it["cant"].value)
                vu = _parse_float(it["vu"].value)
            except Exception:
                lbl_mensaje.value = "Error en cantidad / valor unitario de los ítems."
                page.update()
                return

            if cant <= 0 or vu < 0:
                lbl_mensaje.value = "Cantidad debe ser > 0 y valor unitario no negativo."
                page.update()
                return

            vt = cant * vu
            items.append(
                {
                    "descripcion": desc,
                    "cantidad": cant,
                    "valor_unitario": vu,
                    "valor_total": vt,
                }
            )
            subtotal_items += vt

        if not items:
            lbl_mensaje.value = "Agrega al menos un ítem con descripción."
            page.update()
            return

        try:
            porc = float(dd_iva_porcentaje.value or "0")
        except Exception:
            lbl_mensaje.value = "IVA inválido."
            page.update()
            return

        iva_val = subtotal_items * (porc / 100.0)
        total_val = subtotal_items + iva_val

        if total_val <= 0:
            lbl_mensaje.value = "El total debe ser mayor que 0."
            page.update()
            return

        cabecera = {
            "fecha": txt_fecha.value or date.today().isoformat(),
            "empresa_id": int(dd_empresas.value),
            "paciente_documento": txt_paciente_documento.value or None,
            "paciente_nombre": txt_paciente_nombre.value or "",
            "subtotal": subtotal_items,
            "iva": iva_val,
            "total": total_val,
            "total_letras": None,
            "forma_pago": txt_forma_pago.value or None,
            "estado": "pendiente",
        }

        try:
            if factura_editando_id is None:
                factura_creada = crear_factura_convenio(cabecera, items)
                msg_ok = f"Factura creada correctamente (No. {factura_creada['numero']})."
            else:
                actualizar_factura_convenio(factura_editando_id, cabecera, items)
                msg_ok = f"Factura actualizada correctamente (ID {factura_editando_id})."
        except Exception as ex:
            lbl_mensaje.value = f"Error al guardar la factura: {ex}"
            page.update()
            return

        # Limpiar formulario
        dd_empresas.value = None
        txt_fecha.value = date.today().isoformat()
        _limpiar_paciente()

        # reset items a 1 fila vacía
        items_controls.clear()
        items_column.controls.clear()
        _add_item()

        dd_iva_porcentaje.value = "0"
        _recalcular_totales()

        factura_editando_id = None
        btn_guardar_factura.text = "Guardar factura de convenio"
        btn_guardar_factura.icon = ft.Icons.SAVE

        for c in [
            dd_empresas,
            txt_fecha,
            txt_buscar_paciente,
            resultados_pacientes,
            txt_paciente_documento,
            txt_paciente_nombre,
            dd_iva_porcentaje,
            txt_subtotal,
            txt_iva,
            txt_total,
            txt_forma_pago,
        ]:
            if c.page is not None:
                c.update()

        page.snack_bar = ft.SnackBar(content=ft.Text(msg_ok))
        page.snack_bar.open = True

        _cargar_facturas()
        page.update()

    btn_guardar_factura = ft.ElevatedButton(
        "Guardar factura de convenio",
        icon=ft.Icons.SAVE,
        on_click=_guardar_factura,
    )

    # --------- PREFILL (DESPUÉS de tener controls listos) ----------
    if isinstance(prefill, dict):
        # 1) Empresa (por nombre exacto)
        nombre_emp = (prefill.get("empresa_nombre") or "").strip()
        if nombre_emp:
            for emp in empresas_cache:
                n = (emp.get("nombre") or "").strip()
                if n == nombre_emp:
                    dd_empresas.value = str(emp["id"])
                    break

        # 2) Paciente (puede venir vacío)
        txt_paciente_nombre.value = prefill.get("paciente_nombre") or ""
        txt_paciente_documento.value = prefill.get("paciente_documento") or ""

        # 3) Primer ítem
        if not items_controls:
            _add_item()
        first = items_controls[0]

        precio = prefill.get("precio")
        if precio is not None:
            try:
                first["vu"].value = str(int(precio))
            except Exception:
                first["vu"].value = str(precio)
        else:
            first["vu"].value = ""

        first["cant"].value = "1"

        if prefill.get("fecha"):
            txt_fecha.value = prefill["fecha"]

        # Descripción por defecto si está vacía
        if not (first["desc"].value or "").strip():
            first["desc"].value = "Consulta Psicológica"

        _recalcular_totales()

        # Limpiar flag
        try:
            page.session.remove("facturar_desde_agenda")
        except Exception:
            try:
                delattr(page, "facturar_desde_agenda")
            except Exception:
                pass

    # ===================== CRUD Para Facturas ======================
    def _editar_factura(fid: int):
        nonlocal factura_editando_id

        data = obtener_factura_convenio(fid)
        if not data:
            page.snack_bar = ft.SnackBar(content=ft.Text("No se encontró la factura."))
            page.snack_bar.open = True
            page.update()
            return

        enc = data["encabezado"]
        dets = data["detalles"]

        dd_empresas.value = str(enc.get("empresa_id") or "")
        txt_fecha.value = enc.get("fecha") or date.today().isoformat()
        txt_paciente_documento.value = enc.get("paciente_documento") or ""
        txt_paciente_nombre.value = enc.get("paciente_nombre") or ""
        txt_forma_pago.value = enc.get("forma_pago") or ""
        dd_iva_porcentaje.value = (
            str(int(enc.get("iva_porcentaje") or 0))
            if enc.get("iva_porcentaje") is not None
            else dd_iva_porcentaje.value
        )

        # cargar ítems
        items_controls.clear()
        items_column.controls.clear()

        for d in dets:
            _add_item(
                desc=d.get("descripcion") or "",
                cant=str(d.get("cantidad") or "1"),
                vu=str(d.get("valor_unitario") or ""),
            )

        if not dets:
            _add_item()

        factura_editando_id = fid
        btn_guardar_factura.text = "Actualizar factura"
        btn_guardar_factura.icon = ft.Icons.EDIT

        _recalcular_totales()
        page.update()

    dlg_confirm_borrar = ft.AlertDialog(modal=True)

    def _confirmar_borrar(fid: int, numero: str):
        def _hacer_borrado(_e):
            try:
                eliminar_factura_convenio(fid, borrar_pdf=True)
            except Exception as ex:
                page.snack_bar = ft.SnackBar(content=ft.Text(f"Error al borrar: {ex}"))
                page.snack_bar.open = True
                page.update()
                return

            dlg_confirm_borrar.open = False
            page.update()
            _cargar_facturas()

        dlg_confirm_borrar.title = ft.Text("Confirmar borrado")
        dlg_confirm_borrar.content = ft.Text(
            f"¿Seguro que deseas borrar la factura {numero}? (también se borrará su PDF si existe)"
        )
        dlg_confirm_borrar.actions = [
            ft.TextButton(
                "Cancelar",
                on_click=lambda e: setattr(dlg_confirm_borrar, "open", False) or page.update(),
            ),
            ft.ElevatedButton("Borrar", icon=ft.Icons.DELETE, on_click=_hacer_borrado),
        ]

        page.dialog = dlg_confirm_borrar
        dlg_confirm_borrar.open = True
        page.open(dlg_confirm_borrar)
        page.update()

    # ===================== UI CARDS ======================
    card_crear_factura = ft.Card(
        content=ft.Container(
            padding=10,
            content=ft.Column(
                [
                    ft.Text("Creación de facturas", size=18, weight="bold"),
                    ft.Row(
                        [
                            dd_empresas,
                            txt_fecha,
                            ft.IconButton(
                                icon=ft.Icons.CALENDAR_MONTH,
                                tooltip="Seleccionar fecha",
                                on_click=_abrir_datepicker,
                            ),
                        ],
                        spacing=10,
                        wrap=True,
                    ),
                    ft.Divider(),
                    ft.Text("Paciente", weight="bold"),
                    ft.Row([txt_buscar_paciente, btn_limpiar_paciente], spacing=10, wrap=True),
                    resultados_pacientes,
                    ft.Row([txt_paciente_documento, txt_paciente_nombre], spacing=10, wrap=True),
                    ft.Divider(),
                    ft.Text("Detalle", weight="bold"),
                    items_column,
                    ft.ElevatedButton(
                        "Agregar ítem",
                        icon=ft.Icons.ADD,
                        on_click=lambda e: (_add_item(), _recalcular_totales(), page.update()),
                    ),
                    ft.Row(
                        [dd_iva_porcentaje, txt_subtotal, txt_iva, txt_total],
                        spacing=10,
                        wrap=True,
                    ),
                    ft.Row([txt_forma_pago], spacing=10),
                    lbl_mensaje,
                    ft.Row([btn_guardar_factura], alignment=ft.MainAxisAlignment.END),
                ],
                spacing=10,
            ),
        ),
    )

    card_listado_facturas = ft.Card(
        content=ft.Container(
            padding=10,
            content=ft.Column(
                [
                    ft.Text("Facturas de convenio", size=18, weight="bold"),
                    ft.Container(
                        height=260,
                        content=ft.Row(
                            [
                                ft.Column(
                                    [facturas_table],
                                    expand=True,
                                    scroll=ft.ScrollMode.AUTO,
                                )
                            ],
                            scroll=ft.ScrollMode.AUTO,
                        ),
                    ),
                ],
                spacing=10,
            ),
        ),
    )

    seccion_creacion = ft.Column(
        [card_crear_factura, card_listado_facturas],
        spacing=15,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )

    # ---------------------------------------------------------------------
    # ========== 2. SECCIÓN: INSCRIPCIÓN EMPRESAS CONVENIO ================
    # ---------------------------------------------------------------------
    empresas_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Nombre")),
            ft.DataColumn(ft.Text("NIT")),
            ft.DataColumn(ft.Text("Ciudad")),
            ft.DataColumn(ft.Text("Teléfono")),
            ft.DataColumn(ft.Text("Activa")),
            ft.DataColumn(ft.Text("Acciones")),
        ],
        rows=[],
        column_spacing=16,
    )

    empresa_id_sel: Dict[str, Optional[int]] = {"value": None}

    txt_emp_nombre = ft.TextField(label="Nombre de la empresa", width=350)
    txt_emp_nit = ft.TextField(label="NIT", width=200)
    txt_emp_direccion = ft.TextField(label="Dirección", width=350)
    txt_emp_ciudad = ft.TextField(label="Ciudad", width=200)
    txt_emp_pais = ft.TextField(label="País", width=200, value="Colombia")
    txt_emp_telefono = ft.TextField(label="Teléfono", width=200)
    txt_emp_email = ft.TextField(label="Email de facturación", width=300)
    txt_emp_contacto = ft.TextField(label="Persona de contacto", width=300)
    chk_emp_activa = ft.Checkbox(label="Empresa activa", value=True)

    def limpiar_form_empresa():
        empresa_id_sel["value"] = None
        txt_emp_nombre.value = ""
        txt_emp_nit.value = ""
        txt_emp_direccion.value = ""
        txt_emp_ciudad.value = ""
        txt_emp_pais.value = "Colombia"
        txt_emp_telefono.value = ""
        txt_emp_email.value = ""
        txt_emp_contacto.value = ""
        chk_emp_activa.value = True
        for c in [
            txt_emp_nombre,
            txt_emp_nit,
            txt_emp_direccion,
            txt_emp_ciudad,
            txt_emp_pais,
            txt_emp_telefono,
            txt_emp_email,
            txt_emp_contacto,
            chk_emp_activa,
        ]:
            if c.page is not None:
                c.update()

    def cargar_empresa_en_form(emp: Dict[str, Any]):
        empresa_id_sel["value"] = emp["id"]
        txt_emp_nombre.value = emp.get("nombre") or ""
        txt_emp_nit.value = emp.get("nit") or ""
        txt_emp_direccion.value = emp.get("direccion") or ""
        txt_emp_ciudad.value = emp.get("ciudad") or ""
        txt_emp_pais.value = emp.get("pais") or "Colombia"
        txt_emp_telefono.value = emp.get("telefono") or ""
        txt_emp_email.value = emp.get("email_facturacion") or ""
        txt_emp_contacto.value = emp.get("contacto") or ""
        chk_emp_activa.value = bool(emp.get("activa", 1))
        for c in [
            txt_emp_nombre,
            txt_emp_nit,
            txt_emp_direccion,
            txt_emp_ciudad,
            txt_emp_pais,
            txt_emp_telefono,
            txt_emp_email,
            txt_emp_contacto,
            chk_emp_activa,
        ]:
            if c.page is not None:
                c.update()

    # ---------------- Eliminación empresas (FIX) ----------------
    dlg_confirm_borrar_empresa = ft.AlertDialog(modal=True)

    def _refrescar_dropdown_empresas():
        empresas_new = listar_empresas_convenio()  # solo activas por defecto
        dd_empresas.options = [ft.dropdown.Option(str(x["id"]), x["nombre"]) for x in empresas_new]
        if dd_empresas.page is not None:
            dd_empresas.update()

    def _confirmar_borrar_empresa(emp_id: int, emp_nombre: str):
        def _hacer_borrado(_e):
            try:
                borrada_def, msg = eliminar_empresa_convenio(emp_id)  # <- FIX
            except Exception as ex:
                page.snack_bar = ft.SnackBar(content=ft.Text(f"Error al eliminar empresa: {ex}"))
                page.snack_bar.open = True
                page.update()
                return

            dlg_confirm_borrar_empresa.open = False
            page.update()

            # Si estaba cargada en el form, limpiamos
            if empresa_id_sel["value"] == emp_id:
                limpiar_form_empresa()

            # refrescar tabla + dropdown
            cargar_empresas_table()
            _refrescar_dropdown_empresas()

            page.snack_bar = ft.SnackBar(content=ft.Text(msg))
            page.snack_bar.open = True
            page.update()

        dlg_confirm_borrar_empresa.title = ft.Text("Confirmar eliminación")
        dlg_confirm_borrar_empresa.content = ft.Text(
            f"¿Seguro que deseas eliminar la empresa '{emp_nombre}'?\n"
            "Si tiene facturas, se desactivará para conservar el histórico."
        )
        dlg_confirm_borrar_empresa.actions = [
            ft.TextButton(
                "Cancelar",
                on_click=lambda e: setattr(dlg_confirm_borrar_empresa, "open", False) or page.update(),
            ),
            ft.ElevatedButton("Eliminar", icon=ft.Icons.DELETE, on_click=_hacer_borrado),
        ]

        page.dialog = dlg_confirm_borrar_empresa
        dlg_confirm_borrar_empresa.open = True
        page.open(dlg_confirm_borrar_empresa)
        page.update()

    def cargar_empresas_table():
        # OJO: si quieres que "eliminadas/desactivadas" NO se vean acá,
        # cambia a activa_only=True.
        empresas_full = listar_empresas_convenio(activa_only=False)

        empresas_table.rows.clear()
        for emp in empresas_full:
            btn_editar = ft.IconButton(
                icon=ft.Icons.EDIT,
                tooltip="Editar",
                on_click=lambda e, datos=emp: cargar_empresa_en_form(datos),
            )

            btn_eliminar = ft.IconButton(
                icon=ft.Icons.DELETE,
                tooltip="Eliminar",
                on_click=lambda e, eid=emp["id"], nombre=emp.get("nombre") or "": _confirmar_borrar_empresa(eid, nombre),
            )

            acciones = ft.Row([btn_editar, btn_eliminar], spacing=4)

            empresas_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(emp.get("nombre") or "")),
                        ft.DataCell(ft.Text(emp.get("nit") or "")),
                        ft.DataCell(ft.Text(emp.get("ciudad") or "")),
                        ft.DataCell(ft.Text(emp.get("telefono") or "")),
                        ft.DataCell(ft.Text("Sí" if emp.get("activa") else "No")),
                        ft.DataCell(acciones),
                    ]
                )
            )

        if empresas_table.page is not None:
            empresas_table.update()

    # ===================== Guardar empresa ======================

    def guardar_empresa(e):
        nombre = (txt_emp_nombre.value or "").strip()
        if not nombre:
            page.snack_bar = ft.SnackBar(content=ft.Text("El nombre de la empresa es obligatorio."))
            page.snack_bar.open = True
            page.update()
            return

        datos = {
            "id": empresa_id_sel["value"],
            "nombre": nombre,
            "nit": (txt_emp_nit.value or "").strip() or None,
            "direccion": (txt_emp_direccion.value or "").strip() or None,
            "ciudad": (txt_emp_ciudad.value or "").strip() or None,
            "pais": (txt_emp_pais.value or "").strip() or None,
            "telefono": (txt_emp_telefono.value or "").strip() or None,
            "email_facturacion": (txt_emp_email.value or "").strip() or None,
            "contacto": (txt_emp_contacto.value or "").strip() or None,
            "activa": bool(chk_emp_activa.value),
        }

        nuevo_id = guardar_empresa_convenio(datos)
        empresa_id_sel["value"] = nuevo_id

        page.snack_bar = ft.SnackBar(content=ft.Text("Empresa guardada correctamente."))
        page.snack_bar.open = True
        page.update()

        cargar_empresas_table()

        # Refrescar dropdown de creación de facturas
        _refrescar_dropdown_empresas()

    seccion_empresas = ft.Column(
        [
            ft.Text("Empresas de convenio", size=18, weight="bold"),
            ft.Text(
                "Administra las empresas con las que tienes convenios. "
                "Estas aparecerán en la creación de facturas y en los servicios.",
                size=12,
                color=ft.Colors.GREY_700,
            ),
            ft.Divider(),
            ft.Card(
                content=ft.Container(
                    padding=10,
                    content=ft.Column(
                        [
                            ft.Text("Detalle de la empresa", weight="bold"),
                            ft.Row([txt_emp_nombre, txt_emp_nit], spacing=10, wrap=True),
                            ft.Row([txt_emp_direccion], spacing=10, wrap=True),
                            ft.Row([txt_emp_ciudad, txt_emp_pais], spacing=10, wrap=True),
                            ft.Row([txt_emp_telefono, txt_emp_email], spacing=10, wrap=True),
                            ft.Row([txt_emp_contacto], spacing=10, wrap=True),
                            ft.Row([chk_emp_activa], spacing=10, wrap=True),
                            ft.Row(
                                [
                                    ft.TextButton("Nueva empresa", on_click=lambda e: limpiar_form_empresa()),
                                    ft.ElevatedButton("Guardar", on_click=guardar_empresa),
                                ],
                                alignment=ft.MainAxisAlignment.END,
                            ),
                        ],
                        spacing=10,
                    ),
                )
            ),
            ft.Card(
                content=ft.Container(
                    padding=10,
                    content=ft.Column(
                        [
                            ft.Text("Empresas inscritas", weight="bold"),
                            ft.Divider(),
                            empresas_table,
                        ],
                        spacing=10,
                    ),
                )
            ),
        ],
        spacing=15,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )

    # ---------------------------------------------------------------------
    # ===================== Menú lateral + contenido ======================
    # ---------------------------------------------------------------------
    contenido_derecha = ft.Container(expand=True)

    def cambiar_seccion(nueva: str):
        seccion_activa["value"] = nueva
        if nueva == "creacion":
            contenido_derecha.content = seccion_creacion
        elif nueva == "empresas":
            contenido_derecha.content = seccion_empresas

        tile_creacion.selected = nueva == "creacion"
        tile_empresas.selected = nueva == "empresas"

        if contenido_derecha.page is not None:
            contenido_derecha.update()
        if tile_creacion.page is not None:
            tile_creacion.update()
            tile_empresas.update()

    tile_creacion = ft.ListTile(
        leading=ft.Icon(ft.Icons.RECEIPT_LONG),
        title=ft.Text("Creación de facturas"),
        selected=True,
        on_click=lambda e: cambiar_seccion("creacion"),
    )

    tile_empresas = ft.ListTile(
        leading=ft.Icon(ft.Icons.BUSINESS),
        title=ft.Text("Empresas convenio"),
        selected=False,
        on_click=lambda e: cambiar_seccion("empresas"),
    )

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
                ft.Text("Facturación y administración", size=16, weight="bold"),
                ft.Divider(),
                tile_creacion,
                tile_empresas,
            ],
            spacing=5,
        ),
    )

    # Inicializaciones
    items_controls.clear()
    items_column.controls.clear()
    _add_item()  # 👈 solo una vez
    _recalcular_totales()
    _cargar_facturas()
    cargar_empresas_table()

    cambiar_seccion("creacion")  # ✅ esto hace que cargue la vista de creación al entrar

    return ft.Row(
        [
            menu_izquierdo,
            ft.Container(width=16),
            contenido_derecha,
        ],
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
