import flet as ft
from db import init_db
from pacientes_view import build_pacientes_view


def main(page: ft.Page):
    page.title = "Gestión de Pacientes - Sara"
    page.window_width = 1100
    page.window_height = 700
    page.scroll = "always"

    # Inicializar base de datos
    init_db()

    # Construir y agregar la vista de pacientes
    pacientes_view = build_pacientes_view(page)
    page.add(pacientes_view)


if __name__ == "__main__":
    ft.app(target=main)
