import flet as ft
from db import init_db
from agenda_view import build_agenda_view
from pacientes_view import build_pacientes_view


def main(page: ft.Page):
    page.title = "Gestión de Pacientes - Sara"
    page.window_width = 1100
    page.window_height = 700
    page.scroll = "always"
    page.locale_configuration = ft.LocaleConfiguration(
        supported_locales=[
            ft.Locale("es", "CO"),   # Español Colombia
        ],
        current_locale=ft.Locale("es", "CO"),
    )

    # Inicializar base de datos
    init_db()

    # Contenedor donde iremos cargando la vista actual (pacientes / agenda)
    body = ft.Container(expand=True)

    # ----- Handlers para cambiar de vista -----

    def mostrar_pacientes(e=None):
        body.content = build_pacientes_view(page)
        page.update()

    def mostrar_agenda(e=None):
        body.content = build_agenda_view(page)
        page.update()

    # ----- Barra superior de navegación -----

    barra_navegacion = ft.Row(
        [
            ft.ElevatedButton("Pacientes", on_click=mostrar_pacientes),
            ft.ElevatedButton("Agendar", on_click=mostrar_agenda),
        ],
        spacing=10,
    )

    # Agregamos barra + body al layout principal
    page.add(
        barra_navegacion,
        ft.Divider(),
        body,
    )

    # Vista por defecto al abrir la app
    mostrar_pacientes()


if __name__ == "__main__":
    ft.app(target=main)
