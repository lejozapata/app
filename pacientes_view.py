import re
import json
import threading
import time
import asyncio
from pathlib import Path
from datetime import datetime, date
import flet as ft
from .pacientes_excel import (
    crear_plantilla_pacientes,
    exportar_pacientes_a_excel,
    importar_pacientes_desde_excel,
    validar_archivo_pacientes_excel,
    PlantillaExcelInvalidaError,
)
from .google_forms import debug_dump_latest_response, sync_responses_manual
from .utils import (
    normalize_doc,
    normalize_phone_co,
    form_date_to_ddmmyyyy,
    consent_ok,
    map_tipo_documento,
    normalize_phone_for_db_colombia,
)
from .db import (
    crear_paciente,
    listar_pacientes,
    obtener_paciente,
    actualizar_paciente,
    eliminar_paciente,
    crear_antecedente_medico,
    crear_antecedente_psicologico,
    listar_antecedentes_medicos,
    listar_antecedentes_psicologicos,
    actualizar_antecedente_medico,
    actualizar_antecedente_psicologico,
    eliminar_antecedente_medico,
    eliminar_antecedente_psicologico,
    obtener_configuracion_gmail
)

def get_google_forms_id() -> str:
    """
    Devuelve el Google Forms ID configurado.
    Si no existe o está vacío, retorna string vacío.
    """
    try:
        cfg = obtener_configuracion_gmail()
        form_id = (cfg.get("google_forms_id") or "").strip()
        return form_id
    except Exception:
        return ""


def construir_paciente_desde_form(ans: dict) -> dict:
    def g(k: str) -> str:
        return (ans.get(k) or "").strip()
    ind_tel, tel_local = normalize_phone_for_db_colombia(g("teléfono de contacto"))
    ind_em, em_local = normalize_phone_for_db_colombia(g("teléfono contacto de emergencia"))

    return {
        "tipo_documento": map_tipo_documento(g("tipo de documento de identidad")),
        "documento": normalize_doc(g("nro. documento de identidad")),
        "nombre_completo": g("nombre completo"),
        "fecha_nacimiento": form_date_to_ddmmyyyy(g("fecha de nacimiento")),
        "sexo": g("sexo"),
        "estado_civil": g("estado civil"),
        "escolaridad": g("escolaridad"),
        "eps": g("eps"),
        "direccion": g("dirección"),
        "email": g("correo electrónico"),
        "indicativo_pais": ind_tel,
        "telefono": tel_local,
        "contacto_emergencia_nombre": g("nombre contacto de emergencia"),
        "contacto_emergencia_telefono": em_local,

        # si existe en tu tabla:
        "observaciones": g("observaciones"),
    }
    
def hay_cambios(paciente_db, paciente_nuevo) -> bool:
    campos = [
        "tipo_documento",
        "documento",
        "nombre_completo",
        "fecha_nacimiento",
        "sexo",
        "estado_civil",
        "escolaridad",
        "eps",
        "direccion",
        "email",
        "telefono",
        "contacto_emergencia_nombre",
        "contacto_emergencia_telefono",
    ]

    for campo in campos:
        valor_db = (paciente_db[campo] or "").strip() if campo in paciente_db.keys() else ""
        valor_nuevo = (paciente_nuevo.get(campo) or "").strip()

        if valor_db != valor_nuevo:
            return True  # hubo cambio real

    return False
    



