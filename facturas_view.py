import flet as ft
from datetime import date
from typing import List, Dict, Any, Optional
from facturas_pdf import generar_pdf_factura
import os

from db import (
    listar_empresas_convenio,
    listar_pacientes,
    crear_factura_convenio,
    listar_facturas_convenio,
)


def build_facturas_view(page: ft.Page) -> ft.Control:
    """
    Vista principal de facturación de convenios.
    Permite:
    - Ver listado de facturas
    - Crear una nueva factura (solo BD, sin PDF todavía)
    """

    # -------------------- Estado en memoria --------------------
    empresas = listar_empresas_convenio()
    pacientes_cache = listar_pacientes()

    # Campos del formulario de nueva factura
    dd_empresas = ft.Dropdown(
        label="Empresa del convenio",
        options=[
            ft.dropdown.Option(str(e["id"]), e["nombre"]) for e in empresas
        ],
        width=350,
    )

    txt_fecha = ft.TextField(
        label="Fecha factura",
        value=date.today().isoformat(),
        width=160,
    )

    # -------- Paciente --------
    txt_buscar_paciente = ft.TextField(
        label="Buscar paciente (nombre o documento)",
        width=350,
    )
    resultados_pacientes = ft.Column(spacing=0, tight=True)

    txt_paciente_nombre = ft.TextField(
        label="Paciente",
        read_only=True,
        width=350,
    )
    txt_paciente_documento = ft.TextField(
        label="Documento",
        read_only=True,
        width=200,
    )

    # -------- Detalle (1 ítem por ahora) --------
    txt_descripcion = ft.TextField(
        label="Descripción",
        width=500,
    )
    txt_cantidad = ft.TextField(
        label="Cantidad",
        width=100,
        value="1",
    )
    txt_valor_unitario = ft.TextField(
        label="Valor unitario",
        width=150,
    )

    txt_subtotal = ft.TextField(
        label="Subtotal",
        read_only=True,
        width=150,
    )
    dd_iva_porcentaje = ft.Dropdown(
        label="IVA %",
        options=[
            ft.dropdown.Option("0", "0%"),
            ft.dropdown.Option("19", "19%"),
        ],
        value="0",
        width=120,
    )

    txt_iva = ft.TextField(
        label="IVA",
        read_only=True,
        value="0",
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

    # -------------------- Helpers --------------------

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
    txt_iva.on_change = _recalcular_totales

    # --- Búsqueda de pacientes ---

    def _seleccionar_paciente(pac_row):
        txt_paciente_nombre.value = pac_row["nombre_completo"]
        txt_paciente_documento.value = pac_row["documento"]
        txt_buscar_paciente.value = ""
        resultados_pacientes.controls.clear()

        # Descripción sugerida
        txt_descripcion.value = (
            f"Consulta psicológica de {pac_row['nombre_completo']}"
        )

        page.update()

    def _filtrar_pacientes(e=None):
        query = (txt_buscar_paciente.value or "").strip().lower()
        resultados_pacientes.controls.clear()

        if not query:
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
                content=ft.Text(f"Error al generar PDF: {ex}"),
                bgcolor=ft.Colors.RED_300,
            )
            page.snack_bar.open = True
            page.update()

    def _cargar_facturas():
        facturas_table.rows.clear()
        for f in listar_facturas_convenio():
            fid = f["id"]
            facturas_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(f["numero"])),
                        ft.DataCell(ft.Text(f["fecha"])),
                        ft.DataCell(ft.Text(f.get("empresa_nombre", ""))),
                        ft.DataCell(ft.Text(f.get("paciente_nombre", ""))),
                        ft.DataCell(
                            ft.Text(f"{f['total']:,.0f}".replace(",", "."))
                        ),
                        ft.DataCell(ft.Text(f.get("estado", ""))),
                        ft.DataCell(
                            ft.IconButton(
                                icon=ft.Icons.PICTURE_AS_PDF,
                                tooltip="Generar PDF",
                                on_click=lambda e, fid=fid: _generar_pdf_desde_ui(fid),
                            )
                        ),
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
        iva_val = subtotal * porc / 100.0

        if cant <= 0 or vu <= 0:
            lbl_mensaje.value = (
                "Cantidad y valor unitario deben ser mayores que cero."
            )
            page.update()
            return

        datos_cabecera = {
            "fecha": txt_fecha.value or date.today().isoformat(),
            "empresa_id": int(dd_empresas.value),
            "paciente_documento": txt_paciente_documento.value or None,
            "paciente_nombre": txt_paciente_nombre.value,
            "forma_pago": txt_forma_pago.value or None,
            "iva": iva_val,
        }

        items = [
            {
                "descripcion": txt_descripcion.value.strip(),
                "cantidad": cant,
                "valor_unitario": vu,
            }
        ]

        try:
            resultado = crear_factura_convenio(datos_cabecera, items)
        except Exception as ex:
            lbl_mensaje.value = f"Error al crear la factura: {ex}"
            page.update()
            return

        # Limpiar campos de detalle y paciente (no la empresa)
        txt_descripcion.value = ""
        txt_cantidad.value = "1"
        txt_valor_unitario.value = ""
        txt_subtotal.value = ""
        txt_iva.value = "0"
        txt_total.value = ""
        txt_paciente_nombre.value = ""
        txt_paciente_documento.value = ""
        txt_buscar_paciente.value = ""
        dd_iva_porcentaje.value = "0"
        txt_iva.value = "0"
        resultados_pacientes.controls.clear()

        page.snack_bar = ft.SnackBar(
            content=ft.Text(f"Factura {resultado['numero']} creada correctamente."),
            bgcolor=ft.Colors.GREEN_300,
        )
        page.snack_bar.open = True

        _cargar_facturas()

    btn_guardar = ft.ElevatedButton("Guardar factura", on_click=_guardar_factura)

    # -------------------- Layout --------------------

    formulario = ft.Card(
        content=ft.Container(
            padding=15,
            content=ft.Column(
                [
                    ft.Text("Nueva factura de convenio", size=18, weight="bold"),
                    ft.Row([dd_empresas, txt_fecha], spacing=10),
                    ft.Divider(),
                    ft.Text("Paciente", weight="bold"),
                    txt_buscar_paciente,
                    resultados_pacientes,
                    ft.Row(
                        [txt_paciente_nombre, txt_paciente_documento],
                        spacing=10,
                    ),
                    ft.Divider(),
                    ft.Text("Detalle", weight="bold"),
                    txt_descripcion,
                    ft.Row([txt_cantidad, txt_valor_unitario], spacing=10),
                    ft.Row(
                        [txt_subtotal, dd_iva_porcentaje, txt_iva, txt_total],
                        spacing=10,
                    ),
                    txt_forma_pago,
                    lbl_mensaje,
                    ft.Row(
                        [btn_guardar],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
                spacing=10,
            ),
        ),
        expand=False,
    )

    listado = ft.Card(
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
        expand=True,
    )

    return ft.Column(
        [
            formulario,
            listado,
        ],
        spacing=20,
        expand=True,
    )
