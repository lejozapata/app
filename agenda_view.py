import flet as ft
from datetime import datetime, timedelta
from db import listar_citas_rango   # lo usaremos después

# ---------------------------
# Vista de Agenda / Calendario
# ---------------------------

def build_agenda_view(page: ft.Page):

    # Estado interno --------------------------
    # Semana base: lunes de la semana actual
    hoy = datetime.now()
    semana_lunes = hoy - timedelta(days=hoy.weekday())  # lunes de esta semana

    # Usamos ref para poder modificar dentro de handlers
    semana_lunes_ref = ft.Ref[datetime]()
    semana_lunes_ref.current = semana_lunes

    # Contenedor donde dibujaremos el calendario
    calendario_contenedor = ft.Column(expand=True)

    # -----------------------------------------
    # Función para generar los días de la semana
    # -----------------------------------------
    def obtener_dias_semana(lunes: datetime):
        return [lunes + timedelta(days=i) for i in range(7)]

    # ------------------------------------------------
    # Renderizado semanal del calendario (sin citas)
    # ------------------------------------------------
    def dibujar_calendario():
        dias = obtener_dias_semana(semana_lunes_ref.current)

        # HORAS: 8am a 20pm por ahora
        horas = list(range(8, 21))

        filas = []

        # Encabezado con días de la semana
        encabezado = ft.Row(
            [
                ft.Container(width=70),  # espacio donde van las horas
                *[
                    ft.Container(
                        content=ft.Text(d.strftime("%A %d/%m"), weight="bold"),
                        alignment=ft.alignment.center,
                        width=130,
                        padding=5,
                    )
                    for d in dias
                ]
            ]
        )

        filas.append(encabezado)

        # Cuerpo horario
        for h in horas:
            fila = ft.Row(
                [
                    # Columna de la hora
                    ft.Container(
                        width=70,
                        content=ft.Text(f"{h:02d}:00"),
                        alignment=ft.alignment.center_right,
                        padding=5,
                    ),
                    # 7 columnas, una por día
                    *[
                        ft.Container(
                            width=130,
                            height=50,
                            bgcolor=ft.Colors.GREY_200,
                            border=ft.border.all(0.5, ft.Colors.GREY_400),
                            alignment=ft.alignment.center,
                            on_click=lambda e, dia=d, hora=h: click_slot(dia, hora),
                        )
                        for d in dias
                    ]
                ]
            )
            filas.append(fila)

        calendario_contenedor.controls = filas
        page.update()

    # -------------------------------------------
    # Handler de clic en un bloque vacío
    # -------------------------------------------
    def click_slot(dia: datetime, hora: int):
        # Por ahora solo mostramos qué se clickeó
        page.snack_bar = ft.SnackBar(
            content=ft.Text(f"Click en {dia.strftime('%Y-%m-%d')} {hora:02d}:00"),
            bgcolor=ft.Colors.BLUE_200,
        )
        page.snack_bar.open = True
        page.update()

    # -------------------------------------------
    # Botones de navegación (semana +/-)
    # -------------------------------------------
    def semana_anterior(e):
        semana_lunes_ref.current -= timedelta(days=7)
        dibujar_calendario()

    def semana_siguiente(e):
        semana_lunes_ref.current += timedelta(days=7)
        dibujar_calendario()

    def semana_hoy(e):
        hoy = datetime.now()
        semana_lunes_ref.current = hoy - timedelta(days=hoy.weekday())
        dibujar_calendario()

    # -------------------------------------------
    # Layout superior
    # -------------------------------------------
    barra_controles = ft.Row(
        [
            ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, on_click=semana_anterior),
            ft.Text("Semana de " + semana_lunes_ref.current.strftime("%d/%m/%Y")),
            ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, on_click=semana_siguiente),
            ft.ElevatedButton("Hoy", on_click=semana_hoy),
        ],
        alignment=ft.MainAxisAlignment.START,
    )

    # Dibujamos la semana inicial
    dibujar_calendario()

    # Vista final
    return ft.Column(
        [
            barra_controles,
            ft.Divider(),
            calendario_contenedor,
        ],
        expand=True,
    )
