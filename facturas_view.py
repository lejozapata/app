import os
from datetime import date
from typing import Dict, Any, Optional, List

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
        options=[
            ft.dropdown.Option(str(e["id"]), e["nombre"]) for e in empresas_cache
        ],
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
    # Abrir el DatePicker como un diálogo
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

    # --- Detalle factura ---
    txt_descripcion = ft.TextField(
        label="Detalle",
        width=500,
        multiline=True,
        min_lines=2,
        max_lines=4,
        value="Consulta Psicológica",
    )

    txt_cantidad = ft.TextField(
        label="Cantidad",
        value="1",
        width=100,
    )
    txt_valor_unitario = ft.TextField(
        label="Valor unitario",
        width=150,
        hint_text="Ej: 120000",
    )

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

    txt_subtotal = ft.TextField(
        label="Subtotal",
        read_only=True,
        width=150,
    )
    txt_iva = ft.TextField(
        label="IVA",
        read_only=True,
        width=150,
    )
    txt_total = ft.TextField(
        label="Total",
        read_only=True,
        width=150,
    )

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

    # --- Cálculo de totales ---

    def _recalcular_totales(e=None):
        try:
            cant = float(txt_cantidad.value or 0)
            vu = float(
                (txt_valor_unitario.value or "0")
                .replace(".", "")
                .replace(",", ".")
            )
            porc = float(dd_iva_porcentaje.value or "0")
        except ValueError:
            lbl_mensaje.value = "Error en formato numérico de cantidad / valor / IVA."
            page.update()
            return

        if cant < 0 or vu < 0:
            lbl_mensaje.value = "Cantidad y valor deben ser positivos."
            page.update()
            return

        subtotal = cant * vu
        iva_val = subtotal * porc / 100.0
        total = subtotal + iva_val

        txt_subtotal.value = f"{subtotal:,.0f}".replace(",", ".")
        txt_iva.value = f"{iva_val:,.0f}".replace(",", ".")
        txt_total.value = f"{total:,.0f}".replace(",", ".")

        lbl_mensaje.value = ""
        page.update()

    txt_cantidad.on_change = _recalcular_totales
    txt_valor_unitario.on_change = _recalcular_totales
    dd_iva_porcentaje.on_change = _recalcular_totales
    _recalcular_totales()


     # --- Prefill cuando venimos desde la agenda (facturar convenio) ---
    prefill = None
    try:
        prefill = page.session.get("facturar_desde_agenda")
    except Exception:
        # Fallback por si session no está disponible
        prefill = getattr(page, "facturar_desde_agenda", None)

    if isinstance(prefill, dict):
        # 1) Empresa del convenio (buscamos por nombre)
        nombre_emp = (prefill.get("empresa_nombre") or "").strip()
        if nombre_emp:
            for e in empresas_cache:
                try:
                    n = (e.get("nombre") or "").strip()
                except AttributeError:
                    n = (e["nombre"] or "").strip()
                if n == nombre_emp:
                    dd_empresas.value = str(e["id"])
                    break

        # 2) Paciente
        txt_paciente_nombre.value = prefill.get("paciente_nombre") or ""
        txt_paciente_documento.value = prefill.get("paciente_documento") or ""

        # 3) Precio (va al valor unitario)
        precio = prefill.get("precio")
        if precio is not None:
            try:
                txt_valor_unitario.value = str(int(precio))
            except Exception:
                txt_valor_unitario.value = str(precio)
        else:
            txt_valor_unitario.value = ""

        # Cantidad fija en 1 cuando viene de agenda
        txt_cantidad.value = "1"

        # Fecha sugerida (si viene)
        if prefill.get("fecha"):
            txt_fecha.value = prefill["fecha"]

        # Descripción por defecto
        if not (txt_descripcion.value or "").strip():
            txt_descripcion.value = "Consulta Psicológica"

        # Recalcular totales con los valores precargados
        _recalcular_totales()

        # Limpiar el flag para que no siga prellenando en futuras visitas
        try:
            page.session.remove("facturar_desde_agenda")
        except Exception:
            try:
                delattr(page, "facturar_desde_agenda")
            except Exception:
                pass

    # --- Tabla de facturas existentes ---

    facturas_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Número")),
            ft.DataColumn(ft.Text("Fecha")),
            ft.DataColumn(ft.Text("Empresa")),
            ft.DataColumn(ft.Text("Paciente")),
            ft.DataColumn(ft.Text("Total")),
            ft.DataColumn(ft.Text("Estado")),
            ft.DataColumn(ft.Text("Acciones")),
        ],
        rows=[],
        expand=True,
    )

    def _generar_pdf_desde_ui(factura_id: int):
        """Llama a generar_pdf_factura con el ID de la factura."""
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
        """
        Toggle:
        - pendiente -> pagada
        - pagada -> pendiente
        """
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
        reverse=True,          # 👉 última factura primero
        )
        facturas_table.rows.clear()

        for f in facturas:
            fid = f["id"]
            numero = f["numero"]
            fecha_f = f["fecha"]
            empresa = f.get("empresa_nombre") or ""
            paciente = f.get("paciente_nombre") or ""
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

            # Botón para marcar como pagada (deshabilitado si ya está pagada)
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

            acciones = ft.Row(
                controls=[btn_pagada, btn_pdf, btn_edit, btn_del],
                spacing=4,
            )


            facturas_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(numero))),
                        ft.DataCell(ft.Text(fecha_f)),
                        ft.DataCell(ft.Text(empresa)),
                        ft.DataCell(ft.Text(paciente)),
                        ft.DataCell(ft.Text(total_txt)),
                        ft.DataCell(ft.Text(estado)),
                        ft.DataCell(acciones),
                    ]
                )
            )


        page.update()

    _cargar_facturas()

    # --- Guardar factura en BD ---

    def _guardar_factura(e):
        nonlocal factura_editando_id
        lbl_mensaje.value = ""

        if not dd_empresas.value:
            lbl_mensaje.value = "Selecciona una empresa de convenio."
            page.update()
            return

        if not txt_paciente_nombre.value:
            lbl_mensaje.value = "Selecciona un paciente."
            page.update()
            return

        if not txt_descripcion.value.strip():
            lbl_mensaje.value = "Ingresa la descripción del servicio."
            page.update()
            return

        try:
            cant = float(txt_cantidad.value or 0)
            vu = float(
                (txt_valor_unitario.value or "0")
                .replace(".", "")
                .replace(",", ".")
            )
            porc = float(dd_iva_porcentaje.value or "0")
        except ValueError:
            lbl_mensaje.value = "Error en formato numérico de cantidad / valor / IVA."
            page.update()
            return

        subtotal = cant * vu
        iva_val = subtotal * (porc / 100.0)
        total = subtotal + iva_val

        if total <= 0:
            lbl_mensaje.value = "El total debe ser mayor que 0."
            page.update()
            return

        cabecera = {
            "fecha": txt_fecha.value or date.today().isoformat(),
            "empresa_id": int(dd_empresas.value),
            "paciente_documento": txt_paciente_documento.value or None,
            "paciente_nombre": txt_paciente_nombre.value or "",
            "subtotal": subtotal,
            "iva": iva_val,
            "total": total,
            "total_letras": None,
            "forma_pago": txt_forma_pago.value or None,
            "estado": "pendiente",
        }

        items = [
            {
                "descripcion": txt_descripcion.value.strip(),
                "cantidad": cant,
                "valor_unitario": vu,
                "valor_total": subtotal,
            }
        ]

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
        txt_buscar_paciente.value = ""
        resultados_pacientes.controls.clear()
        txt_paciente_documento.value = ""
        txt_paciente_nombre.value = ""

        txt_descripcion.value = "Consulta Psicológica"
        txt_cantidad.value = "1"
        txt_valor_unitario.value = ""
        dd_iva_porcentaje.value = "0"
        _recalcular_totales()
        
        factura_editando_id = None
        btn_guardar_factura.text = "Guardar factura de convenio"
        btn_guardar_factura.icon = ft.Icons.SAVE

        # Refrescar los controles visibles
        for c in [
            dd_empresas,
            txt_fecha,
            txt_buscar_paciente,
            resultados_pacientes,
            txt_paciente_documento,
            txt_paciente_nombre,
            txt_descripcion,
            txt_cantidad,
            txt_valor_unitario,
            dd_iva_porcentaje,
            txt_subtotal,
            txt_iva,
            txt_total,
        ]:
            if c.page is not None:
                c.update()

        page.snack_bar = ft.SnackBar(content=ft.Text(msg_ok))
        page.snack_bar.open = True

        _cargar_facturas()
        page.update()

    # Estado para edición
    factura_editando_id = None

    btn_guardar_factura = ft.ElevatedButton(
        "Guardar factura de convenio", icon=ft.Icons.SAVE, on_click=_guardar_factura
    )

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
                        wrap=True
                    ),
                    ft.Divider(),
                    ft.Text("Paciente", weight="bold"),
                    ft.Row([txt_buscar_paciente], spacing=10),
                    resultados_pacientes,
                    ft.Row(
                        [
                            txt_paciente_documento,
                            txt_paciente_nombre,
                        ],
                        spacing=10,
                        wrap=True
                    ),
                    ft.Divider(),
                    ft.Text("Detalle", weight="bold"),
                    txt_descripcion,
                    ft.Row(
                        [
                            txt_cantidad,
                            txt_valor_unitario,
                            dd_iva_porcentaje,
                            txt_subtotal,
                            txt_iva,
                            txt_total,
                        ],
                        spacing=10,
                        wrap=True
                    ),
                    ft.Row([txt_forma_pago], spacing=10),
                    lbl_mensaje,
                    ft.Row(
                        [btn_guardar_factura],
                        alignment=ft.MainAxisAlignment.END,
                    ),
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
                    content=ft.Row(  # 👈 wrapper horizontal
                        [
                            ft.Column(
                                [facturas_table],
                                expand=True,
                                scroll=ft.ScrollMode.AUTO,  # vertical (ya lo tenías)
                            )
                        ],
                        scroll=ft.ScrollMode.AUTO,  # 👈 horizontal
                    ),
                ),
            ],
            spacing=10,
        ),
    ),
)


    seccion_creacion = ft.Column(
        [
            card_crear_factura,
            card_listado_facturas,
        ],
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

    def cargar_empresas_table():
        empresas_full = listar_empresas_convenio(activa_only=False)
        empresas_table.rows.clear()
        for emp in empresas_full:
            btn_editar = ft.TextButton(
                "Editar",
                on_click=lambda e, datos=emp: cargar_empresa_en_form(datos),
            )
            empresas_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(emp.get("nombre") or "")),
                        ft.DataCell(ft.Text(emp.get("nit") or "")),
                        ft.DataCell(ft.Text(emp.get("ciudad") or "")),
                        ft.DataCell(ft.Text(emp.get("telefono") or "")),
                        ft.DataCell(ft.Text("Sí" if emp.get("activa") else "No")),
                        ft.DataCell(btn_editar),
                    ]
                )
            )
        if empresas_table.page is not None:
            empresas_table.update()

    def guardar_empresa(e):
        nombre = (txt_emp_nombre.value or "").strip()
        if not nombre:
            page.snack_bar = ft.SnackBar(
                content=ft.Text("El nombre de la empresa es obligatorio."),
            )
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

        page.snack_bar = ft.SnackBar(
            content=ft.Text("Empresa guardada correctamente."),
        )
        page.snack_bar.open = True
        page.update()

        cargar_empresas_table()

        # También refrescar dropdown de creación de facturas
        empresas_new = listar_empresas_convenio()
        dd_empresas.options = [
            ft.dropdown.Option(str(e["id"]), e["nombre"]) for e in empresas_new
        ]
        if dd_empresas.page is not None:
            dd_empresas.update()

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
                                    ft.TextButton(
                                        "Nueva empresa",
                                        on_click=lambda e: limpiar_form_empresa(),
                                    ),
                                    ft.ElevatedButton(
                                        "Guardar", on_click=guardar_empresa
                                    ),
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
    # ===================== CRUD Para Facturas ======================
    # ---------------------------------------------------------------------
    
    def _fmt_num(v):
        try:
            f = float(v)
            if f.is_integer():
                return str(int(f))
            return str(f)
        except Exception:
            return str(v or "")
    
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

        # Cabecera
        dd_empresas.value = str(enc.get("empresa_id") or "")
        txt_fecha.value = enc.get("fecha") or date.today().isoformat()
        txt_paciente_documento.value = enc.get("paciente_documento") or ""
        txt_paciente_nombre.value = enc.get("paciente_nombre") or ""
        txt_forma_pago.value = enc.get("forma_pago") or ""

        # Detalle (tu UI hoy maneja 1 ítem, tomamos el primero)
        if dets:
            d0 = dets[0]
            txt_descripcion.value = d0.get("descripcion") or "Consulta Psicológica"
            txt_cantidad.value = _fmt_num(d0.get("cantidad") or "1")
            txt_valor_unitario.value = _fmt_num(d0.get("valor_unitario") or "")
            # IVA: en tu UI lo calculas por %; si quieres ser exacto,
            # aquí podrías inferir el porcentaje con subtotal/iva, pero lo dejamos en 0 o lo que ya esté.
            # dd_iva_porcentaje.value = "0"

        _recalcular_totales()

        factura_editando_id = fid
        btn_guardar_factura.text = "Actualizar factura"
        btn_guardar_factura.icon = ft.Icons.EDIT

        page.update()
        
    dlg_confirm_borrar = ft.AlertDialog(modal=True)

    def _confirmar_borrar(fid: int, numero: str):
        def _hacer_borrado(e):
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
            ft.TextButton("Cancelar", on_click=lambda e: setattr(dlg_confirm_borrar, "open", False) or page.update()),
            ft.ElevatedButton("Borrar", icon=ft.Icons.DELETE, on_click=_hacer_borrado),
        ]

        page.dialog = dlg_confirm_borrar
        dlg_confirm_borrar.open = True
        page.open(dlg_confirm_borrar)
        page.update()




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
    cargar_empresas_table()
    cambiar_seccion("creacion")

    return ft.Row(
        [
            menu_izquierdo,
            ft.Container(width=16),
            contenido_derecha,
        ],
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
