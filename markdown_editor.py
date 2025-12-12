import flet as ft
from typing import Optional


class MarkdownEditor(ft.Column):
    """
    Editor de texto con soporte Markdown básico + vista previa.

    Diseño pragmático:
    - TextField multiline normal.
    - Botones B / I / 💡 en una fila encima del campo.
    - NO depende de selección (porque Flet 0.28 pierde selección al clicar botones).
    - Cada botón inserta una plantilla de Markdown en el cursor si es posible,
      o al final del texto como fallback.
    """

    def __init__(
        self,
        label: str = "Contenido enriquecido",
        width: int = 800,
        preview_width: int = 350,
        min_lines: int = 4,
        max_lines: int = 12,
        hint_text: Optional[str] = None,
    ):
        super().__init__(spacing=6)

        self.label = label
        self.width = width
        self.preview_width = preview_width
        self.min_lines = min_lines
        self.max_lines = max_lines
        self.hint_text = (
            hint_text
            or "Usa Markdown: **negrita**, _cursiva_, ==resaltado==.\n"
                "Los botones insertan plantillas en la posición del cursor."
        )

        # Campo de texto base
        self.txt = ft.TextField(
            label=self.label,
            multiline=True,
            min_lines=self.min_lines,
            max_lines=self.max_lines,
            width=self.width,
            hint_text=self.hint_text,
        )

        # Vista previa Markdown
        self.preview = ft.Markdown(
            "",
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            selectable=True,
            expand=True,
        )

        self.txt.on_change = self._update_preview

        # Barra de botones arriba del campo
        barra_markdown = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.FORMAT_BOLD,
                    tooltip="Insertar **negrita**",
                    on_click=lambda e: self._insert_snippet("bold"),
                ),
                ft.IconButton(
                    icon=ft.Icons.FORMAT_ITALIC,
                    tooltip="Insertar _cursiva_",
                    on_click=lambda e: self._insert_snippet("italic"),
                ),
                ft.IconButton(
                    icon=ft.Icons.HIGHLIGHT,
                    tooltip="Insertar ==resaltado==",
                    on_click=lambda e: self._insert_snippet("highlight"),
                ),
            ],
            spacing=4,
        )

        # Layout principal: barra + campo + preview
        contenido = ft.Row(
            [
                ft.Column(
                    [
                        barra_markdown,
                        self.txt,
                    ],
                    spacing=4,
                    expand=True,
                ),
                ft.VerticalDivider(width=16),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("Vista previa", weight="bold"),
                            self.preview,
                        ],
                        spacing=4,
                    ),
                    width=self.preview_width,
                    expand=True,
                ),
            ],
            expand=True,
        )

        self.controls = [contenido]

    # ---------------- API pública ----------------

    def get_value(self) -> str:
        return self.txt.value or ""

    def set_value(self, value: str):
        self.txt.value = value or ""
        self.txt.update()
        self._update_preview()

    # ---------------- Inserción de plantillas ----------------

    def _insert_snippet(self, tipo: str):
        """
        Inserta una plantilla de Markdown en la posición del cursor (si Flet lo permite)
        o al final del texto como fallback.
        """
        if tipo == "bold":
            snippet = "**texto**"
            cursor_offset = 2  # para quedar entre los **
        elif tipo == "italic":
            snippet = "_texto_"
            cursor_offset = 1
        elif tipo == "highlight":
            snippet = "==texto=="
            cursor_offset = 2
        else:
            return

        texto = self.txt.value or ""

        # Intentar usar la posición del cursor si está disponible
        pos = None
        try:
            sel = self.txt.selection
            if sel is not None and sel.start is not None:
                pos = sel.start
        except Exception:
            pos = None

        if pos is None or pos < 0 or pos > len(texto):
            pos = len(texto)

        nuevo_texto = texto[:pos] + snippet + texto[pos:]

        self.txt.value = nuevo_texto
        self.txt.update()
        self._update_preview()

        # Intentar colocar el cursor dentro de la plantilla
        try:
            nuevo_cursor = pos + cursor_offset
            self.txt.selection = ft.TextSelection(nuevo_cursor, nuevo_cursor)
            self.txt.update()
        except Exception:
            pass

    # ---------------- Vista previa ----------------

    def _update_preview(self, e=None):
        self.preview.value = self.txt.value or ""
        self.preview.update()