def build_pacientes_view(page: ft.Page) -> ft.Control:
    """
    Vista principal de gestión de pacientes:
    - Formulario de registro/edición
    - Listado de pacientes
    - Historial de antecedentes por paciente
    """

    # ------------------------------------------------------------------
    # ESTADO GENERAL
    # ------------------------------------------------------------------

    # Cache en memoria para filtrar sin ir siempre a la BD
    pacientes_cache = []

    # Estado de edición de paciente
    modo_edicion = False
    documento_seleccionado = None

    # True cuando hay cambios sin guardar en el formulario
    form_dirty = False
    def marcar_formulario_sucio(e=None):
        """Marca que el formulario tiene cambios sin guardar."""
        nonlocal form_dirty
        form_dirty = True
        
        
    # ------------------------------------------------------------------   
    # ERRORES DEL IMPORT EXCEL
    # ------------------------------------------------------------------
    
    def _show_dialog(titulo: str, lineas: list[str]):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(titulo),
            content=ft.Container(
                content=ft.ListView(
                    controls=[ft.Text(x, selectable=True) for x in lineas],
                    expand=True,
                    spacing=6,
                ),
                width=700,
                height=400,
            ),
            actions=[ft.TextButton("Cerrar")],
        )

        def _close(e=None):
            dlg.open = False
            page.update()

        dlg.actions[0].on_click = _close

        page.open(dlg)   # <-- CLAVE


    # ------------------------------------------------------------------
    
    # ----------------- Países / Indicativos -----------------
    # Carga desde data/countries.json (ya lo tienes en el proyecto).
    # Guardamos en BD solo el phoneCode en dígitos (ej: "57", "61").
    def _flag_emoji(iso2: str) -> str:
        iso2 = (iso2 or "").strip().upper()
        if len(iso2) != 2 or not iso2.isalpha():
            return ""
        return chr(0x1F1E6 + (ord(iso2[0]) - ord("A"))) + chr(0x1F1E6 + (ord(iso2[1]) - ord("A")))

    def _solo_digitos(s: str) -> str:
        return "".join(c for c in (s or "") if c.isdigit())

    def _cargar_paises():
        # Intentamos resolver ../data/countries.json desde este archivo
        base_dir = Path(__file__).resolve().parents[1]
        candidates = [
            base_dir / "data" / "countries.json",
            Path(__file__).resolve().parent / "data" / "countries.json",
        ]
        for fp in candidates:
            if fp.exists():
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data
        return []

    _paises_raw = _cargar_paises()
    _paises = []
    _iso2_to_code = {}
    _code_to_iso2 = {}

    for it in _paises_raw or []:
        iso2 = (it.get("iso2") or "").upper()
        name = (it.get("nameES") or it.get("nameEN") or "").strip()
        code = _solo_digitos(it.get("phoneCode") or "")
        if not iso2 or not name or not code:
            continue
        _iso2_to_code[iso2] = code
        # Si hay varios países con mismo indicativo, nos quedamos con el primero.
        _code_to_iso2.setdefault(code, iso2)
        _paises.append(
            {
                "iso2": iso2,
                "name": name,
                "code": code,
                "label": f"{_flag_emoji(iso2)} {name} (+{code})".strip(),
            }
        )

    # Colombia primero y default
    _paises.sort(key=lambda x: (0 if x["iso2"] == "CO" else 1, x["name"].lower()))
    if "57" in _code_to_iso2:
        _code_to_iso2["57"] = "CO"


        # ----------------- Helpers teléfono (SIN límite de dígitos) -----------------

    def _formatear_espacios(digits: str) -> str:
        """Formatea una cadena de dígitos con el patrón 3-3-4 repetible por bloques de 10.

        Ej:
          - 3206798393 -> 320 679 8393
          - 12312312341231231234 -> 123 123 1234 123 123 1234

        No recorta: si hay más dígitos, sigue repitiendo el patrón.
        """
        if not digits:
            return ""

        partes = []
        i = 0
        n = len(digits)

        while i < n:
            bloque = digits[i:i+10]
            if len(bloque) <= 3:
                partes.append(bloque)
            elif len(bloque) <= 6:
                partes.append(f"{bloque[:3]} {bloque[3:]}")
            else:
                partes.append(f"{bloque[:3]} {bloque[3:6]} {bloque[6:]}")
            i += 10

        return " ".join(partes)

    # Guards para evitar re-entradas en on_change (update() puede disparar otro evento)
    _tel_format_guard = {"active": False}
    _tel_emerg_format_guard = {"active": False}

    def _on_change_telefono(e):
        # Formatea en tiempo real (solo visual). En BD se guarda sin espacios.
        if _tel_format_guard["active"]:
            return
        _tel_format_guard["active"] = True
        try:
            raw = e.control.value or ""
            digits = _solo_digitos_telefono(raw)

            # Permitir vacío
            if not digits:
                if raw != "":
                    e.control.value = ""
                    e.control.update()
                marcar_formulario_sucio()
                return

            formatted = _formatear_telefono_con_espacios(digits)
            if raw != formatted:
                e.control.value = formatted
                e.control.update()

            marcar_formulario_sucio()
        finally:
            _tel_format_guard["active"] = False

    def _on_change_tel_emergencia(e):
        if _tel_emerg_format_guard["active"]:
            return
        _tel_emerg_format_guard["active"] = True
        try:
            raw = e.control.value or ""
            digits = _solo_digitos_telefono(raw)

            if not digits:
                if raw != "":
                    e.control.value = ""
                    e.control.update()
                marcar_formulario_sucio()
                return

            formatted = _formatear_telefono_con_espacios(digits)
            if raw != formatted:
                e.control.value = formatted
                e.control.update()

            marcar_formulario_sucio()
        finally:
            _tel_emerg_format_guard["active"] = False

    def _on_blur_telefono(e):
        # En blur re-aplicamos por si hubo edición en medio del texto
        raw = e.control.value or ""
        digits = _solo_digitos_telefono(raw)
        if not digits:
            e.control.value = ""
            e.control.update()
            return
        formatted = _formatear_telefono_con_espacios(digits)
        if raw != formatted:
            e.control.value = formatted
            e.control.update()

    def _on_blur_tel_emergencia(e):
        raw = e.control.value or ""
        digits = _solo_digitos_telefono(raw)
        if not digits:
            e.control.value = ""
            e.control.update()
            return
        formatted = _formatear_telefono_con_espacios(digits)
        if raw != formatted:
            e.control.value = formatted
            e.control.update()
    
    # Funcion para hacer Sync desde Google Forms
    def sincronizar_desde_google_forms() -> str:
        """
        Sincroniza TODAS las respuestas NUEVAS del formulario (según responseId).
        Usa google_forms_state.json para no repetir las ya procesadas.
        """
        form_id = get_google_forms_id()
        if not form_id:
            return "Google Forms no configurado. Ve a Configuración."

        def _first_nonempty(ans: dict, *keys: str) -> str:
            for k in keys:
                v = (ans.get(k) or "").strip()
                if v:
                    return v
            return ""

        def process_row_fn(ans: dict, raw: dict):
            if not ans:
                return "skipped", "Respuesta vacía"

            # ✅ Consentimiento: el key real viene de _norm(title)
            # "Tratamiento de datos personales" -> "tratamiento de datos personales"
            consent = _first_nonempty(
                ans,
                "tratamiento de datos personales",      # ✅ el correcto con tu _norm actual
                "tratamiento_de_datos_personales",      # compat
                "consentimiento_tratamiento",           # compat viejo
                "consentimiento datos personales",      # compat viejo
            ).lower()

            # En Forms normalmente esto llega como "Acepto"
            if "acepto" not in consent:
                return "skipped", "Formulario incompleto (sin aceptación de tratamiento de datos)"

            paciente = construir_paciente_desde_form(ans)
            doc = (paciente.get("documento") or "").strip()
            nombre = (paciente.get("nombre_completo") or "").strip()

            if not doc:
                return "skipped", f"Registro sin documento: {nombre or 'sin nombre'}"

            existente = obtener_paciente(doc)

            if existente:
                if not hay_cambios(existente, paciente):
                    return "skipped", f"Sin cambios: {nombre or doc}"
                actualizar_paciente(paciente)
                return "updated", f"Actualizado: {nombre or doc}"

            crear_paciente(paciente)
            return "inserted", f"Creado: {nombre or doc}"

        inserted, updated, skipped, messages = sync_responses_manual(form_id, process_row_fn)

        total = inserted + updated + skipped
        if total == 0:
            return "No hay respuestas nuevas"

        resumen = f"Forms ✅ Nuevos:{inserted} · Actualizados:{updated} · Omitidos:{skipped}"
        if not messages:
            return resumen

        top = messages[:3]
        extra = len(messages) - len(top)
        detalle = " | ".join(top) + (f" (+{extra} más)" if extra > 0 else "")
        return f"{resumen}\n{detalle}"

    # CONTROLES DEL FORMULARIO DE PACIENTE
    # ------------------------------------------------------------------
    # Funcion para controlar sync
    # Banner / estado visible (siempre con espacio)
    lbl_sync_forms = ft.Text(
        "",
        size=16,
        weight=ft.FontWeight.W_600,
        color=ft.Colors.WHITE,
    )

    sync_banner = ft.Container(
        content=lbl_sync_forms,
        padding=12,
        border_radius=8,
        bgcolor=ft.Colors.BLUE_GREY_700,
        visible=False,
    )
    
    btn_sync_forms = ft.IconButton(
        icon=ft.Icons.SYNC,
        tooltip="Sincronizar desde Google Forms",
    )

    def mostrar_mensaje_forms(texto: str, tipo: str = "info", duracion: int = 7):
        # Colores por tipo
        colores = {
            "info": ft.Colors.BLUE_600,
            "ok": ft.Colors.GREEN_600,
            "error": ft.Colors.RED_600,
            "warn": ft.Colors.ORANGE_600,
        }

        lbl_sync_forms.value = texto
        lbl_sync_forms.color = ft.Colors.WHITE
        sync_banner.bgcolor = colores.get(tipo, ft.Colors.BLUE_GREY_700)
        sync_banner.visible = True
        page.update()

        async def _limpiar():
            await asyncio.sleep(duracion)
            if sync_banner.page:
                sync_banner.visible = False
                page.update()

        page.run_task(_limpiar)
    

    def on_sync_click(e=None):
        btn_sync_forms.disabled = True
        page.update()
        mostrar_mensaje_forms("Sincronizando desde Google Forms...", tipo="info", duracion=6)

        def tarea_sync():
            try:
                msg = sincronizar_desde_google_forms()

                async def _ui_ok():
                    try:
                        cargar_pacientes()
                    except Exception:
                        pass

                    # tipo según resultado (más robusto)
                    tipo = "ok"
                    msg_low = (msg or "").lower()

                    if "no hay respuestas nuevas" in msg_low:
                        tipo = "warn"
                    elif "nuevos:0" in msg_low and "actualizados:0" in msg_low:
                        tipo = "warn"
                    elif "sin consentimiento" in msg_low:
                        tipo = "warn"
                    elif msg_low.startswith("google forms no configurado"):
                        tipo = "warn"

                    mostrar_mensaje_forms(msg, tipo=tipo, duracion=8)
                    btn_sync_forms.disabled = False
                    page.update()

                page.run_task(_ui_ok)

            except Exception as ex:
                err_msg = str(ex)  # ✅ capturar aquí (evita NameError en closures)

                # Mensajes amigables
                low = err_msg.lower()
                if "httperror 404" in low or "requested entity was not found" in low:
                    err_msg = "El Google Forms ID no existe o no tienes acceso. Verifícalo en Configuración."
                elif "invalid_grant" in low:
                    err_msg = "Sesión de Google expirada. Vuelve a iniciar sesión / autorizar la cuenta."
                elif "insufficient authentication scopes" in low:
                    err_msg = "Faltan permisos OAuth (scopes) para Google Forms. Reautoriza la cuenta."

                async def _ui_err():
                    mostrar_mensaje_forms(f"⚠️ Error: {err_msg}", tipo="error", duracion=10)
                    btn_sync_forms.disabled = False
                    page.update()

                page.run_task(_ui_err)

        page.run_thread(tarea_sync)

    btn_sync_forms.on_click = on_sync_click

    documento = ft.TextField(label="Documento", width=200)

    tipo_documento = ft.Dropdown(
        label="Tipo documento",
        width=150,
        options=[
            ft.DropdownOption(
                text="Seleccione tipo...",
                key="tipo_default",
                disabled=True,
            ),
            ft.dropdown.Option("CC"),
            ft.dropdown.Option("TI"),
            ft.dropdown.Option("CE"),
            ft.dropdown.Option("PASAPORTE"),
            ft.dropdown.Option("OTRO"),
        ],
    )

    nombre_completo = ft.TextField(label="Nombre completo", width=400)

    fecha_nacimiento = ft.TextField(
        label="Fecha nacimiento",
        width=200,
        hint_text="(DD-MM-YYYY)",
        
    )


     # Campo de edad solo lectura No se guarda en BD
    edad = ft.TextField(
        label="Edad",
        width=80,
        read_only=True,
        filled=True,
        bgcolor=ft.Colors.GREY_300,
        text_style=ft.TextStyle(color=ft.Colors.BLACK87),
        value="-",
    )

     # DatePicker para fecha de nacimiento
    datepicker_nacimiento = ft.DatePicker(
        help_text="Selecciona la fecha de nacimiento",
        first_date=datetime(1900, 1, 1),
        last_date=datetime.now(),
        date_picker_entry_mode=ft.DatePickerEntryMode.CALENDAR_ONLY
    )

    # Lo agregamos a overlays de la página para poder abrirlo
    page.overlay.append(datepicker_nacimiento)

    sexo = ft.Dropdown(
        label="Sexo",
        width=150,
        options=[
            ft.DropdownOption(
                text="Seleccione sexo...",
                key="sexo_default",
                disabled=True,
            ),
            ft.dropdown.Option("Femenino"),
            ft.dropdown.Option("Masculino"),
            ft.dropdown.Option("Otro"),
            ft.dropdown.Option("Prefiero no decir"),
        ],
    )

    estado_civil = ft.Dropdown(
        label="Estado civil",
        width=200,
        options=[
            ft.DropdownOption(
                text="Seleccione estado...",
                key="estado_default",
                disabled=True,
            ),
            ft.dropdown.Option("Soltera/o"),
            ft.dropdown.Option("Casada/o"),
            ft.dropdown.Option("Unión libre"),
            ft.dropdown.Option("Separada/o"),
            ft.dropdown.Option("Divorciada/o"),
            ft.dropdown.Option("Viuda/o"),
        ],
    )

    escolaridad = ft.TextField(label="Escolaridad", width=250)

    eps = ft.TextField(label="EPS", width=250)
    # Contenedor para mostrar sugerencias de EPS (autocomplete simple)
    eps_sugerencias = ft.Column(spacing=2, visible=False)

    direccion = ft.TextField(label="Dirección", width=400)
    email = ft.TextField(label="Email", width=300)

    # Selector de país para indicativo (usa countries.json)
    # Nota: no usamos emoji en Dropdown porque algunos entornos no lo renderizan.
    # En su lugar mostramos la bandera como imagen (flagcdn) en un selector propio.
    indicativo_pais = ft.TextField(value="CO", visible=False)

    _paises_por_iso2 = {p["iso2"]: p for p in _paises}

    def _flag_url(iso2: str) -> str:
        iso2 = (iso2 or "").strip().lower()
        if len(iso2) != 2:
            return ""
        # 40px ancho; puedes subir a w80 si lo quieres más grande
        return f"https://flagcdn.com/w40/{iso2}.png"

    img_flag_pais = ft.Image(src=_flag_url("CO"), width=18, height=14)
    txt_pais_sel = ft.Text(_paises_por_iso2.get("CO", {}).get("label", "Colombia (+57)"), no_wrap=True)

    def _actualizar_ui_pais():
        iso2 = (indicativo_pais.value or "CO").upper()
        pinfo = _paises_por_iso2.get(iso2) or _paises_por_iso2.get("CO") or {}
        img_flag_pais.src = _flag_url(pinfo.get("iso2") or "CO")
        txt_pais_sel.value = pinfo.get("label") or "Colombia (+57)"
        if img_flag_pais.page is not None:
            img_flag_pais.update()
        if txt_pais_sel.page is not None:
            txt_pais_sel.update()

    # Diálogo de selección de país
    pais_buscar = ft.TextField(label="Buscar país", width=420)
    pais_lista = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO, height=420)

    def _aplicar_filtro_pais(q: str):
        q = (q or "").strip().lower()
        pais_lista.controls.clear()
        for pinfo in _paises:
            label = pinfo.get("label", "")
            if q and q not in label.lower():
                continue
            iso2 = pinfo.get("iso2", "CO")
            # En _paises normalizamos a: {"iso2","name","code","label"}
            # Mostramos todo en el title y evitamos un subtitle extra (el "+" suelto).
            pais_lista.controls.append(
                ft.ListTile(
                    leading=ft.Image(src=_flag_url(iso2), width=18, height=14),
                    title=ft.Text(pinfo.get("label") or label),

                    on_click=lambda e, iso2_sel=iso2: _seleccionar_pais(iso2_sel),
                )
            )
        if pais_lista.page is not None:
            pais_lista.update()

    def _seleccionar_pais(iso2_sel: str):
        indicativo_pais.value = (iso2_sel or "CO").upper()
        _actualizar_ui_pais()
        dlg_paises.open = False
        page.update()

    def _abrir_dialogo_paises(e=None):
        # Colombia primero ya viene así en _paises; solo pintamos lista
        pais_buscar.value = ""
        _aplicar_filtro_pais("")
        page.open(dlg_paises)

    pais_buscar.on_change = lambda e: _aplicar_filtro_pais(pais_buscar.value)

    dlg_paises = ft.AlertDialog(
        modal=True,
        title=ft.Text("Seleccionar país"),
        content=ft.Column([pais_buscar, pais_lista], tight=True),
        actions=[ft.TextButton("Cerrar", on_click=lambda e: (_set_dialog(False)))],
    )

    def _set_dialog(open_state: bool):
        dlg_paises.open = open_state
        page.update()

    # Botón visible para selección de país
    btn_pais = ft.OutlinedButton(
        content=ft.Row([img_flag_pais, txt_pais_sel], spacing=8, tight=True),
        on_click=_abrir_dialogo_paises,
    )

    telefono = ft.TextField(
        label="Teléfono de contacto",
        width=200,
        keyboard_type=ft.KeyboardType.PHONE,
        input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9\s]*"),
        on_change=_on_change_telefono,
        on_blur=_on_blur_telefono,
    )

    contacto_emergencia_nombre = ft.TextField(
        label="Nombre contacto de emergencia",
        width=300,
    )
    contacto_emergencia_telefono = ft.TextField(
        label="Teléfono contacto de emergencia",
        width=200,
        keyboard_type=ft.KeyboardType.PHONE,
        input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9\s]*"),
        on_change=_on_change_tel_emergencia,
        on_blur=_on_blur_tel_emergencia,
    )

    observaciones = ft.TextField(
        label="Observaciones",
        multiline=True,
        min_lines=2,
        max_lines=4,
        width=600,
    )

    # Campos para registrar antecedentes al crear/editar paciente
    antecedente_medico_form = ft.TextField(
        label="Antecedente médico",
        multiline=True,
        min_lines=2,
        max_lines=3,
        width=600,
    )

    antecedente_psico_form = ft.TextField(
        label="Antecedente psicológico",
        multiline=True,
        min_lines=2,
        max_lines=3,
        width=600,
    )

    # mensaje_estado: para mostrar errores / confirmaciones de guardado
    mensaje_estado = ft.Text(value="", color="red")
    # texto_contexto: para mostrar "Editando paciente: ..."
    texto_contexto = ft.Text(value="", color="blue", size=12)

    # ------------------------------------------------------------------
    # CONTROLES PARA HISTORIAL DE ANTECEDENTES (LADO DERECHO)
    # ------------------------------------------------------------------

    etiqueta_paciente_antecedentes = ft.Text(
        value="Selecciona un paciente para ver sus antecedentes.",
        size=16,
        weight="bold",
    )

    antecedentes_medicos_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Fecha registro")),
            ft.DataColumn(ft.Text("Descripción")),
            ft.DataColumn(ft.Text("Acciones")),
        ],
        rows=[],
    )

    antecedentes_psico_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Fecha registro")),
            ft.DataColumn(ft.Text("Descripción")),
            ft.DataColumn(ft.Text("Acciones")),
        ],
        rows=[],
    )


    # ------------------------------------------------------------------
    # TABLA DE PACIENTES
    # ------------------------------------------------------------------

    tabla_pacientes = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Documento")),
            ft.DataColumn(ft.Text("Tipo")),
            ft.DataColumn(ft.Text("Nombre")),
            ft.DataColumn(ft.Text("Fecha nac.")),
            ft.DataColumn(ft.Text("Edad")),
            ft.DataColumn(ft.Text("Sexo")),
            ft.DataColumn(ft.Text("Teléfono")),
            ft.DataColumn(ft.Text("Acciones")),
        ],
        rows=[],
    )

    buscador = ft.TextField(
        label="Buscar por documento o nombre",
        width=400,
    )

    # ------------------------------------------------------------------
    # FUNCIONES AUXILIARES GENERALES
    # ------------------------------------------------------------------

    def mostrar_snackbar(texto: str):
        """Muestra un mensaje emergente en la parte inferior."""
        page.snack_bar = ft.SnackBar(content=ft.Text(texto))
        page.snack_bar.open = True
        page.update()

    def email_valido(correo: str) -> bool:
        """Valida la estructura básica de un email."""
        if not correo:
            return True
        return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", correo) is not None

    def reset_dropdowns_a_default():
        """Pone los dropdowns en su opción inicial ('Seleccione ...')."""
        tipo_documento.value = "tipo_default"
        sexo.value = "sexo_default"
        estado_civil.value = "estado_default"

    def abrir_dialogo_editar_antecedente(tipo: str, antecedente: dict):
        """
        Abre un diálogo para editar la descripción de un antecedente.
        tipo: "medico" o "psico"
        antecedente: dict con al menos {"id", "descripcion"}
        """
        campo_descripcion = ft.TextField(
            value=antecedente["descripcion"],
            multiline=True,
            min_lines=3,
            max_lines=6,
            width=400,
        )

        def cerrar_dialogo(e=None):
            dialog.open = False
            page.update()

        def guardar_cambios(e):
            texto_nuevo = (campo_descripcion.value or "").strip()
            if not texto_nuevo:
                # No permitir dejarlo vacío
                return

            if tipo == "medico":
                actualizar_antecedente_medico(antecedente["id"], texto_nuevo)
            else:
                actualizar_antecedente_psicologico(antecedente["id"], texto_nuevo)

            cerrar_dialogo()
            # Volver a cargar antecedentes del paciente actualmente seleccionado
            if documento_seleccionado:
                cargar_antecedentes(documento_seleccionado)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Editar antecedente médico"
                if tipo == "medico"
                else "Editar antecedente psicológico"
            ),
            content=campo_descripcion,
            actions=[
                ft.TextButton("Cancelar", on_click=cerrar_dialogo),
                ft.TextButton("Guardar", on_click=guardar_cambios),
            ],
        )

        page.open(dialog)

    def confirmar_eliminar_antecedente(tipo: str, antecedente_id: int):
        """
        Muestra confirmación antes de eliminar un antecedente.
        tipo: "medico" o "psico"
        """

        def cancelar(e=None):
            dialog.open = False
            page.update()

        def confirmar(e):
            if tipo == "medico":
                eliminar_antecedente_medico(antecedente_id)
            else:
                eliminar_antecedente_psicologico(antecedente_id)

            dialog.open = False
            page.update()

            if documento_seleccionado:
                cargar_antecedentes(documento_seleccionado)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Eliminar antecedente"),
            content=ft.Text(
                "¿Seguro que deseas eliminar este antecedente?\n"
                "Esta acción no se puede deshacer."
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=cancelar),
                ft.TextButton("Eliminar", on_click=confirmar),
            ],
        )

        page.open(dialog)


    # ------------------------------------------------------------------
    # FUNCIONES AUXILIARES: ANTECEDENTES
    # ------------------------------------------------------------------
    ####### LIMPIAR ########
    def limpiar_antecedentes():
        """Limpia tablas de antecedentes (historial) en la parte derecha."""
        antecedentes_medicos_table.rows.clear()
        antecedentes_psico_table.rows.clear()

    ####### CARGAR ######## 
    def cargar_antecedentes(documento: str):
        """Carga antecedentes médicos y psicológicos del paciente."""
        limpiar_antecedentes()

        # ------------------ Antecedentes médicos ------------------
        medicos = listar_antecedentes_medicos(documento)
        for a in medicos:
            acciones = ft.Row(
                [
                    ft.TextButton(
                        "Editar",
                        on_click=lambda e, ant=a: abrir_dialogo_editar_antecedente(
                            "medico", dict(ant)
                        ),
                    ),
                    
                    ft.TextButton(
                        "Eliminar",
                        on_click=lambda e, ant_id=a["id"]: confirmar_eliminar_antecedente(
                            "medico", ant_id
                        ),
                    ),
                ],
                spacing=5,
            )

            antecedentes_medicos_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(a["fecha_registro"])),
                        ft.DataCell(ft.Text(a["descripcion"])),
                        ft.DataCell(acciones),
                    ]
                )
            )

        # ---------------- Antecedentes psicológicos ----------------
        psicologicos = listar_antecedentes_psicologicos(documento)
        for a in psicologicos:
            acciones = ft.Row(
                [
                    ft.TextButton(
                        "Editar",
                        on_click=lambda e, ant=a: abrir_dialogo_editar_antecedente(
                            "psico", dict(ant)
                        ),
                    ),
                    ft.TextButton(
                        "Eliminar",
                        on_click=lambda e, ant_id=a["id"]: confirmar_eliminar_antecedente(
                            "psico", ant_id
                        ),
                    ),
                ],
                spacing=5,
            )

            antecedentes_psico_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(a["fecha_registro"])),
                        ft.DataCell(ft.Text(a["descripcion"])),
                        ft.DataCell(acciones),
                    ]
                )
            )

        page.update()

    # ------------------------------------------------------------------
    # FUNCIONES AUXILIARES: FORMULARIO PACIENTE

    def _solo_digitos_telefono(s: str) -> str:
        """Extrae solo dígitos. Útil para guardar en BD y para WhatsApp."""
        return "".join(c for c in (s or "") if c.isdigit())

    def _formatear_telefono_con_espacios(s: str) -> str:
        """Formatea el teléfono con espacios SIN limitar la cantidad de dígitos.

        Regla:
        - Formato base por bloque de 10 dígitos: 3-3-4  (ej: 320 679 8393)
        - Si hay más de 10 dígitos, repite el patrón 3-3-4 en el siguiente bloque
          (ej: 123 123 1234 123 123 1234)
        - Para el último bloque incompleto, aplica el mejor formato posible:
            * <=3: tal cual
            * 4-6: 3 + resto
            * 7-10: 3-3-resto
        """
        digits = _solo_digitos_telefono(s)
        if not digits:
            return ""

        partes = []
        i = 0
        n = len(digits)

        while i < n:
            bloque = digits[i : i + 10]
            if len(bloque) <= 3:
                partes.append(bloque)
            elif len(bloque) <= 6:
                partes.append(f"{bloque[:3]} {bloque[3:]}")
            else:
                # 7..10
                partes.append(f"{bloque[:3]} {bloque[3:6]} {bloque[6:]}")
            i += 10

        return " ".join(partes)

    # ------------------------------------------------------------------

    def limpiar_formulario():
        """
        Limpia el formulario de paciente y sale de modo edición.
        También resetea el panel de antecedentes (texto + tablas).
        """
        nonlocal modo_edicion, documento_seleccionado, form_dirty

        # TextFields
        documento.value = ""
        nombre_completo.value = ""
        fecha_nacimiento.value = ""
        escolaridad.value = ""
        eps.value = ""
        direccion.value = ""
        email.value = ""
        indicativo_pais.value = "CO"
        _actualizar_ui_pais()
        telefono.value = ""
        contacto_emergencia_nombre.value = ""
        contacto_emergencia_telefono.value = ""
        observaciones.value = ""
        antecedente_medico_form.value = ""
        antecedente_psico_form.value = ""
        datepicker_nacimiento.value = None
        edad.value = "-"

        # limpiar errores visuales de campos obligatorios
        for campo in (documento, tipo_documento, nombre_completo, fecha_nacimiento, email):
            campo.error_text = None

        mensaje_estado.value = ""
        mensaje_estado.color = "red"
        texto_contexto.value = ""

        # Dropdowns
        reset_dropdowns_a_default()

        # Salir de modo edición y marcar formulario limpio
        documento.disabled = False
        modo_edicion = False
        documento_seleccionado = None
        form_dirty = False

        # Reset panel de antecedentes
        etiqueta_paciente_antecedentes.value = (
            "Selecciona un paciente para ver sus antecedentes."
        )
        limpiar_antecedentes()

        # Ocultar sugerencias de EPS
        eps_sugerencias.visible = False
        eps_sugerencias.controls.clear()

        page.update()


    # ------------------------------------------------------------------
    # FUNCIONES: AUTOCOMPLETE EPS
    # ------------------------------------------------------------------

    def seleccionar_sugerencia_eps(valor: str):
        """Selecciona una EPS sugerida y oculta las sugerencias."""
        eps.value = valor
        eps_sugerencias.visible = False
        eps_sugerencias.controls.clear()

        marcar_formulario_sucio()
        page.update()

    def actualizar_sugerencias_eps(e=None):
        """
        Autocompletado básico de EPS:
        - Usa los valores existentes en pacientes_cache
        - Sugiere coincidencias que empiezan igual al texto digitado
        """
        texto = (eps.value or "").strip().lower()
        eps_sugerencias.controls.clear()

        if not texto:
            eps_sugerencias.visible = False
            page.update()
            return

        # Conjunto de EPS existentes no vacías
        eps_existentes = sorted(
            {
                (p.get("eps") or "").strip()
                for p in pacientes_cache
                if (p.get("eps") or "").strip()
            }
        )

        coincidencias = [
            val
            for val in eps_existentes
            if val.lower().startswith(texto) and val.lower() != texto
        ]

        if not coincidencias:
            eps_sugerencias.visible = False
        else:
            for val in coincidencias[:5]:
                eps_sugerencias.controls.append(
                    ft.TextButton(
                        text=val,
                        style=ft.ButtonStyle(padding=0),
                        on_click=lambda ev, v=val: seleccionar_sugerencia_eps(v),
                    )
                )
            eps_sugerencias.visible = True

        page.update()

    # ------------------------------------------------------------------
    # FUNCIONES: LISTA DE PACIENTES
    # ------------------------------------------------------------------

    def cargar_pacientes():
        """Carga todos los pacientes desde la BD y refresca la tabla."""
        nonlocal pacientes_cache
        pacientes = listar_pacientes()
        pacientes_cache = [dict(p) for p in pacientes]
        aplicar_filtro_tabla()
        # Actualizar posibles sugerencias para EPS
        actualizar_sugerencias_eps()

    def aplicar_filtro_tabla(e=None):
        """Aplica filtro de búsqueda sobre el cache y rellena la tabla."""
        texto = buscador.value.lower().strip() if buscador.value else ""
        tabla_pacientes.rows.clear()

        for p in pacientes_cache:
            if texto:
                if texto not in p["documento"].lower() and texto not in p[
                    "nombre_completo"
                ].lower():
                    continue

            # Documento como "link" para editar (con protección de cambios)
            doc_cell = ft.DataCell(
                ft.TextButton(
                    text=p["documento"],
                    on_click=lambda ev, doc=p["documento"]: intentar_cargar_paciente(
                        doc
                    ),
                )
            )

            acciones = ft.Row(
                [
                    ft.IconButton(
                        icon=ft.Icons.EDIT,
                        tooltip="Editar paciente",
                        on_click=lambda ev, doc=p["documento"]: intentar_cargar_paciente(
                            doc
                        ),  
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE,
                        tooltip="Eliminar",
                        on_click=lambda ev, doc=p["documento"]: confirmar_eliminar_paciente(
                            doc
                        ),
                    ),
                    ft.FilledButton(
                        text="Historia clínica",
                        icon=ft.Icons.DESCRIPTION,  # icono de documento / historia
                        on_click=lambda ev, doc=p["documento"]: abrir_historia(doc),
                    ),
                ],
                spacing=8,
            )

            tabla_pacientes.rows.append(
                ft.DataRow(
                    cells=[
                        doc_cell,
                        ft.DataCell(ft.Text(p["tipo_documento"])),
                        ft.DataCell(ft.Text(p["nombre_completo"])),
                        ft.DataCell(ft.Text(p["fecha_nacimiento"])),
                        ft.DataCell(ft.Text(calcular_edad_desde_fecha(p["fecha_nacimiento"]))),
                        ft.DataCell(ft.Text(p["sexo"])),
                        ft.DataCell(ft.Text((f"+{(p.get('indicativo_pais') or '57')} {(p.get('telefono') or '')}".strip() if (p.get('telefono') or '').strip() else ""))),
                        ft.DataCell(acciones),
                    ]
                )
            )

        page.update()

    # ------------------------------------------------------------------
    # FUNCIONES: CARGAR PACIENTE Y GUARDAR / ELIMINAR
    # ------------------------------------------------------------------

    def cargar_paciente_en_formulario(doc: str):
        """
        Carga los datos del paciente seleccionado en el formulario.
        También actualiza el panel de antecedentes para ese paciente.
        """
        nonlocal modo_edicion, documento_seleccionado, form_dirty

        fila = obtener_paciente(doc)
        if fila is None:
            mensaje_estado.value = "No se pudo cargar el paciente seleccionado."
            mensaje_estado.color = "red"
            page.update()
            return

        p = dict(fila)

        # Cargar datos básicos
        documento.value = p["documento"]
        tipo_documento.value = p["tipo_documento"]
        nombre_completo.value = p["nombre_completo"]
        fecha_nacimiento.value = p["fecha_nacimiento"]
        edad.value = calcular_edad_desde_fecha(p["fecha_nacimiento"])
        sexo.value = p.get("sexo") or "sexo_default"
        estado_civil.value = p.get("estado_civil") or "estado_default"
        escolaridad.value = p.get("escolaridad") or ""
        eps.value = p.get("eps") or ""
        direccion.value = p.get("direccion") or ""
        email.value = p.get("email") or ""
        email.error_text = None
        telefono.value = _formatear_telefono_con_espacios(p.get("telefono") or "")
        _code = _solo_digitos(p.get("indicativo_pais") or "57")
        indicativo_pais.value = _code_to_iso2.get(_code, "CO")
        _actualizar_ui_pais()
        contacto_emergencia_nombre.value = p.get("contacto_emergencia_nombre") or ""
        contacto_emergencia_telefono.value = _formatear_telefono_con_espacios(p.get("contacto_emergencia_telefono") or "")
        observaciones.value = p.get("observaciones") or ""

        # Campos de antecedentes se dejan vacíos (sirven para crear nuevos)
        antecedente_medico_form.value = ""
        antecedente_psico_form.value = ""

        # Estado de edición
        documento.disabled = True
        modo_edicion = True
        documento_seleccionado = p["documento"]
        texto_contexto.value = f"Editando paciente: {p['nombre_completo']}"

        # Panel de antecedentes
        etiqueta_paciente_antecedentes.value = (
            f"Antecedentes de: {p['nombre_completo']} ({p['documento']})"
        )
        cargar_antecedentes(p["documento"])
        actualizar_sugerencias_eps()

        # El formulario recién cargado se considera "limpio"
        form_dirty = False
        page.update()

        # Funcion para cargar paciente con protección de pérdida de datos
    def intentar_cargar_paciente(doc: str):
        """
        Protege contra pérdida de datos:
        - Si el formulario está limpio -> limpia mensajes/errores y carga directamente.
        - Si hay cambios sin guardar -> pide confirmación y, al confirmar,
          limpia mensajes/errores y carga el nuevo paciente.
        """
        nonlocal form_dirty

        # Helper: limpia mensajes y errores y luego carga el paciente
        def cargar_limpiando():
            # limpiar mensajes
            mensaje_estado.value = ""
            mensaje_estado.color = "red"
            # limpiar errores visuales en campos
            for campo in (documento, tipo_documento, nombre_completo, fecha_nacimiento, email):
                campo.error_text = None
            page.update()
            cargar_paciente_en_formulario(doc)

        if not form_dirty:
            cargar_limpiando()
            return

        def on_cancel(e):
            dialog.open = False
            page.update()

        def on_confirm(e):
            nonlocal form_dirty
            dialog.open = False
            # descartamos cambios no guardados
            form_dirty = False
            page.update()
            cargar_limpiando()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Cambios sin guardar"),
            content=ft.Text(
                "Hay cambios sin guardar en el formulario.\n"
                "Si continúas se perderán. ¿Deseas continuar?"
            ),
            actions=[
                ft.TextButton("No", on_click=on_cancel),
                ft.TextButton("Sí, continuar", on_click=on_confirm),
            ],
        )

        page.open(dialog)


    def guardar_paciente_handler(e):
        """
        Crea o actualiza un paciente.
        Además, si se diligencian antecedentes,
        se insertan en sus tablas correspondientes.
        """
        nonlocal modo_edicion, documento_seleccionado, form_dirty

        # Reset de errores visuales
        for campo in (documento, tipo_documento, nombre_completo, fecha_nacimiento, email):
            campo.error_text = None

        mensaje_estado.value = ""
        mensaje_estado.color = "red"

        # ------------------------------------------------------
        # 1) VALIDACIÓN DE CAMPOS OBLIGATORIOS
        # ------------------------------------------------------
        errores_obligatorios = False

        if not (documento.value or "").strip():
            documento.error_text = "Requerido"
            errores_obligatorios = True

        if not tipo_documento.value or tipo_documento.value == "tipo_default":
            tipo_documento.error_text = "Requerido"
            errores_obligatorios = True

        if not (nombre_completo.value or "").strip():
            nombre_completo.error_text = "Requerido"
            errores_obligatorios = True

        if not (fecha_nacimiento.value or "").strip():
            fecha_nacimiento.error_text = "Requerido"
            errores_obligatorios = True

        if errores_obligatorios:
            mensaje_estado.value = "Hay campos obligatorios sin llenar."
            page.update()
            return

        # ------------------------------------------------------
        # 2) VALIDACIÓN DE FORMATO DE FECHA Y EMAIL (SIMULTÁNEOS)
        # ------------------------------------------------------
        hay_errores = False

        fn = (fecha_nacimiento.value or "").strip()
        try:
            datetime.strptime(fn, "%d-%m-%Y")
        except ValueError:
            fecha_nacimiento.error_text = "La fecha de nacimiento no es válida. Usa formato DD-MM-YYYY."
            hay_errores = True

        correo = (email.value or "").strip()
        if correo and not email_valido(correo):
            email.error_text = "Correo inválido, revisa el formato."
            hay_errores = True

        if hay_errores:
            mensaje_estado.value = "Hay errores en el formulario."
            page.update()
            return

        # ------------------------------------------------------
        # 3) SI TODO ESTÁ OK, CONSTRUIR OBJETO PACIENTE Y GUARDAR
        # ------------------------------------------------------
        paciente = {
            "documento": documento.value.strip(),
            "tipo_documento": (tipo_documento.value or "").strip(),
            "nombre_completo": nombre_completo.value.strip(),
            "fecha_nacimiento": fn,
            "sexo": (sexo.value or "").strip()
            if sexo.value not in ("sexo_default", None)
            else "",
            "estado_civil": (estado_civil.value or "").strip()
            if estado_civil.value not in ("estado_default", None)
            else "",
            "escolaridad": (escolaridad.value or "").strip(),
            "eps": eps.value.strip(),
            "direccion": direccion.value.strip(),
            "email": correo,
            "indicativo_pais": _iso2_to_code.get((indicativo_pais.value or "CO").upper(), "57"),
            "telefono": _solo_digitos_telefono(telefono.value),
            "contacto_emergencia_nombre": contacto_emergencia_nombre.value.strip(),
            "contacto_emergencia_telefono": _solo_digitos_telefono(contacto_emergencia_telefono.value),
            "observaciones": observaciones.value.strip(),
        }

        try:
            if modo_edicion and documento_seleccionado == paciente["documento"]:
                actualizar_paciente(paciente)
                texto_snack = "Paciente actualizado correctamente."
            else:
                crear_paciente(paciente)
                texto_snack = "Paciente guardado correctamente."
        except Exception as ex:
            mensaje_estado.value = f"Error al guardar paciente: {ex}"
            page.update()
            return

        # Registrar antecedentes si se diligenciaron
        doc = paciente["documento"]
        txt_med = (antecedente_medico_form.value or "").strip()
        txt_psico = (antecedente_psico_form.value or "").strip()

        if txt_med:
            crear_antecedente_medico(doc, txt_med)
        if txt_psico:
            crear_antecedente_psicologico(doc, txt_psico)

        # Mensaje de éxito
        mensaje_estado.color = "green"
        mensaje_estado.value = texto_snack

        # Formulario queda "limpio"
        form_dirty = False

        # Refrescar tabla y mantener paciente cargado
        cargar_pacientes()
        cargar_paciente_en_formulario(doc)

        mostrar_snackbar(texto_snack)

    # ------------------------------------------------------------------
    # ELIMINAR PACIENTE + CONFIRMACIÓN
    # ------------------------------------------------------------------

    def eliminar_paciente_action(doc: str):
        """Elimina un paciente y refresca la lista."""
        nonlocal modo_edicion, documento_seleccionado, form_dirty

        try:
            eliminar_paciente(doc)
        except Exception as ex:
            mensaje_estado.value = f"Error al eliminar paciente: {ex}"
            mensaje_estado.color = "red"
            page.update()
            return

        # Si estaba en edición, limpiamos el formulario
        if modo_edicion and documento_seleccionado == doc:
            limpiar_formulario()
        else:
            # Por si el formulario estaba cargado pero no en modo_edicion
            form_dirty = False

        cargar_pacientes()
        mensaje_estado.value = f"Paciente {doc} eliminado correctamente."
        mensaje_estado.color = "green"
        mostrar_snackbar(f"Paciente {doc} eliminado.")
        page.update()


    def abrir_historia(doc: str):
        """Navega a la vista de Historia clínica para este paciente."""
        # Guardar el documento en la sesión (o como atributo de fallback)
        try:
            page.session.set("historia_paciente_documento", doc)
        except Exception:
            setattr(page, "historia_paciente_documento", doc)

        # Buscar callback registrado en main.py
        cb = getattr(page, "mostrar_historia_cb", None)
        if callable(cb):
            cb(None)
        else:
            # Fallback si por alguna razón no existe mostrar_historia_cb
            page.snack_bar = ft.SnackBar(
                content=ft.Text(
                    "La vista de Historia clínica no está disponible."
                )
            )
            page.snack_bar.open = True
            page.update()

    def confirmar_eliminar_paciente(doc: str):
        """Muestra un diálogo de confirmación antes de eliminar un paciente."""

        def on_cancel(e):
            dialog.open = False
            page.update()

        def on_confirm(e):
            dialog.open = False
            page.update()
            eliminar_paciente_action(doc)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Eliminar paciente"),
            content=ft.Text(
                f"¿Estás seguro de eliminar al paciente con documento {doc}?\n"
                "Esta acción no se puede deshacer."
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=on_cancel),
                ft.TextButton("Eliminar", on_click=on_confirm),
            ],
        )

        # Forma recomendada en versiones recientes de Flet
        page.open(dialog)

    # ------------------------------------------------------------------
    # MANEJO DE FECHA: FORMATEO AUTOMÁTICO
    # ------------------------------------------------------------------

    def formatear_fecha_nacimiento(e=None):
        """
        Mientras el usuario escribe, se formatea como DD-MM-YYYY.
        Solo se permiten dígitos, se insertan guiones automáticamente.
        """
        valor = fecha_nacimiento.value or ""
        digitos = "".join(ch for ch in valor if ch.isdigit())
        if len(digitos) > 8:
            digitos = digitos[:8]

        if len(digitos) <= 2:
            nuevo = digitos
        elif len(digitos) <= 4:
            nuevo = f"{digitos[:2]}-{digitos[2:]}"
        else:
            nuevo = f"{digitos[:2]}-{digitos[2:4]}-{digitos[4:]}"

        if fecha_nacimiento.value != nuevo:
            fecha_nacimiento.value = nuevo
            page.update()

    # ------------------------------------------------------------------
    # MANEJO DE DIÁLOGO DE CANCELAR
    # ------------------------------------------------------------------

    def abrir_dialogo_cancelar(e):
        """Muestra confirmación antes de limpiar el formulario."""

        def on_no(ev):
            dialog.open = False
            page.update()

        def on_si(ev):
            dialog.open = False
            page.update()
            limpiar_formulario()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Cancelar edición"),
            content=ft.Text(
                "¿Deseas cancelar y limpiar todos los campos del formulario?"
            ),
            actions=[
                ft.TextButton("No", on_click=on_no),
                ft.TextButton("Sí", on_click=on_si),
            ],
        )

        page.open(dialog)

    # ------------------------------------------------------------------
    # WIRING DE EVENTOS (incluye tracking de cambios)
    # ------------------------------------------------------------------

    buscador.on_change = aplicar_filtro_tabla

    # Campos que marcan el formulario como "sucio"
    documento.on_change = marcar_formulario_sucio
    tipo_documento.on_change = marcar_formulario_sucio
    nombre_completo.on_change = marcar_formulario_sucio
    sexo.on_change = marcar_formulario_sucio
    estado_civil.on_change = marcar_formulario_sucio
    escolaridad.on_change = marcar_formulario_sucio
    direccion.on_change = marcar_formulario_sucio
    email.on_change = marcar_formulario_sucio
    contacto_emergencia_nombre.on_change = marcar_formulario_sucio
    observaciones.on_change = marcar_formulario_sucio
    antecedente_medico_form.on_change = marcar_formulario_sucio
    antecedente_psico_form.on_change = marcar_formulario_sucio

    # EPS: autocompletar + marcar sucio
    def on_eps_change(e):
        marcar_formulario_sucio(e)
        actualizar_sugerencias_eps(e)

    eps.on_change = on_eps_change

    # Fecha: formatear + marcar sucio
    def on_fecha_change(e):
        marcar_formulario_sucio(e)
        formatear_fecha_nacimiento(e)
        # Después de formatear, intentar calcular edad
        edad.value = calcular_edad_desde_fecha(fecha_nacimiento.value or "")
        page.update()

    fecha_nacimiento.on_change = on_fecha_change

    boton_guardar = ft.ElevatedButton(
        text="Guardar paciente",
        on_click=guardar_paciente_handler,
        icon=ft.Icons.SAVE,
    )

    boton_limpiar = ft.TextButton(
        text="Limpiar",
        on_click=lambda e: limpiar_formulario(),
    )

    boton_cancelar = ft.TextButton(
        text="Cancelar",
        on_click=abrir_dialogo_cancelar,
    )

    #FUNCION CALCULAR EDAD

    def calcular_edad_desde_fecha(fecha_str: str) -> str:
        """
        Recibe fecha en formato DD-MM-YYYY y devuelve edad (años) como string.
        Si la fecha es inválida, devuelve "".
        """
        if not fecha_str:
            return ""

        try:
            fecha = datetime.strptime(fecha_str, "%d-%m-%Y").date()
        except ValueError:
            return ""

        hoy = datetime.today().date()
        años = hoy.year - fecha.year - (
            (hoy.month, hoy.day) < (fecha.month, fecha.day)
        )
        if años < 0:
            return ""
        return str(años)
    
    #FUNCION Para actualizar fecha desde datepicker

    def actualizar_fecha_desde_datepicker(e: ft.ControlEvent):
        # e.control es el DatePicker, su value es un datetime.date
        if not e.control.value:
            return

        d: date = e.control.value

        # 1) Actualizar el TextField con formato DD-MM-YYYY
        fecha_nacimiento.value = d.strftime("%d-%m-%Y")
        fecha_nacimiento.error_text = None  # limpiar errores si los había

        # 2) Recalcular edad
        hoy = date.today()
        edad_num = hoy.year - d.year - ((hoy.month, hoy.day) < (d.month, d.day))
        edad.value = str(edad_num)

        # Si quieres marcar el formulario como “sucio”:
        marcar_formulario_sucio()

        page.update()

    datepicker_nacimiento.on_change = actualizar_fecha_desde_datepicker


    def validar_fecha_nacimiento_manual():
        try:
            d = datetime.strptime(fecha_nacimiento.value, "%d-%m-%Y").date()
            if d > date.today():
                fecha_nacimiento.error_text = "La fecha no puede ser futura"
                edad.value = ""
                page.update()
                return False
            return d
        except Exception:
            fecha_nacimiento.error_text = "Formato inválido (DD-MM-YYYY)"
            edad.value = ""
            page.update()
            return False
     
    def abrir_datepicker(e):
        """
        Abre el DatePicker sincronizando la fecha con el contenido del TextField.
        Si la fecha del TextField es válida, el DatePicker abrirá en esa fecha.
        Si no es válida o está vacío, el DatePicker queda sin selección.
        """

        try:
            if fecha_nacimiento.value:
                # Parsear fecha escrita (DD-MM-YYYY)
                d = datetime.strptime(fecha_nacimiento.value, "%d-%m-%Y").date()

                # No permitir fechas futuras
                if d > date.today():
                    fecha_nacimiento.error_text = "La fecha no puede ser futura"
                    page.update()
                    return

                # Sincronizar el datepicker con esa fecha
                datepicker_nacimiento.value = d
            else:
                # Si el campo está vacío, dejamos el datepicker sin selección
                datepicker_nacimiento.value = None

        except Exception:
            # Si el formato es inválido, abrimos el datepicker "en blanco"
            datepicker_nacimiento.value = None

        # Ahora sí, abrimos el datepicker
        page.open(datepicker_nacimiento)

