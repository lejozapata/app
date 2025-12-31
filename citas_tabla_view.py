import flet as ft
from datetime import date, datetime, timedelta

from .db import listar_citas_con_paciente_rango, eliminar_cita, get_connection


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def _month_end(d: date) -> date:
    # último día del mes: primer día del mes siguiente - 1 día
    if d.month == 12:
        next_m = date(d.year + 1, 1, 1)
    else:
        next_m = date(d.year, d.month + 1, 1)
    return next_m - timedelta(days=1)


def _fmt_money(value) -> str:
    try:
        if value is None:
            return ""
        v = float(value)
        # sin decimales, con separador de miles (formato COL)
        return f"${v:,.0f}".replace(",", ".")
    except Exception:
        return str(value or "")


def _parse_fecha_hora(fecha_hora: str) -> datetime | None:
    if not fecha_hora:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(fecha_hora, fmt)
        except Exception:
            pass
    return None


def build_citas_tabla_view(
    page: ft.Page,
    *,
    on_edit_cita=None,
    on_cancel_cita=None,
) -> ft.AlertDialog:
    """
    Devuelve un AlertDialog con la tabla de citas del mes.

    Callbacks opcionales para reutilizar la lógica de agenda_view:
      - on_edit_cita(cita_row_dict)
      - on_cancel_cita(cita_row_dict)

    Si NO pasas callbacks:
      - Edit no hace nada
      - Cancel/Eliminar borra directo (eliminar_cita)
    """

    estado = {
        "month_ref": _month_start(date.today()),
        "filter_text": "",
        "rows_raw": [],
    }

    txt_filtro = ft.TextField(
        label="Filtrar por paciente",
        width=320,
        on_change=lambda e: _refrescar(),
    )
    
    dd_year = ft.Dropdown(
        width=120,
        value=str(estado["month_ref"].year),
        options=[ft.dropdown.Option(str(y)) for y in range(date.today().year - 3, date.today().year + 4)],
        on_change=lambda e: _cambiar_anio(),
        label="Año",
    )

    def _cambiar_anio():
        try:
            y = int(dd_year.value)
        except Exception:
            return
        d = estado["month_ref"]
        estado["month_ref"] = date(y, d.month, 1)
        _refrescar()

    lbl_mes = ft.Text(weight="bold")
    table_host = ft.Column([], expand=True, scroll=ft.ScrollMode.AUTO)
    contador_txt = ft.Text("", weight="bold", size=13)

    def _set_mes_label():
        d = estado["month_ref"]
        # Español “bonito” sin depender de locale del SO
        meses = [
            "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
        ]
        lbl_mes.value = f"{meses[d.month - 1]} {d.year}"

    def _cargar_rows_mes():
        inicio = _month_start(estado["month_ref"])
        fin = _month_end(estado["month_ref"])

        # rango completo del mes (00:00 a 23:59:59)
        fecha_inicio = f"{inicio.isoformat()} 00:00"
        fecha_fin = f"{fin.isoformat()} 23:59:59"

        rows = listar_citas_con_paciente_rango(fecha_inicio, fecha_fin)
        estado["rows_raw"] = [dict(r) for r in rows]
        
        # ✅ Marcar si la cita ya tiene sesión clínica (y cuál sesión)
        try:
            cita_ids = [int(r.get("id")) for r in estado["rows_raw"] if r.get("id") is not None]
            cita_ids = sorted(set(cita_ids))

            sesiones_set = set()
            if cita_ids:
                conn = get_connection()
                cur = conn.cursor()
                qmarks = ",".join(["?"] * len(cita_ids))
                cur.execute(
                    f"SELECT cita_id FROM sesiones_clinicas WHERE cita_id IN ({qmarks});",
                    tuple(cita_ids),
                )
                for rr in cur.fetchall():
                    try:
                        # rr puede ser Row o tuple según tu conexión -> cubrir ambos
                        cid = rr["cita_id"] if hasattr(rr, "keys") else rr[0]
                        sesiones_set.add(int(cid))
                    except Exception:
                        pass
                conn.close()

            for r in estado["rows_raw"]:
                try:
                    r["tiene_sesion"] = int(r.get("id")) in sesiones_set
                except Exception:
                    r["tiene_sesion"] = False

        except Exception:
            for r in estado["rows_raw"]:
                r["tiene_sesion"] = False


    def _aplicar_filtro(rows: list[dict]) -> list[dict]:
        q = (txt_filtro.value or "").strip().lower()
        if not q:
            return rows
        out = []
        for r in rows:
            nombre = str(r.get("nombre_completo") or "").lower()
            doc = str(r.get("documento_paciente") or "").lower()
            if q in nombre or q in doc:
                out.append(r)
        return out

    dlg_holder = {"dlg": None}
    
    def _accion_editar(r: dict):
        if callable(on_edit_cita):
            if dlg_holder["dlg"]:
                page.close(dlg_holder["dlg"])
                page.update()
            on_edit_cita(r)
            return   # <-- esto es clave

        page.snack_bar = ft.SnackBar(ft.Text("Hook: on_edit_cita no está conectado."), open=True)
        page.update()

    def _accion_cancelar(r: dict):
        cita_id = r.get("id")
        if not cita_id:
            return

        paciente = (r.get("nombre_completo") or "").strip()
        fecha_hora = (r.get("fecha_hora") or "").strip()

        def _do(_):
            try:
                # Si agenda_view está conectado, que él haga la cancelación/borrado y refresco
                if callable(on_cancel_cita):
                    on_cancel_cita(r)
                else:
                    eliminar_cita(int(cita_id))

                dlg_confirm.open = False
                page.update()
                _refrescar()
            except Exception as ex:
                dlg_confirm.open = False
                page.snack_bar = ft.SnackBar(ft.Text(f"Error al borrar cita: {ex}"), open=True)
                page.update()

        dlg_confirm = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirmar borrado"),
            content=ft.Text(
                f"¿Seguro que deseas borrar la cita de {paciente or 'este paciente'}?\n{fecha_hora}\n\n"
                "Esta acción no se puede deshacer."
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: _cerrar_confirm(dlg_confirm)),
                ft.ElevatedButton("Borrar", icon=ft.Icons.DELETE, on_click=_do),
            ],
        )
        page.open(dlg_confirm)

    def _cerrar_confirm(d: ft.AlertDialog):
        d.open = False
        page.update()
        
    def _texto_confirmacion(r: dict) -> str:
        paciente = (r.get("nombre_completo") or "").strip() or "Paciente"
        dt = _parse_fecha_hora(r.get("fecha_hora"))
        when = dt.strftime("%Y-%m-%d %H:%M") if dt else (r.get("fecha_hora") or "")
        return f"¿Cancelar esta cita?\n\n{paciente}\n{when}"

    def _cerrar_confirm(d: ft.AlertDialog):
        d.open = False
        page.update()
        
    def _ir_a_historia_y_precargar_sesion(rr: dict):
        # Guardar contexto para historia_view
        page.session.set("historia_paciente_documento", rr.get("documento_paciente"))
        page.session.set("historia_prefill_cita_id", int(rr.get("id")))

        # Cerrar el dialog actual
        d = dlg_holder.get("dlg")
        if d:
            try:
                page.close(d)
            except Exception:
                d.open = False

        page.update()

        # Navegar a Historia
        cb = getattr(page, "mostrar_historia_cb", None)
        if callable(cb):
            cb()
        else:
            page.snack_bar = ft.SnackBar(ft.Text("No está conectado mostrar_historia_cb"), open=True)
            page.update()
            
    def _ir_a_historia_y_abrir_sesion_existente(rr: dict):
        cita_id = rr.get("id")
        if not cita_id:
            return

        # 1) buscar sesion_id de esa cita
        sesion_id = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM sesiones_clinicas WHERE cita_id = ? ORDER BY id DESC LIMIT 1;",
                (int(cita_id),),
            )
            row = cur.fetchone()
            conn.close()
            if row:
                sesion_id = row["id"] if hasattr(row, "keys") else row[0]
        except Exception:
            sesion_id = None

        if not sesion_id:
            # si por algo no se encuentra, mejor no navegar
            page.snack_bar = ft.SnackBar(ft.Text("No se encontró la sesión asociada a esta cita."), open=True)
            page.update()
            return

        # 2) guardar contexto para historia_view
        page.session.set("historia_paciente_documento", rr.get("documento_paciente"))
        page.session.set("historia_open_sesion_id", int(sesion_id))

        # 3) cerrar dialog
        d = dlg_holder.get("dlg")
        if d:
            try:
                page.close(d)
            except Exception:
                d.open = False
        page.update()

        # 4) navegar a historia
        cb = getattr(page, "mostrar_historia_cb", None)
        if callable(cb):
            cb()


    def _build_table(rows: list[dict]) -> ft.Control:
        cols = [
            ft.DataColumn(ft.Text("HC")),
            ft.DataColumn(ft.Text("Fecha")),
            ft.DataColumn(ft.Text("Hora")),
            ft.DataColumn(ft.Text("Paciente")),
            ft.DataColumn(ft.Text("Modalidad")),
            ft.DataColumn(ft.Text("Canal")),
            ft.DataColumn(ft.Text("Valor")),
            ft.DataColumn(ft.Text("Estado")),
            ft.DataColumn(ft.Text("Pagado")),
            ft.DataColumn(ft.Text("Acciones")),
        ]

        data_rows: list[ft.DataRow] = []

        for r in rows:
            dt = _parse_fecha_hora(r.get("fecha_hora"))
            fecha = dt.strftime("%Y-%m-%d") if dt else (r.get("fecha_hora") or "")
            hora = dt.strftime("%H:%M") if dt else ""
            paciente = r.get("nombre_completo") or ""
            modalidad = (r.get("modalidad") or "")
            canal = (r.get("canal") or "")
            valor = _fmt_money(r.get("precio"))
            estado_txt = (r.get("estado") or "")
            #Pagado
            modalidad_l = (r.get("modalidad") or "").lower()
            
            # Ícono de sesión clínica
            tiene = bool(r.get("tiene_sesion"))

            hc_icon = ft.IconButton(
                icon=ft.Icons.CHECK_CIRCLE if tiene else ft.Icons.RADIO_BUTTON_UNCHECKED,
                tooltip="Ver/editar sesión clínica" if tiene else "Sin sesión clínica",
                icon_color=ft.Colors.GREEN_600 if tiene else ft.Colors.GREY_400,
                on_click=(lambda e, rr=r: _ir_a_historia_y_abrir_sesion_existente(rr)) if tiene else None,
                disabled=not tiene,
            )
                
            if modalidad_l == "convenio":
                pagado_cell = ft.Row(
                    [
                        ft.Text("Convenio", color=ft.Colors.GREY_700),
                        ft.Icon(
                            ft.Icons.INFO_OUTLINE,
                            size=14,
                            tooltip="Las citas por convenio se gestionan desde Facturación",
                        ),
                    ],
                    spacing=4,
                )
            else:
                pagado = "Sí" if int(r.get("pagado") or 0) == 1 else "No"
                pagado_cell = ft.Text(pagado)
            #Fin Pagado

            btn_edit = ft.IconButton(
                icon=ft.Icons.EDIT,
                tooltip="Editar",
                on_click=lambda e, rr=r: _accion_editar(rr),
            )
            
            btn_crear_sesion = ft.IconButton(
                icon=ft.Icons.NOTE_ADD_OUTLINED,
                tooltip="Crear sesión clínica para esta cita",
                on_click=lambda e, rr=r: _ir_a_historia_y_precargar_sesion(rr),
            )
            
            # btn_cancel = ft.IconButton(
            #     icon=ft.Icons.DELETE_OUTLINE,
            #     tooltip="Cancelar / borrar",
            #     on_click=lambda e, rr=r: _accion_cancelar(rr),
            # )
            acciones = [btn_edit]

            tiene_sesion = bool(r.get("tiene_sesion"))
            estado_cita = (r.get("estado") or "").strip().lower()

            dt = _parse_fecha_hora(r.get("fecha_hora"))
            ya_ocurrio = bool(dt) and (dt <= datetime.now())

            es_no_asistio = estado_cita in {"no asistió", "no asistio", "no_asistio", "no-asistio"}

            # Mostrar "Crear sesión" SOLO si:
            #  - no tiene sesión aún
            #  - ya ocurrió la cita
            #  - NO es "NO ASISTIÓ"
            if (not tiene_sesion) and ya_ocurrio and (not es_no_asistio):
                acciones.insert(0, btn_crear_sesion)

            data_rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(hc_icon),
                        ft.DataCell(ft.Text(fecha)),
                        ft.DataCell(ft.Text(hora)),
                        ft.DataCell(ft.Text(paciente)),
                        ft.DataCell(ft.Text(modalidad)),
                        ft.DataCell(ft.Text(canal)),
                        ft.DataCell(ft.Text(valor)),
                        ft.DataCell(ft.Text(estado_txt)),
                        ft.DataCell(pagado_cell),
                        ft.DataCell(ft.Row(acciones, spacing=0)),
                    ]
                )
            )

        if not data_rows:
            return ft.Container(
                content=ft.Text("No hay citas para este mes con el filtro actual."),
                padding=20,
            )

        return ft.DataTable(
            columns=cols,
            rows=data_rows,
            heading_row_height=44,
            data_row_min_height=44,
            data_row_max_height=56,
            column_spacing=18,
            horizontal_margin=10,
        )

    def _refrescar():
        _set_mes_label()
        _cargar_rows_mes()
        rows = _aplicar_filtro(estado["rows_raw"])
        total = len(rows)
        presenciales = sum(1 for c in rows if (c.get("canal") or "").lower() == "presencial")
        virtuales = sum(1 for c in rows if (c.get("canal") or "").lower() == "virtual")

        contador_txt.value = f"Total citas: {total} | Presenciales: {presenciales} | Virtuales: {virtuales}"

        table_host.controls.clear()
        table_host.controls.append(_build_table(rows))

        page.update()

    def _mes_prev(e=None):
        d = estado["month_ref"]
        if d.month == 1:
            estado["month_ref"] = date(d.year - 1, 12, 1)
        else:
            estado["month_ref"] = date(d.year, d.month - 1, 1)
        
        dd_year.value = str(estado["month_ref"].year)
        _refrescar()

    def _mes_next(e=None):
        d = estado["month_ref"]
        if d.month == 12:
            estado["month_ref"] = date(d.year + 1, 1, 1)
        else:
            estado["month_ref"] = date(d.year, d.month + 1, 1)
            
        dd_year.value = str(estado["month_ref"].year)
        _refrescar()

    header = ft.Row(
        [
            ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="Mes anterior", on_click=_mes_prev),
            lbl_mes,
            ft.IconButton(ft.Icons.CHEVRON_RIGHT, tooltip="Mes siguiente", on_click=_mes_next),
            dd_year,
            ft.Container(expand=True),
            txt_filtro,
        ],
        alignment=ft.MainAxisAlignment.START,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    
    def _close():
        d = dlg_holder.get("dlg")
        if d is None:
            return
        try:
            page.close(d)
        except Exception:
            d.open = False
            page.update()

    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Row(
            [
                ft.Text("Resumen de Citas", weight="bold"),
                ft.Container(
                    width=32,
                    height=32,
                    border=ft.border.all(1, ft.Colors.RED_300),
                    border_radius=6,
                    alignment=ft.alignment.center,
                    content=ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        icon_color=ft.Colors.RED,
                        tooltip="Cerrar",
                        hover_color=ft.Colors.RED_100,
                        on_click=lambda e: _close(),
                        style=ft.ButtonStyle(
                            padding=0,
                        ),
                    ),
                )
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        content=ft.Container(
            width=1100,
            height=650,
            content=ft.Column(
                [
                    header,
                    contador_txt,
                    ft.Divider(),
                    table_host,
                ],
                spacing=10,
            ),
        ),
        actions=[],  # sin botón "Cerrar" abajo
    )
    dlg_holder["dlg"] = dlg


    # primera carga
    _refrescar()
    return dlg
