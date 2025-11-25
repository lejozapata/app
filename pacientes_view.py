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
)


def build_pacientes_view(page: ft.Page) -> ft.Control:
    """
    Vista principal de gestión de pacientes:
    - Formulario de registro/edición
    - Listado de pacientes
    - Historial de antecedentes por paciente
    """

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
        label="Fecha nacimiento (DD-MM-YYYY)",
        width=200,
        hint_text="Ej: 21-04-1993",
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
    direccion = ft.TextField(label="Dirección", width=400)
    email = ft.TextField(label="Email", width=300)
    telefono = ft.TextField(label="Teléfono de contacto", width=200)

    contacto_emergencia_nombre = ft.TextField(
        label="Nombre contacto de emergencia", width=300
    )
    contacto_emergencia_telefono = ft.TextField(
        label="Teléfono contacto de emergencia", width=200
    )

    observaciones = ft.TextField(
        label="Observaciones",
        multiline=True,
        min_lines=2,
        max_lines=4,
        width=600,
    )

    # Campos para registrar antecedentes iniciales al crear/editar paciente
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

    mensaje_estado = ft.Text(value="", color="red")

    # ------------------------------------------------------------------
    # CONTROLES PARA HISTORIAL DE ANTECEDENTES (PARTE INFERIOR)
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
        ],
        rows=[],
    )

    antecedentes_psico_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Fecha registro")),
            ft.DataColumn(ft.Text("Descripción")),
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

    # Cache en memoria para filtrar sin ir siempre a la BD
    pacientes_cache = []

    # Estado de edición de paciente
    modo_edicion = False
    documento_seleccionado = None

    # ------------------------------------------------------------------
    # FUNCIONES AUXILIARES
    # ------------------------------------------------------------------

    def reset_dropdowns_a_default():
        """Pone los dropdowns en su opción inicial ('Seleccione ...')."""
        tipo_documento.value = "tipo_default"
        sexo.value = "sexo_default"
        estado_civil.value = "estado_default"

    def limpiar_antecedentes():
        """Limpia tablas de antecedentes (historial) en la parte inferior."""
        antecedentes_medicos_table.rows.clear()
        antecedentes_psico_table.rows.clear()

    def cargar_antecedentes(documento: str):
        """Carga antecedentes médicos y psicológicos del paciente."""
        limpiar_antecedentes()

        # Antecedentes médicos
        medicos = listar_antecedentes_medicos(documento)
        for a in medicos:
            antecedentes_medicos_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(a["fecha_registro"])),
                        ft.DataCell(ft.Text(a["descripcion"])),
                    ]
                )
            )

        # Antecedentes psicológicos
        psicologicos = listar_antecedentes_psicologicos(documento)
        for a in psicologicos:
            antecedentes_psico_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(a["fecha_registro"])),
                        ft.DataCell(ft.Text(a["descripcion"])),
                    ]
                )
            )

        page.update()

    def limpiar_formulario():
        """
        Limpia el formulario de paciente y sale de modo edición.
        También resetea el panel de antecedentes (texto + tablas).
        """
        nonlocal modo_edicion, documento_seleccionado

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
        mensaje_estado.value = ""

        # Dropdowns
        reset_dropdowns_a_default()

        # Salir de modo edición
        documento.disabled = False
        modo_edicion = False
        documento_seleccionado = None

        # Reset panel de antecedentes
        etiqueta_paciente_antecedentes.value = (
            "Selecciona un paciente para ver sus antecedentes."
        )
        limpiar_antecedentes()

        page.update()

    def cargar_pacientes():
        """Carga todos los pacientes desde la BD y refresca la tabla."""
        nonlocal pacientes_cache
        pacientes = listar_pacientes()
        pacientes_cache = [dict(p) for p in pacientes]
        aplicar_filtro_tabla()

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

            acciones = ft.Row(
                [
                    ft.TextButton(
                        "Editar",
                        on_click=lambda ev, doc=p["documento"]: cargar_paciente_en_formulario(
                            doc
                        ),
                    ),
                    ft.TextButton(
                        "Eliminar",
                        on_click=lambda ev, doc=p["documento"]: eliminar_paciente_action(
                            doc
                        ),
                    ),
                ],
                spacing=5,
            )

            tabla_pacientes.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(p["documento"])),
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

    def cargar_paciente_en_formulario(doc: str):
        """
        Carga los datos del paciente seleccionado en el formulario.
        También actualiza el panel de antecedentes para ese paciente.
        """
        nonlocal modo_edicion, documento_seleccionado

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
        sexo.value = p.get("sexo") or "sexo_default"
        estado_civil.value = p.get("estado_civil") or "estado_default"
        escolaridad.value = p.get("escolaridad") or ""
        eps.value = p.get("eps") or ""
        direccion.value = p.get("direccion") or ""
        email.value = p.get("email") or ""
        telefono.value = p.get("telefono") or ""
        contacto_emergencia_nombre.value = p.get("contacto_emergencia_nombre") or ""
        contacto_emergencia_telefono.value = p.get("contacto_emergencia_telefono") or ""
        observaciones.value = p.get("observaciones") or ""

        # Campos de antecedentes iniciales se dejan vacíos (sirven para crear nuevos)
        antecedente_medico_form.value = ""
        antecedente_psico_form.value = ""

        # Estado de edición
        documento.disabled = True
        modo_edicion = True
        documento_seleccionado = p["documento"]
        mensaje_estado.value = f"Editando paciente: {p['nombre_completo']}"
        mensaje_estado.color = "blue"

        # Actualizar panel de antecedentes
        etiqueta_paciente_antecedentes.value = (
            f"Antecedentes de: {p['nombre_completo']} ({p['documento']})"
        )
        cargar_antecedentes(p["documento"])

        page.update()

    def guardar_paciente_handler(e):
        """
        Crea o actualiza un paciente.
        Además, si se diligencian antecedentes iniciales,
        se insertan en sus tablas correspondientes.
        """
        nonlocal modo_edicion, documento_seleccionado

        obligatorios = [
            (documento, "Documento"),
            (tipo_documento, "Tipo documento"),
            (nombre_completo, "Nombre completo"),
            (fecha_nacimiento, "Fecha de nacimiento"),
        ]

        for campo, nombre in obligatorios:
            if not campo.value:
                mensaje_estado.value = f"El campo '{nombre}' es obligatorio."
                mensaje_estado.color = "red"
                page.update()
                return

        paciente = {
            "documento": documento.value.strip(),
            "tipo_documento": (tipo_documento.value or "").strip(),
            "nombre_completo": nombre_completo.value.strip(),
            "fecha_nacimiento": fecha_nacimiento.value.strip(),
            "sexo": (sexo.value or "").strip()
            if sexo.value not in ("sexo_default", None)
            else "",
            "estado_civil": (estado_civil.value or "").strip()
            if estado_civil.value not in ("estado_default", None)
            else "",
            "escolaridad": (escolaridad.value or "").strip(),
            "eps": eps.value.strip(),
            "direccion": direccion.value.strip(),
            "email": email.value.strip(),
            "telefono": telefono.value.strip(),
            "contacto_emergencia_nombre": contacto_emergencia_nombre.value.strip(),
            "contacto_emergencia_telefono": contacto_emergencia_telefono.value.strip(),
            "observaciones": observaciones.value.strip(),
        }

        try:
            if modo_edicion and documento_seleccionado == paciente["documento"]:
                actualizar_paciente(paciente)
                mensaje_estado.value = "Paciente actualizado correctamente."
            else:
                crear_paciente(paciente)
                mensaje_estado.value = "Paciente guardado correctamente."
        except Exception as ex:
            mensaje_estado.value = f"Error al guardar paciente: {ex}"
            mensaje_estado.color = "red"
            page.update()
            return

        # Registrar antecedentes iniciales si se diligenciaron
        doc = paciente["documento"]
        txt_med = (antecedente_medico_form.value or "").strip()
        txt_psico = (antecedente_psico_form.value or "").strip()

        if txt_med:
            crear_antecedente_medico(doc, txt_med)
        if txt_psico:
            crear_antecedente_psicologico(doc, txt_psico)

        mensaje_estado.color = "green"

        # Tras guardar, recargamos tabla y limpiamos formulario
        limpiar_formulario()
        cargar_pacientes()

    def eliminar_paciente_action(doc: str):
        """Elimina un paciente y refresca la lista."""
        nonlocal modo_edicion, documento_seleccionado

        eliminar_paciente(doc)

        # Si estaba en edición, limpiamos el formulario
        if modo_edicion and documento_seleccionado == doc:
            limpiar_formulario()

        mensaje_estado.value = f"Paciente {doc} eliminado."
        mensaje_estado.color = "green"
        cargar_pacientes()
        page.update()

    # ------------------------------------------------------------------
    # WIRING DE EVENTOS
    # ------------------------------------------------------------------

    buscador.on_change = aplicar_filtro_tabla

    boton_guardar = ft.ElevatedButton(
        text="Guardar paciente",
        on_click=guardar_paciente_handler,
    )

    boton_limpiar = ft.TextButton(
        text="Limpiar",
        on_click=lambda e: limpiar_formulario(),
    )

    # ------------------------------------------------------------------
    # LAYOUT (FORMULARIO + LISTADO + ANTECEDENTES)
    # ------------------------------------------------------------------

    # Sección: Registro de paciente
    formulario = ft.Card(
        content=ft.Container(
            padding=15,
            content=ft.Column(
                [
                    ft.Text("Registro de paciente", size=20, weight="bold"),
                    ft.Row([documento, tipo_documento, nombre_completo], wrap=True),
                    ft.Row([fecha_nacimiento, sexo, estado_civil], wrap=True),
                    ft.Row([escolaridad, eps], wrap=True),
                    ft.Row([direccion], wrap=True),
                    ft.Row([email, telefono], wrap=True),
                    ft.Row([contacto_emergencia_nombre, contacto_emergencia_telefono]),
                    observaciones,
                    antecedente_medico_form,
                    antecedente_psico_form,
                    ft.Row([boton_guardar, boton_limpiar], spacing=10),
                    mensaje_estado,
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
                    tabla_pacientes,
                ],
                spacing=10,
            ),
        )
    )

    # Sección: Historial de antecedentes
    antecedentes_panel = ft.Card(
        content=ft.Container(
            padding=15,
            content=ft.Column(
                [
                    etiqueta_paciente_antecedentes,
                    ft.Text("Antecedentes médicos:", weight="bold"),
                    antecedentes_medicos_table,
                    ft.Text("Antecedentes psicológicos:", weight="bold"),
                    antecedentes_psico_table,
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