#SUFIJO AL FINAL PARA QUE SALGA EL ICONO DE CALENDARIO EN EL TEXTFIELD

    fecha_nacimiento.suffix = ft.IconButton(
        icon=ft.Icons.CALENDAR_MONTH,
        tooltip="Abrir calendario",
        on_click=abrir_datepicker,
    )
    
     # ---------------- Excel Import/Export ----------------

    def _snack_ok(msg: str):
        page.snack_bar = ft.SnackBar(content=ft.Text(msg))
        page.snack_bar.open = True
        page.update()

    def _snack_err(msg: str):
        page.snack_bar = ft.SnackBar(content=ft.Text(msg))
        page.snack_bar.open = True
        page.update()

    def on_pick_import_result(e: ft.FilePickerResultEvent):
        if not e.files:
            return

        archivo = e.files[0].path
        if not archivo:
            _snack_err("No se pudo acceder a la ruta del archivo. (En web, usa versión desktop o ajusta lectura por bytes).")
            return
        try:
            # (Opcional) validar antes para fallar rápido con mensaje claro
            validar_archivo_pacientes_excel(archivo)

            res = importar_pacientes_desde_excel(archivo)
            cargar_pacientes()

            resumen = f"Importación OK. Insertados: {res.insertados}, Actualizados: {res.actualizados}."
            if res.warnings:
                resumen += f" Avisos: {len(res.warnings)}."
            if res.errores:
                resumen += f" Errores: {len(res.errores)}."

            _snack_ok(resumen)

            # Mostrar detalles si hay
            if res.warnings:
                _show_dialog("Avisos de importación", res.warnings)

            if res.errores:
                # si hay MUCHOS, mostramos los primeros N para no saturar
                _show_dialog("Errores de importación (primeros 200)", res.errores[:200])

        except PlantillaExcelInvalidaError as ex:
            _snack_err("Archivo inválido para importar.")
            _show_dialog("Archivo inválido", [
                str(ex),
                "",
                "Sugerencias:",
                "- Usa el botón 'Plantilla' para descargar la plantilla oficial.",
                "- No cambies el nombre/orden de columnas.",
                "- Verifica que sea .xlsx (no .csv).",
            ])
        except Exception as ex:
            _snack_err(f"Error importando Excel: {ex}")

    def on_pick_export_path(e: ft.FilePickerResultEvent):
        # save_file retorna path en e.path (en desktop)
        if not e.path:
            return
        try:
            exportar_pacientes_a_excel(e.path)
            _snack_ok("Exportación OK: archivo generado.")
        except Exception as ex:
            _snack_err(f"Error exportando Excel: {ex}")

    def on_pick_template_path(e: ft.FilePickerResultEvent):
        if not e.path:
            return
        try:
            crear_plantilla_pacientes(e.path)
            _snack_ok("Plantilla creada.")
        except Exception as ex:
            _snack_err(f"Error creando plantilla: {ex}")

    picker_import = ft.FilePicker(on_result=on_pick_import_result)
    picker_export = ft.FilePicker(on_result=on_pick_export_path)
    picker_template = ft.FilePicker(on_result=on_pick_template_path)

    page.overlay.extend([picker_import, picker_export, picker_template])




    # ------------------------------------------------------------------
    # LAYOUT (FORMULARIO + LISTADO + ANTECEDENTES)
    # ------------------------------------------------------------------

    # EPS + sugerencias en la misma columna para que salgan justo debajo
    eps_col = ft.Column([eps, eps_sugerencias], spacing=0)

    # Sección: Registro de paciente
    formulario = ft.Card(
        content=ft.Container(
            padding=15,
            content=ft.Column(
                [
                    ft.Text("Registro de paciente", size=20, weight="bold"),
                    ft.Row([documento, tipo_documento, nombre_completo], wrap=True),
                    ft.Row([fecha_nacimiento, edad, sexo, estado_civil], wrap=True),
                    ft.Row([escolaridad, eps_col], wrap=True),  # o eps_stack o eps_col si luego lo volvíamos a usar

                    ft.Row([direccion], wrap=True),
                    ft.Row([email, btn_pais, telefono], wrap=True),
                    ft.Row(
                        [contacto_emergencia_nombre, contacto_emergencia_telefono],
                        wrap=True,
                    ),
                    observaciones,
                    antecedente_medico_form,
                    antecedente_psico_form,
                    ft.Row(
                        [boton_guardar, boton_limpiar, boton_cancelar],
                        spacing=10,
                    ),
                    mensaje_estado,
                    texto_contexto,
                ],
                spacing=10,
            ),
        )
    )

    # Sección: Pacientes registrados
    listado = ft.Card(
        content=ft.Container(
            padding=15,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Pacientes registrados", size=20, weight="bold"),
                            ft.Row(
                                [
                                    buscador,
                                    ft.OutlinedButton(
                                        "Plantilla",
                                        icon=ft.Icons.DESCRIPTION_OUTLINED,
                                        tooltip="Descargar plantilla vacía para importar",
                                        on_click=lambda ev: picker_template.save_file(
                                            file_name="plantilla_pacientes.xlsx",
                                            allowed_extensions=["xlsx"],
                                        ),
                                    ),
                                    ft.OutlinedButton(
                                        "Exportar",
                                        icon=ft.Icons.FILE_DOWNLOAD,
                                        tooltip="Exportar todos los pacientes a Excel",
                                        on_click=lambda ev: picker_export.save_file(
                                            file_name="pacientes_export.xlsx",
                                            allowed_extensions=["xlsx"],
                                        ),
                                    ),
                                    ft.FilledButton(
                                        "Importar",
                                        icon=ft.Icons.FILE_UPLOAD,
                                        tooltip="Importar pacientes desde Excel",
                                        on_click=lambda ev: picker_import.pick_files(
                                            allow_multiple=False,
                                            allowed_extensions=["xlsx"],
                                        ),
                                    ),
                                    btn_sync_forms,
                                ],
                                spacing=8,
                                wrap=True,
                            ),
                        ],
                        alignment="spaceBetween",
                        wrap=True,
                    ),
                     sync_banner,
                    # Contenedor con altura fija + scroll interno
                    ft.Container(
                        height=250,  # ajusta este valor si quieres más / menos alto
                        content=ft.Column(
                            [tabla_pacientes],
                            scroll=ft.ScrollMode.AUTO,
                        ),
                    ),
                ],
                spacing=10,
            ),
        )
    )


    # Sección: Historial de antecedentes (lado derecho)
    antecedentes_panel = ft.Card(
        content=ft.Container(
            padding=15,
            content=ft.Column(
                [
                    etiqueta_paciente_antecedentes,
                    ft.Text("Antecedentes médicos:", weight="bold"),
                    ft.Container(
                        height=150,  # altura fija para médicos
                        content=ft.Column(
                            [antecedentes_medicos_table],
                            scroll=ft.ScrollMode.AUTO,
                        ),
                    ),
                    ft.Text("Antecedentes psicológicos:", weight="bold"),
                    ft.Container(
                        height=150,  # altura fija para psicológicos
                        content=ft.Column(
                            [antecedentes_psico_table],
                            scroll=ft.ScrollMode.AUTO,
                        ),
                    ),
                ],
                spacing=10,
            ),
        )
    )


    # ------------------------------------------------------------------
    # INICIALIZACIÓN DE LA VISTA
    # ------------------------------------------------------------------

    reset_dropdowns_a_default()
    limpiar_antecedentes()
    cargar_pacientes()

    # Fila superior: formulario + antecedentes al lado
    fila_superior = ft.Row(
        [
            formulario,
            antecedentes_panel,
        ],
        alignment="start",
        vertical_alignment="start",
    )

    return ft.Column(
        [
            fila_superior,
            listado,
        ],
        spacing=20,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )