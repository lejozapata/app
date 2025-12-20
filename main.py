import flet as ft
from pathlib import Path
from .db import init_db
from .admin_view import build_admin_view
from .agenda_view import build_agenda_view
from .pacientes_view import build_pacientes_view
from .facturas_view import build_facturas_view
from .historia_view import build_historia_view
from .finanzas_view import build_finanzas_view
from .citas_tabla_view import build_citas_tabla_view
from .documentos_view import build_documentos_view
from .ui_config import BRAND_BG, BRAND_PRIMARY, TEXT_MAIN



def main(page: ft.Page):
    page.title = "Gestión de Pacientes - Sara"
    # Tamaño inicial de la ventana
    page.window.width = 1366
    page.window.height = 768
    page.bgcolor = BRAND_BG
    page.theme_mode = ft.ThemeMode.LIGHT
    
    page.theme = ft.Theme(
        color_scheme=ft.ColorScheme(
            primary=BRAND_PRIMARY,
            on_primary="#ffffff",
            surface="#ffffff",
            on_surface=TEXT_MAIN,
            background=BRAND_BG,
            on_background=TEXT_MAIN,
        ),
        use_material3=True,
    )
    
    icon_path = Path(__file__).resolve().parents[1] / "data" / "imagenes" / "icon.ico"
    page.window.icon = str(icon_path)

    # Tamaño mínimo para que no se deforme el layout
    #page.window.min_width = 1100
    #page.window.min_height = 700
    #page.scroll = "always"

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
    page.mostrar_agenda_cb = mostrar_agenda

    def mostrar_admin(e=None):
        body.content = build_admin_view(page)
        body.update()

    def mostrar_facturas(e=None):
        body.content = build_facturas_view(page)
        page.update()
        # Registrar callback en page para que otras vistas (agenda) puedan llamar a Facturas
    page.mostrar_facturas_cb = mostrar_facturas

    def mostrar_finanzas(e=None):
        body.content = build_finanzas_view(page)
        body.update()

    def mostrar_historia(e=None):
        body.content = build_historia_view(page)
        page.update()
    page.mostrar_historia_cb = mostrar_historia
    
    #def mostrar_citas_tabla(e=None):
    #    body.content = build_citas_tabla_view(page)
    #    page.update()
        
    def mostrar_documentos(e=None):
        body.content = build_documentos_view(page)
        page.update()
    page.mostrar_documentos_cb = mostrar_documentos

#


# ----- Top Bar para admin -----
    top_bar = ft.Row(
        [
            ft.Row(
                [
                    ft.ElevatedButton("Pacientes", on_click=mostrar_pacientes),
                    ft.ElevatedButton("Agendar", on_click=mostrar_agenda),
                    ft.ElevatedButton("Facturas", on_click=mostrar_facturas),
                    ft.ElevatedButton("Documentos", on_click=mostrar_documentos),
                    ft.ElevatedButton("Finanzas", on_click=mostrar_finanzas),
                ]
            ),
            ft.Container(expand=True),
            ft.IconButton(
                icon=ft.Icons.SETTINGS,
                tooltip="Configuración",
                on_click=mostrar_admin,
            ),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    # Vista por defecto al abrir la app
    mostrar_pacientes()

 # Muestra la barra superior para admin
    page.add(
        ft.Column(
            [
                top_bar,
                ft.Divider(),
                body,
            ],
            expand=True,
        )
    )


# if __name__ == "__main__":
#     ft.app(
#         target=main,
#         assets_dir="../data",
#         view=ft.AppView.FLET_APP,  # escritorio
#     )
