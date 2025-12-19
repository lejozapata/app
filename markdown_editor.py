import flet as ft
from typing import Optional
import re

try:
    from spellchecker import SpellChecker
except Exception:
    SpellChecker = None


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
    page: Optional[ft.Page] = None,   # 👈 NUEVO

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
        
        self._page_ref = page
        self.spell = SpellChecker(language="es") if SpellChecker else None

        # Opcional: palabras que no quieres que marque
        if self.spell:
            self.spell.word_frequency.load_words(["SURA", "EPS", "CIE10", "DSM"])

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
                ft.IconButton(
                    icon=ft.Icons.SPELLCHECK,
                    tooltip="Revisar ortografía",
                    on_click=self._revisar_ortografia,
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
        if self.txt.page is not None:
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
        
        
    def _get_page(self) -> Optional[ft.Page]:
        if getattr(self, "_page_ref", None) is not None:
            return self._page_ref
        try:
            return self.page
        except Exception:
            return None

    def _revisar_ortografia(self, e=None):
        page = self._get_page()
        if page is None:
            return
        
        # Debug opcional (ya sin error)
        page.snack_bar = ft.SnackBar(content=ft.Text("Click ortografía OK"))
        page.snack_bar.open = True
        page.update()

        if not self.spell:
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Revisión ortográfica no disponible. Instala: pip install pyspellchecker")
            )
            page.snack_bar.open = True
            page.update()
            return

        texto = (self.txt.value or "").strip()
        if not texto:
            page.snack_bar = ft.SnackBar(content=ft.Text("No hay texto para revisar."))
            page.snack_bar.open = True
            page.update()
            return

        palabras = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", texto)
        desconocidas = sorted(set(self.spell.unknown([p.lower() for p in palabras])))

        if not desconocidas:
            page.snack_bar = ft.SnackBar(content=ft.Text("No encontré errores ortográficos."))
            page.snack_bar.open = True
            page.update()
            return

        sugerencias = []
        for w in desconocidas[:80]:  # tope para no saturar UI
            corr = self.spell.correction(w)
            if corr and corr != w:
                sugerencias.append((w, corr))

        if not sugerencias:
            page.snack_bar = ft.SnackBar(content=ft.Text("Encontré palabras dudosas, pero sin sugerencias claras."))
            page.snack_bar.open = True
            page.update()
            return

        lista = ft.Column(
            controls=[ft.Row([ft.Text(f"{w}  →  {c}")]) for w, c in sugerencias],
            scroll=ft.ScrollMode.AUTO,
            height=300,
            width=520,
        )

        def aplicar(ev):
            nuevo = texto
            for w, c in sugerencias:
                nuevo = re.sub(rf"\b{re.escape(w)}\b", c, nuevo, flags=re.IGNORECASE)

            self.set_value(nuevo)  # reutiliza tu API pública (actualiza preview)

            page.dialog.open = False
            page.update()

            page.snack_bar = ft.SnackBar(content=ft.Text("Correcciones aplicadas."))
            page.snack_bar.open = True
            page.update()
        
        def _cerrar_dialogo(ev):
            page.dialog.open = False
            page.update()

        dlg = ft.AlertDialog(
            title=ft.Text("Revisión ortográfica"),
            content=lista,
            actions=[
                ft.TextButton("Cerrar", on_click=_cerrar_dialogo),
                ft.ElevatedButton("Aplicar correcciones", icon=ft.Icons.CHECK, on_click=aplicar),
            ],
        )
        page.dialog = dlg
        page.dialog.open = True
        page.update()

    # ---------------- Vista previa ----------------

    def _update_preview(self, e=None):
        self.preview.value = self.txt.value or ""
        self.preview.update()
