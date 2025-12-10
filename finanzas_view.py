import flet as ft
from datetime import date

from db import (
    resumen_financiero_mensual,
    registrar_gasto_financiero,
    listar_gastos_financieros,
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


def _formatear_moneda(valor: float) -> str:
    try:
        return f"${valor:,.0f}".replace(",", ".")
    except Exception:
        return str(valor)


def build_finanzas_view(page: ft.Page) -> ft.Control:
    """
    Vista de Finanzas:
      - Resumen mensual de ingresos y gastos
      - Ingresos por citas particulares (virtual / presencial)
      - Ingresos por convenios (facturas)
      - Registro de gastos (arriendo de consultorio, otros)
    """
    hoy = date.today()
    anio_inicial = hoy.year
    mes_inicial = hoy.month

    # Estado interno simple
    estado = {
        "anio": anio_inicial,
        "mes": mes_inicial,
    }

    # --------- Controles cabecera (selección de periodo) ---------

    lbl_titulo = ft.Text(
        "Finanzas",
        size=24,
        weight=ft.FontWeight.BOLD,
    )

    lbl_subtitulo = ft.Text(
        "",
        size=14,
        color=ft.Colors.GREY_700,
    )

    dd_anio = ft.Dropdown(
        label="Año",
        width=120,
        value=str(anio_inicial),
        options=[
            ft.dropdown.Option(str(anio_inicial - 1)),
            ft.dropdown.Option(str(anio_inicial)),
            ft.dropdown.Option(str(anio_inicial + 1)),
            ft.dropdown.Option(str(anio_inicial + 2)),
        ],
    )

    dd_mes = ft.Dropdown(
        label="Mes",
        width=180,
        value=str(mes_inicial),
        options=[
            ft.dropdown.Option(str(i + 1), MESES_NOMBRE[i]) for i in range(12)
        ],
    )

    # --------- KPIs (textos que vamos a ir actualizando) ---------

    lbl_kpi_ingresos_particulares = ft.Text(
        "—", size=20, weight=ft.FontWeight.BOLD
    )
    lbl_kpi_ingresos_convenios = ft.Text(
        "—", size=20, weight=ft.FontWeight.BOLD
    )
    lbl_kpi_gastos = ft.Text("—", size=20, weight=ft.FontWeight.BOLD)
    lbl_kpi_utilidad_cobrada = ft.Text(
        "—", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700
    )

    def _kpi_card(titulo: str, lbl_valor: ft.Text, descripcion: str = "") -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(titulo, size=14, weight=ft.FontWeight.BOLD),
                    lbl_valor,
                    ft.Text(
                        descripcion,
                        size=12,
                        color=ft.Colors.GREY_700,
                    ),
                ],
                spacing=4,
            ),
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.GREY_100,
            expand=True,
        )

    fila_kpis = ft.Row(
        controls=[
            _kpi_card(
                "Ingresos por citas particulares",
                lbl_kpi_ingresos_particulares,
                "Virtual + Presencial (pagadas)",
            ),
            _kpi_card(
                "Ingresos por convenios",
                lbl_kpi_ingresos_convenios,
                "Facturas de convenio (emitidas)",
            ),
            _kpi_card(
                "Gastos",
                lbl_kpi_gastos,
                "Arriendo consultorio + otros",
            ),
            _kpi_card(
                "Utilidad neta (cobrada)",
                lbl_kpi_utilidad_cobrada,
                "Ingresos cobrados – Gastos",
            ),
        ],
        spacing=12,
        run_spacing=12,
        wrap=True,
    )

    # --------- Tablas de detalle ---------

    # Citas particulares y convenios
    tabla_citas = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Concepto")),
            ft.DataColumn(ft.Text("Cantidad")),
            ft.DataColumn(ft.Text("Total")),
        ],
        rows=[],
        expand=True,
    )

    # Facturas convenio por estado
    tabla_facturas = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Estado")),
            ft.DataColumn(ft.Text("Cantidad facturas")),
            ft.DataColumn(ft.Text("Total")),
        ],
        rows=[],
        expand=True,
    )

    # Gastos
    tabla_gastos = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Tipo")),
            ft.DataColumn(ft.Text("Descripción")),
            ft.DataColumn(ft.Text("Fecha")),
            ft.DataColumn(ft.Text("Monto")),
        ],
        rows=[],
        expand=True,
    )

    # --------- Formulario para registrar gasto ---------

    txt_fecha_gasto = ft.TextField(
        label="Fecha del gasto (YYYY-MM-DD)",
        hint_text="YYYY-MM-DD",
        width=180,
    )

    dd_tipo_gasto = ft.Dropdown(
        label="Tipo de gasto",
        width=200,
        value="arriendo_consultorio",
        options=[
            ft.dropdown.Option("arriendo_consultorio", "Arriendo consultorio"),
            ft.dropdown.Option("otro", "Otro gasto"),
        ],
    )

    txt_descripcion_gasto = ft.TextField(
        label="Descripción",
        width=260,
    )

    txt_monto_gasto = ft.TextField(
        label="Monto del gasto",
        width=160,
        text_align=ft.TextAlign.RIGHT,
    )

    lbl_mensaje_gasto = ft.Text("", color=ft.Colors.RED_400, size=12)

    def _registrar_gasto(e):
        lbl_mensaje_gasto.value = ""
        try:
            monto = float((txt_monto_gasto.value or "0").replace(".", "").replace(",", "."))
        except ValueError:
            lbl_mensaje_gasto.value = "Monto inválido."
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
        txt_fecha_gasto.value = ""
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

    # --------- Lógica de refresco de datos ---------

    def _cargar_resumen():
        anio = int(dd_anio.value or anio_inicial)
        mes = int(dd_mes.value or mes_inicial)
        estado["anio"] = anio
        estado["mes"] = mes

        try:
            data = resumen_financiero_mensual(anio, mes)
        except Exception as ex:
            lbl_subtitulo.value = f"Error al cargar datos: {ex}"
            page.update()
            return

        nombre_mes = MESES_NOMBRE[mes - 1]
        lbl_subtitulo.value = f"Resumen financiero de {nombre_mes} {anio}"

        ingresos = data.get("ingresos", {})
        gastos = data.get("gastos", {})
        utilidad = data.get("utilidad", {})

        citas = ingresos.get("citas", {})
        convenios = ingresos.get("convenios", {})

        total_particulares = float(citas.get("total_particulares", 0) or 0)
        total_facturas_emitidas = float(convenios.get("total_facturas_emitidas", 0) or 0)
        total_gastos = float(gastos.get("total_gastos", 0) or 0)
        neta_cobrada = float(utilidad.get("neta_cobrada", 0) or 0)

        lbl_kpi_ingresos_particulares.value = _formatear_moneda(total_particulares)
        lbl_kpi_ingresos_convenios.value = _formatear_moneda(total_facturas_emitidas)
        lbl_kpi_gastos.value = _formatear_moneda(total_gastos)
        lbl_kpi_utilidad_cobrada.value = _formatear_moneda(neta_cobrada)

        # ---- tabla de citas ----
        tabla_citas.rows.clear()

        cant_pres = int(citas.get("presencial", {}).get("cantidad", 0) or 0)
        total_pres = float(citas.get("presencial", {}).get("total", 0) or 0)

        cant_virt = int(citas.get("virtual", {}).get("cantidad", 0) or 0)
        total_virt = float(citas.get("virtual", {}).get("total", 0) or 0)

        cant_conv_citas = int(convenios.get("cantidad_citas", 0) or 0)

        tabla_citas.rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text("Citas presenciales (pagadas)")),
                    ft.DataCell(ft.Text(str(cant_pres))),
                    ft.DataCell(ft.Text(_formatear_moneda(total_pres))),
                ]
            )
        )

        tabla_citas.rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text("Citas virtuales (pagadas)")),
                    ft.DataCell(ft.Text(str(cant_virt))),
                    ft.DataCell(ft.Text(_formatear_moneda(total_virt))),
                ]
            )
        )

        tabla_citas.rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text("Citas de convenio (cantidad de sesiones)")),
                    ft.DataCell(ft.Text(str(cant_conv_citas))),
                    ft.DataCell(ft.Text("—")),
                ]
            )
        )

        # ---- tabla de facturas convenio ----
        tabla_facturas.rows.clear()
        facturas_por_estado = convenios.get("facturas_por_estado", {})

        for estado_fact, info in facturas_por_estado.items():
            cant = int(info.get("cantidad", 0) or 0)
            total = float(info.get("total", 0) or 0)
            tabla_facturas.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(estado_fact.capitalize())),
                        ft.DataCell(ft.Text(str(cant))),
                        ft.DataCell(ft.Text(_formatear_moneda(total))),
                    ]
                )
            )

        # ---- tabla de gastos ----
        tabla_gastos.rows.clear()
        # cargamos gastos individuales para el mes
        # usamos el rango exacto de fechas
        try:
            # reconstruimos el rango del mes a partir de data["rango"]
            fecha_desde = data.get("rango", {}).get("desde")
            fecha_hasta = data.get("rango", {}).get("hasta")
            gastos_detalle = listar_gastos_financieros(
                fecha_desde=fecha_desde, fecha_hasta=fecha_hasta
            )
        except Exception:
            gastos_detalle = []

        for g in gastos_detalle:
            tabla_gastos.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(g.get("tipo", ""))),
                        ft.DataCell(ft.Text(g.get("descripcion", "") or "")),
                        ft.DataCell(ft.Text(g.get("fecha", ""))),
                        ft.DataCell(ft.Text(_formatear_moneda(float(g.get("monto", 0) or 0)))),
                    ]
                )
            )

        page.update()

    def _cambio_periodo(e):
        _cargar_resumen()

    dd_anio.on_change = _cambio_periodo
    dd_mes.on_change = _cambio_periodo

    # --------- Layout principal ---------

    cabecera = ft.Row(
        controls=[
            ft.Column(
                [lbl_titulo, lbl_subtitulo],
                spacing=2,
                expand=True,
            ),
            ft.Row([dd_anio, dd_mes], spacing=8),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    contenido = ft.Column(
        [
            cabecera,
            ft.Divider(),
            fila_kpis,
            ft.Divider(),
            ft.Text(
                "Detalle de ingresos",
                size=16,
                weight=ft.FontWeight.BOLD,
            ),
            tabla_citas,
            ft.Text(
                "Facturas de convenio",
                size=16,
                weight=ft.FontWeight.BOLD,
            ),
            tabla_facturas,
            ft.Divider(),
            formulario_gasto,
            ft.Text(
                "Gastos registrados en el mes",
                size=16,
                weight=ft.FontWeight.BOLD,
            ),
            tabla_gastos,
        ],
        spacing=12,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )

    # Cargar datos iniciales
    _cargar_resumen()

    # Devolvemos un Container para que el main lo meta en la vista
    return ft.Container(
        content=contenido,
        expand=True,
        padding=20,
    )
