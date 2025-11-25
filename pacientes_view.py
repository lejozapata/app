import re
from datetime import datetime

import flet as ft
from db import (
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
)


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

    # ------------------------------------------------------------------
    # CONTROLES DEL FORMULARIO DE PACIENTE
    # ------------------------------------------------------------------

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

    sexo = ft.Dropdown(
        label="Sexo",
        width=150,
        options=[
            ft.DropdownOption(
                text="Seleccione sexo...",
                key="sexo_default",
                disabled=True,
            ),
            ft.dropdown.Option("F"),
            ft.dropdown.Option("M"),
            ft.dropdown.Option("Otro"),
            ft.dropdown.Option("Prefiere no decir"),
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
    telefono = ft.TextField(label="Teléfono de contacto", width=200)

    contacto_emergencia_nombre = ft.TextField(
        label="Nombre contacto de emergencia",
        width=300,
    )
    contacto_emergencia_telefono = ft.TextField(
        label="Teléfono contacto de emergencia",
        width=200,
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
            ft.DataColumn(ft.Text("Sexo")),
            ft.DataColumn(ft.Text("Teléfono")),
            ft.DataColumn(ft.Text("EPS")),
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

    def marcar_formulario_sucio(e=None):
        """Marca que el formulario tiene cambios sin guardar."""
        nonlocal form_dirty
        form_dirty = True

    # ------------------------------------------------------------------
    # EDICIÓN / ELIMINACIÓN DE ANTECEDENTES
    # ------------------------------------------------------------------

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
        telefono.value = ""
        contacto_emergencia_nombre.value = ""
        contacto_emergencia_telefono.value = ""
        observaciones.value = ""
        antecedente_medico_form.value = ""
        antecedente_psico_form.value = ""
        edad.value = ""

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
                    ft.TextButton(
                        "Editar",
                        on_click=lambda ev, doc=p["documento"]: intentar_cargar_paciente(
                            doc
                        ),
                    ),
                    ft.TextButton(
                        "Eliminar",
                        on_click=lambda ev, doc=p["documento"]: confirmar_eliminar_paciente(
                            doc
                        ),
                    ),
                ],
                spacing=5,
            )

            tabla_pacientes.rows.append(
                ft.DataRow(
                    cells=[
                        doc_cell,
                        ft.DataCell(ft.Text(p["tipo_documento"])),
                        ft.DataCell(ft.Text(p["nombre_completo"])),
                        ft.DataCell(ft.Text(p["fecha_nacimiento"])),
                        ft.DataCell(ft.Text(p.get("sexo") or "")),
                        ft.DataCell(ft.Text(p.get("telefono") or "")),
                        ft.DataCell(ft.Text(p.get("eps") or "")),
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
        telefono.value = p.get("telefono") or ""
        contacto_emergencia_nombre.value = p.get("contacto_emergencia_nombre") or ""
        contacto_emergencia_telefono.value = p.get("contacto_emergencia_telefono") or ""
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
            "telefono": telefono.value.strip(),
            "contacto_emergencia_nombre": contacto_emergencia_nombre.value.strip(),
            "contacto_emergencia_telefono": contacto_emergencia_telefono.value.strip(),
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
    telefono.on_change = marcar_formulario_sucio
    contacto_emergencia_nombre.on_change = marcar_formulario_sucio
    contacto_emergencia_telefono.on_change = marcar_formulario_sucio
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
                    ft.Row([escolaridad, eps], wrap=True),  # o eps_stack o eps_col si luego lo volvíamos a usar

                    ft.Row([direccion], wrap=True),
                    ft.Row([email, telefono], wrap=True),
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
                            buscador,
                        ],
                        alignment="spaceBetween",
                        wrap=True,
                    ),
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
    )
