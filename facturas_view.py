import os
from datetime import date
from typing import Dict, Any, Optional, List

import flet as ft

from facturas_pdf import generar_pdf_factura
from db import (
    listar_empresas_convenio,
    listar_pacientes,
    crear_factura_convenio,
    listar_facturas_convenio,
    guardar_empresa_convenio,
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
    )

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
            ruta = generar_pdf_factura(factura_id, abrir=True)
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

    def _cargar_facturas():
        facturas = listar_facturas_convenio()
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

            facturas_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(numero))),
                        ft.DataCell(ft.Text(fecha_f)),
                        ft.DataCell(ft.Text(empresa)),
                        ft.DataCell(ft.Text(paciente)),
                        ft.DataCell(ft.Text(total_txt)),
                        ft.DataCell(ft.Text(estado)),
                        ft.DataCell(btn_pdf),
                    ]
                )
            )

        page.update()

    _cargar_facturas()

    # --- Guardar factura en BD ---

    def _guardar_factura(e):
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

        descripcion_base = (txt_descripcion.value or "").strip() or "Consulta Psicológica"
        nombre_paciente = (txt_paciente_nombre.value or "").strip()

        if nombre_paciente:
            descripcion_final = f"{descripcion_base} de {nombre_paciente}"
        else:
            descripcion_final = descripcion_base

        items = [
            {
                "descripcion": descripcion_final,
                "cantidad": cant,
                "valor_unitario": vu,
            }
        ]

        try:
            factura_creada = crear_factura_convenio(cabecera, items)
        except Exception as ex:
            lbl_mensaje.value = f"Error al guardar la factura: {ex}"
            page.update()
            return

        # Limpiar formulario
        txt_descripcion.value = ""
        txt_cantidad.value = "1"
        txt_valor_unitario.value = ""
        dd_iva_porcentaje.value = "0"
        _recalcular_totales()

        page.snack_bar = ft.SnackBar(
            content=ft.Text(
                f"Factura creada correctamente (No. {factura_creada['numero']})."
            )
        )
        page.snack_bar.open = True

        _cargar_facturas()
        page.update()

    btn_guardar_factura = ft.ElevatedButton(
        "Guardar factura de convenio", icon=ft.Icons.SAVE, on_click=_guardar_factura
    )

    card_crear_factura = ft.Card(
        content=ft.Container(
            padding=10,
            content=ft.Column(
                [
                    ft.Text("Creación de facturas", size=18, weight="bold"),
                    ft.Row([dd_empresas, txt_fecha], spacing=10),
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
                    facturas_table,
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
                            ft.Row([txt_emp_nombre, txt_emp_nit], spacing=10),
                            ft.Row([txt_emp_direccion], spacing=10),
                            ft.Row([txt_emp_ciudad, txt_emp_pais], spacing=10),
                            ft.Row([txt_emp_telefono, txt_emp_email], spacing=10),
                            ft.Row([txt_emp_contacto], spacing=10),
                            ft.Row([chk_emp_activa], spacing=10),
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
    # ================== 3. SECCIÓN: FINANZAS (placeholder) ===============
    # ---------------------------------------------------------------------

    seccion_finanzas = ft.Column(
        [
            ft.Text("Finanzas", size=18, weight="bold"),
            ft.Text(
                "Más adelante verás aquí un resumen financiero de facturas, pagos y convenios.",
                size=12,
                color=ft.Colors.GREY_700,
            ),
            ft.Divider(),
            ft.Text("Esta sección está en construcción."),
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
        elif nueva == "finanzas":
            contenido_derecha.content = seccion_finanzas

        tile_creacion.selected = nueva == "creacion"
        tile_empresas.selected = nueva == "empresas"
        tile_finanzas.selected = nueva == "finanzas"

        if contenido_derecha.page is not None:
            contenido_derecha.update()
        if tile_creacion.page is not None:
            tile_creacion.update()
            tile_empresas.update()
            tile_finanzas.update()

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

    tile_finanzas = ft.ListTile(
        leading=ft.Icon(ft.Icons.ANALYTICS),
        title=ft.Text("Finanzas"),
        selected=False,
        on_click=lambda e: cambiar_seccion("finanzas"),
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
                tile_finanzas,
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
