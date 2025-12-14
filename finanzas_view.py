import flet as ft
from datetime import date, datetime

from db import (
    resumen_financiero_mensual,
    registrar_gasto_financiero,
    listar_gastos_financieros,
    eliminar_gasto_financiero,
    registrar_paquete_arriendo,
    resumen_paquetes_arriendo,
)

MESES_NOMBRE = [
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


def _fmt(valor):
    try:
        return f"${valor:,.0f}".replace(",", ".")
    except Exception:
        return str(valor)


def build_finanzas_view(page: ft.Page) -> ft.Control:
    """
    Vista principal de Finanzas.
    MAIN LA INVOCA COMO: build_finanzas_view(page)
    """

    hoy = date.today()
    anio_actual = hoy.year
    mes_actual = hoy.month

    # ----------------- ENCABEZADO Y FILTROS -----------------
    lbl_titulo = ft.Text("Finanzas", size=24, weight=ft.FontWeight.BOLD)
    lbl_subtitulo = ft.Text("", size=14, color=ft.Colors.GREY_700)

    dd_anio = ft.Dropdown(
        label="Año",
        value=str(anio_actual),
        width=120,
        options=[
            ft.dropdown.Option(str(anio_actual - 1)),
            ft.dropdown.Option(str(anio_actual)),
            ft.dropdown.Option(str(anio_actual + 1)),
        ],
    )

    dd_mes = ft.Dropdown(
        label="Mes",
        value=str(mes_actual),
        width=150,
        options=[ft.dropdown.Option(str(i + 1), MESES_NOMBRE[i]) for i in range(12)],
    )

    # ----------------- KPIs PRINCIPALES -----------------
    kpi_particulares = ft.Text("—", size=20, weight=ft.FontWeight.BOLD)
    kpi_convenios = ft.Text("—", size=20, weight=ft.FontWeight.BOLD)
    kpi_gastos = ft.Text("—", size=20, weight=ft.FontWeight.BOLD)
    kpi_utilidad = ft.Text("—", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN)

    card_particulares = ft.Card(
        content=ft.Container(
            content=ft.Column(
                [ft.Text("Ingresos particulares", size=12, color=ft.Colors.GREY_700), kpi_particulares],
                spacing=4,
            ),
            padding=12,
        )
    )

    card_convenios = ft.Card(
        content=ft.Container(
            content=ft.Column(
                [ft.Text("Ingresos convenios", size=12, color=ft.Colors.GREY_700), kpi_convenios],
                spacing=4,
            ),
            padding=12,
        )
    )

    card_gastos = ft.Card(
        content=ft.Container(
            content=ft.Column(
                [ft.Text("Gastos", size=12, color=ft.Colors.GREY_700), kpi_gastos],
                spacing=4,
            ),
            padding=12,
        )
    )

    card_utilidad = ft.Card(
        content=ft.Container(
            content=ft.Column(
                [ft.Text("Utilidad neta", size=12, color=ft.Colors.GREY_700), kpi_utilidad],
                spacing=4,
            ),
            padding=12,
        )
    )

    fila_kpis = ft.Row(
        [card_particulares, card_convenios, card_gastos, card_utilidad],
        spacing=12,
        wrap=True,
    )

    # ----------------- TABLAS DE DETALLE -----------------

    tabla_ingresos = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Concepto")),
            ft.DataColumn(ft.Text("Cantidad")),
            ft.DataColumn(ft.Text("Total")),
        ],
        rows=[],
        column_spacing=20,
    )

    tabla_facturas = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Estado facturas convenio")),
            ft.DataColumn(ft.Text("Cantidad")),
            ft.DataColumn(ft.Text("Total")),
        ],
        rows=[],
        column_spacing=20,
    )

    tabla_gastos = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Tipo")),
            ft.DataColumn(ft.Text("Descripción")),
            ft.DataColumn(ft.Text("Fecha")),
            ft.DataColumn(ft.Text("Monto")),
            ft.DataColumn(ft.Text("Acciones")),
        ],
        rows=[],
        column_spacing=16,
    )

    # ----------------- FORMULARIO DE GASTOS -----------------

    txt_fecha_gasto = ft.TextField(
        label="Fecha",
        value=date.today().isoformat(),
        width=160,
        read_only=True,
    )
    
     # ---- DatePicker para fecha de gasto ----
    datepicker_gasto = ft.DatePicker(
        help_text="Selecciona la fecha del gasto",
        first_date=datetime(2020, 1, 1),
        last_date=datetime.now(),
        #date_picker_entry_mode=ft.DatePickerEntryMode.CALENDAR_ONLY,
    )

    # lo agregamos a los overlays de la página para poder abrirlo
    page.overlay.append(datepicker_gasto)

    def _actualizar_fecha_desde_datepicker_gasto(e: ft.ControlEvent):
        """
        Cuando el usuario elige una fecha en el datepicker,
        actualizamos el TextField en formato YYYY-MM-DD.
        """
        if not e.control.value:
            return

        d: date = e.control.value
        txt_fecha_gasto.value = d.strftime("%Y-%m-%d")
        txt_fecha_gasto.error_text = None
        page.update()

    datepicker_gasto.on_change = _actualizar_fecha_desde_datepicker_gasto

    def _abrir_datepicker_gasto(e):
        """
        Abre el datepicker de gasto, intentando posicionarlo
        en la fecha escrita (si es válida).
        """
        valor = (txt_fecha_gasto.value or "").strip()
        if valor:
            try:
                d = datetime.strptime(valor, "%Y-%m-%d").date()
                datepicker_gasto.value = d
            except ValueError:
                datepicker_gasto.value = None
        else:
            datepicker_gasto.value = None

        page.open(datepicker_gasto)

    # iconito de calendario al final del campo de fecha
    txt_fecha_gasto.suffix = ft.IconButton(
        icon=ft.Icons.CALENDAR_MONTH,
        tooltip="Abrir calendario",
        on_click=_abrir_datepicker_gasto,
    )

    dd_tipo_gasto = ft.Dropdown(
        label="Tipo",
        value="arriendo_consultorio",
        width=200,
        options=[
            ft.dropdown.Option("carro", "Carro"),
            ft.dropdown.Option("hogar", "Hogar"),
            ft.dropdown.Option("ocio", "Ocio/Hobbies"),
            ft.dropdown.Option("otro", "Otro gasto"),
        ],
    )
    txt_descripcion_gasto = ft.TextField(label="Descripción", width=260)
    txt_monto_gasto = ft.TextField(label="Monto", width=140)
    lbl_mensaje_gasto = ft.Text("", color=ft.Colors.RED_400, size=12)

    def _registrar_gasto(e):
        lbl_mensaje_gasto.value = ""
        page.update()

        try:
            monto = float(txt_monto_gasto.value or "0")
        except ValueError:
            lbl_mensaje_gasto.value = "El monto debe ser número."
            page.update()
            return

        if monto <= 0:
            lbl_mensaje_gasto.value = "El monto debe ser mayor que cero."
            page.update()
            return

        fecha = (txt_fecha_gasto.value or "").strip()
        tipo = dd_tipo_gasto.value or "otro"
        descripcion = (txt_descripcion_gasto.value or "").strip()

        try:
            registrar_gasto_financiero(
                {
                    "fecha": fecha,
                    "tipo": tipo,
                    "descripcion": descripcion,
                    "monto": monto,
                }
            )
        except Exception as ex:
            lbl_mensaje_gasto.value = f"Error al guardar el gasto: {ex}"
            page.update()
            return

        # limpiar campos
        txt_fecha_gasto.value = date.today().isoformat()
        txt_descripcion_gasto.value = ""
        txt_monto_gasto.value = ""

        page.snack_bar = ft.SnackBar(
            content=ft.Text("Gasto registrado."),
            bgcolor=ft.Colors.GREEN_300,
        )
        page.snack_bar.open = True

        _cargar_resumen()
        page.update()

    btn_registrar_gasto = ft.ElevatedButton(
        text="Registrar gasto",
        icon=ft.Icons.SAVE,
        on_click=_registrar_gasto,
    )

    formulario_gasto = ft.Column(
        [
            ft.Text(
                "Registrar gasto (arriendo consultorio u otros)",
                size=14,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Row(
                [
                    txt_fecha_gasto,
                    dd_tipo_gasto,
                    txt_descripcion_gasto,
                    txt_monto_gasto,
                    btn_registrar_gasto,
                ],
                spacing=8,
                wrap=True,
            ),
            lbl_mensaje_gasto,
        ],
        spacing=8,
    )

    # ----------------- SECCIÓN PAQUETES DE ARRIENDO -----------------

    txt_fecha_paquete = ft.TextField(
        label="Fecha",
        value=date.today().isoformat(),
        width=160,
        read_only=True,
    )

        # ---- DatePicker para fecha de compra del paquete ----
    datepicker_paquete = ft.DatePicker(
        help_text="Selecciona la fecha del paquete",
        first_date=datetime(2020, 1, 1),
        last_date=datetime.now(),
        #date_picker_entry_mode=ft.DatePickerEntryMode.CALENDAR_ONLY,
    )

    page.overlay.append(datepicker_paquete)

    def _actualizar_fecha_desde_datepicker_paquete(e: ft.ControlEvent):
        if not e.control.value:
            return

        d: date = e.control.value
        txt_fecha_paquete.value = d.strftime("%Y-%m-%d")
        txt_fecha_paquete.error_text = None
        page.update()

    datepicker_paquete.on_change = _actualizar_fecha_desde_datepicker_paquete

    def _abrir_datepicker_paquete(e):
        valor = (txt_fecha_paquete.value or "").strip()
        if valor:
            try:
                d = datetime.strptime(valor, "%Y-%m-%d").date()
                datepicker_paquete.value = d
            except ValueError:
                datepicker_paquete.value = None
        else:
            datepicker_paquete.value = None

        page.open(datepicker_paquete)

    txt_fecha_paquete.suffix = ft.IconButton(
        icon=ft.Icons.CALENDAR_MONTH,
        tooltip="Abrir calendario",
        on_click=_abrir_datepicker_paquete,
    )



    txt_cantidad_citas = ft.TextField(
        label="# citas en paquete",
        width=150,
    )
    txt_costo_paquete = ft.TextField(
        label="Costo total paquete",
        width=170,
    )
    txt_descripcion_paquete = ft.TextField(
        label="Descripción / referencia",
        width=260,
    )
    lbl_mensaje_paquete = ft.Text("", color=ft.Colors.RED_400, size=12)

    # labels de resumen de paquetes
    lbl_paq_resumen = ft.Text("", size=13, color=ft.Colors.GREY_800)
    lbl_paq_detalle = ft.Text("", size=12, color=ft.Colors.GREY_700)

    def _cargar_resumen_paquetes():
        try:
            info = resumen_paquetes_arriendo() or {}
        except Exception as ex:
            lbl_paq_resumen.value = f"Error al cargar paquetes: {ex}"
            lbl_paq_detalle.value = ""
            page.update()
            return

        total_citas = int(info.get("total_citas", 0) or 0)
        citas_usadas = int(info.get("citas_usadas", 0) or 0)
        citas_disponibles = int(info.get("citas_disponibles", 0) or 0)
        costo_total = float(info.get("costo_total", 0) or 0)

        if total_citas <= 0:
            lbl_paq_resumen.value = "No hay paquetes de arriendo registrados."
            lbl_paq_detalle.value = ""
        else:
            costo_promedio = costo_total / total_citas if total_citas > 0 else 0.0
            lbl_paq_resumen.value = (
                f"Paquetes de arriendo: {total_citas} citas totales, "
                f"{citas_usadas} usadas, {citas_disponibles} disponibles."
            )
            lbl_paq_detalle.value = (
                f"Costo total acumulado: {_fmt(costo_total)}  "
                f"· Costo promedio por cita: {_fmt(costo_promedio)}"
            )

        page.update()

    def _registrar_paquete(e):
        lbl_mensaje_paquete.value = ""
        page.update()

        try:
            cantidad = int(txt_cantidad_citas.value or "0")
        except ValueError:
            lbl_mensaje_paquete.value = "La cantidad de citas debe ser un número entero."
            page.update()
            return

        try:
            costo = float(txt_costo_paquete.value or "0")
        except ValueError:
            lbl_mensaje_paquete.value = "El costo total debe ser numérico."
            page.update()
            return

        if cantidad <= 0:
            lbl_mensaje_paquete.value = "La cantidad de citas debe ser mayor que cero."
            page.update()
            return

        if costo <= 0:
            lbl_mensaje_paquete.value = "El costo total debe ser mayor que cero."
            page.update()
            return

        fecha_compra = (txt_fecha_paquete.value or "").strip()
        if not fecha_compra:
            fecha_compra = hoy.strftime("%Y-%m-%d")
        else:
            # validación simple de formato
            try:
                datetime.strptime(fecha_compra, "%Y-%m-%d")
            except ValueError:
                lbl_mensaje_paquete.value = "Fecha de compra inválida. Usa formato YYYY-MM-DD."
                page.update()
                return

        descripcion = (txt_descripcion_paquete.value or "").strip()

        try:
            registrar_paquete_arriendo(
                {
                    "fecha_compra": fecha_compra,
                    "cantidad_citas": cantidad,
                    "precio_total": costo,
                    "descripcion": descripcion,
                }
            )
        except Exception as ex:
            lbl_mensaje_paquete.value = f"Error al registrar paquete: {ex}"
            page.update()
            return

        # limpiar
        txt_fecha_paquete.value = date.today().isoformat()
        txt_cantidad_citas.value = ""
        txt_costo_paquete.value = ""
        txt_descripcion_paquete.value = ""

        page.snack_bar = ft.SnackBar(
            content=ft.Text("Paquete de arriendo registrado."),
            bgcolor=ft.Colors.GREEN_300,
        )
        page.snack_bar.open = True

        _cargar_resumen_paquetes()
        _cargar_resumen()
        page.update()

    btn_registrar_paquete = ft.ElevatedButton(
        text="Registrar paquete",
        icon=ft.Icons.SAVE,
        on_click=_registrar_paquete,
    )

    seccion_paquetes = ft.Column(
        [
            ft.Text(
                "Paquetes de arriendo de consultorio",
                size=14,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Text(
                "Aquí Sara registra los paquetes que compra para el consultorio. "
                "Más adelante los vamos a consumir automáticamente con las citas presenciales.",
                size=11,
                color=ft.Colors.GREY_700,
            ),
            ft.Row(
                [
                    txt_fecha_paquete,
                    txt_cantidad_citas,
                    txt_costo_paquete,
                    txt_descripcion_paquete,
                    btn_registrar_paquete,
                ],
                spacing=8,
                wrap=True,
            ),
            lbl_mensaje_paquete,
            lbl_paq_resumen,
            lbl_paq_detalle,
        ],
        spacing=6,
    )

    # ----------------- LÓGICA DE CARGA DE RESUMEN -----------------

    def _cargar_resumen():
        # limpiar mensaje de error de gastos (si hubo errores anteriores)
        lbl_mensaje_gasto.value = ""

        try:
            anio = int(dd_anio.value or anio_actual)
            mes = int(dd_mes.value or mes_actual)
        except ValueError:
            anio = anio_actual
            mes = mes_actual

        try:
            data = resumen_financiero_mensual(anio, mes)
        except Exception as ex:
            lbl_subtitulo.value = f"Error al cargar datos: {ex}"
            # vaciar tablas
            tabla_ingresos.rows = []
            tabla_facturas.rows = []
            tabla_gastos.rows = []
            page.update()
            return

        nombre_mes = MESES_NOMBRE[mes - 1]
        lbl_subtitulo.value = f"Resumen financiero de {nombre_mes} {anio}"

        ingresos = data.get("ingresos", {}) or {}
        gastos = data.get("gastos", {}) or {}
        utilidad = data.get("utilidad", {}) or {}

        citas = ingresos.get("citas", {}) or {}
        convenios = ingresos.get("convenios", {}) or {}

        total_particulares = float(citas.get("total_particulares", 0) or 0)
        cantidad_citas_pagadas = int(citas.get("cantidad_citas_pagadas", 0) or 0)

        total_facturas_emitidas = float(
            convenios.get("total_facturas_emitidas", 0) or 0
        )
        cantidad_facturas_emitidas = int(
            convenios.get("cantidad_facturas_emitidas", 0) or 0
        )

        total_facturas_pagadas = float(
            convenios.get("total_facturas_pagadas", 0) or 0
        )
        cantidad_facturas_pagadas = int(
            convenios.get("cantidad_facturas_pagadas", 0) or 0
        )
        total_facturas_pendientes = float(
            convenios.get("total_facturas_pendientes", 0) or 0
        )
        cantidad_facturas_pendientes = int(
            convenios.get("cantidad_facturas_pendientes", 0) or 0
        )

        total_gastos = float(gastos.get("total_gastos", 0) or 0)
        neta_cobrada = float(utilidad.get("neta_cobrada", 0) or 0)

        # KPIs
        kpi_particulares.value = _fmt(total_particulares)
        kpi_convenios.value = _fmt(total_facturas_pagadas)
        kpi_gastos.value = _fmt(total_gastos)
        kpi_utilidad.value = _fmt(neta_cobrada)

        # Tabla ingresos
        tabla_ingresos.rows = [
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text("Citas particulares pagadas")),
                    ft.DataCell(ft.Text(str(cantidad_citas_pagadas))),
                    ft.DataCell(ft.Text(_fmt(total_particulares))),
                ]
            ),
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text("Facturas de convenio emitidas")),
                    ft.DataCell(ft.Text(str(cantidad_facturas_emitidas))),
                    ft.DataCell(ft.Text(_fmt(total_facturas_emitidas))),
                ]
            ),
        ]

        # Tabla facturas
        tabla_facturas.rows = [
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text("Facturas pagadas")),
                    ft.DataCell(ft.Text(str(cantidad_facturas_pagadas))),
                    ft.DataCell(ft.Text(_fmt(total_facturas_pagadas))),
                ]
            ),
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text("Facturas pendientes")),
                    ft.DataCell(ft.Text(str(cantidad_facturas_pendientes))),
                    ft.DataCell(ft.Text(_fmt(total_facturas_pendientes))),
                ]
            ),
        ]

        # Tabla gastos (detalle)
        # rango del mes: del 1 al último día
        fecha_desde = f"{anio}-{mes:02d}-01"
        if mes == 12:
            fecha_hasta = f"{anio}-12-31"
        else:
            fecha_hasta = f"{anio}-{mes+1:02d}-01"

        try:
            gastos_lista = listar_gastos_financieros(
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                tipo=None,
            )
        except Exception as ex:
            gastos_lista = []
            lbl_mensaje_gasto.value = f"Error al cargar gastos: {ex}"

        filas_gastos = []

        for g in gastos_lista:
            gid = g.get("id")
            tipo = g.get("tipo", "")
            descripcion = g.get("descripcion", "")
            fecha_g = g.get("fecha", "")
            monto_g = float(g.get("monto", 0) or 0)

            def _make_delete_handler(id_gasto: int):
                def _handler(ev):
                    try:
                        eliminar_gasto_financiero(id_gasto)
                    except Exception as ex:
                        page.snack_bar = ft.SnackBar(
                            content=ft.Text(f"Error al eliminar gasto: {ex}"),
                            bgcolor=ft.Colors.RED_200,
                        )
                        page.snack_bar.open = True
                        page.update()
                        return

                    page.snack_bar = ft.SnackBar(
                        content=ft.Text("Gasto eliminado."),
                        bgcolor=ft.Colors.GREEN_300,
                    )
                    page.snack_bar.open = True
                    _cargar_resumen()
                    page.update()

                return _handler

            btn_del = ft.IconButton(
                icon=ft.Icons.DELETE,
                tooltip="Eliminar gasto",
                icon_color=ft.Colors.RED_300,
                on_click=_make_delete_handler(gid),
            )

            filas_gastos.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(tipo)),
                        ft.DataCell(ft.Text(descripcion)),
                        ft.DataCell(ft.Text(fecha_g)),
                        ft.DataCell(ft.Text(_fmt(monto_g))),
                        ft.DataCell(btn_del),
                    ]
                )
            )

        tabla_gastos.rows = filas_gastos

        # actualizar resumen de paquetes también (porque afectan la lectura mental de Sara)
        _cargar_resumen_paquetes()

        page.update()

    # Eventos de cambio de filtros
    def _on_cambio_filtros(e):
        _cargar_resumen()

    dd_anio.on_change = _on_cambio_filtros
    dd_mes.on_change = _on_cambio_filtros

    # Cargar datos iniciales
    _cargar_resumen()
    _cargar_resumen_paquetes()

    # ----------------- LAYOUT GENERAL -----------------

    filtros_row = ft.Row(
        [
            dd_anio,
            dd_mes,
        ],
        spacing=12,
    )

    tablas_column = ft.Column(
        [
            ft.Text("Ingresos", size=16, weight=ft.FontWeight.BOLD),
            tabla_ingresos,
            ft.Container(height=12),
            ft.Text("Facturas de convenio", size=16, weight=ft.FontWeight.BOLD),
            tabla_facturas,
            ft.Container(height=12),
            ft.Text("Gastos detallados", size=16, weight=ft.FontWeight.BOLD),
            tabla_gastos,
        ],
        spacing=8,
    )

    contenido = ft.Column(
        [
            lbl_titulo,
            lbl_subtitulo,
            filtros_row,
            ft.Container(height=8),
            fila_kpis,
            ft.Container(height=16),
            tablas_column,
            ft.Container(height=16),
            formulario_gasto,
            ft.Container(height=16),
            seccion_paquetes,
        ],
        spacing=10,
        scroll=ft.ScrollMode.ALWAYS,
    )

    return ft.Container(
        content=contenido,
        padding=16,
    )
