import flet as ft
from db import crear_paciente, listar_pacientes


def build_pacientes_view(page: ft.Page) -> ft.Control:
    # ------------- CONTROLES DEL FORMULARIO -------------

    documento = ft.TextField(label="Documento", width=200)
    tipo_documento = ft.Dropdown(
        label="Tipo documento",
        width=150,
        options=[
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
        hint_text="Ej: 01-01-1990",
    )

    sexo = ft.Dropdown(
        label="Sexo",
        width=150,
        options=[
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
            ft.dropdown.Option("Soltera/o"),
            ft.dropdown.Option("Casada/o"),
            ft.dropdown.Option("Unión libre"),
            ft.dropdown.Option("Divorciada/o"),
            ft.dropdown.Option("Viuda/o"),
        ],
    )

    escolaridad = ft.TextField(label="Escolaridad",width=250,)
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

    mensaje_estado = ft.Text(value="", color="red")

    # ------------- TABLA DE PACIENTES -------------

    tabla_pacientes = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Documento")),
            ft.DataColumn(ft.Text("Tipo")),
            ft.DataColumn(ft.Text("Nombre")),
            ft.DataColumn(ft.Text("Fecha nac.")),
            ft.DataColumn(ft.Text("Sexo")),
            ft.DataColumn(ft.Text("Teléfono")),
            ft.DataColumn(ft.Text("EPS")),
        ],
        rows=[],
    )

    buscador = ft.TextField(
        label="Buscar por documento o nombre",
        width=400,
    )

    # Cache en memoria de pacientes para filtros
    pacientes_cache = []

    # ------------- FUNCIONES -------------

    def cargar_pacientes():
        nonlocal pacientes_cache
        pacientes = listar_pacientes()
        pacientes_cache = [dict(p) for p in pacientes]
        aplicar_filtro_tabla()

    def aplicar_filtro_tabla(e=None):
        texto = buscador.value.lower().strip() if buscador.value else ""
        tabla_pacientes.rows.clear()

        for p in pacientes_cache:
            if texto:
                if texto not in p["documento"].lower() and texto not in p[
                    "nombre_completo"
                ].lower():
                    continue

            fila = ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(p["documento"])),
                    ft.DataCell(ft.Text(p["tipo_documento"])),
                    ft.DataCell(ft.Text(p["nombre_completo"])),
                    ft.DataCell(ft.Text(p["fecha_nacimiento"])),
                    ft.DataCell(ft.Text(p.get("sexo") or "")),
                    ft.DataCell(ft.Text(p.get("telefono") or "")),
                    ft.DataCell(ft.Text(p.get("eps") or "")),
                ]
            )
            tabla_pacientes.rows.append(fila)

        page.update()

    def limpiar_formulario():
        documento.value = ""
        tipo_documento.value = None
        nombre_completo.value = ""
        fecha_nacimiento.value = ""
        sexo.value = None
        estado_civil.value = None
        escolaridad.value = ""
        eps.value = ""
        direccion.value = ""
        email.value = ""
        telefono.value = ""
        contacto_emergencia_nombre.value = ""
        contacto_emergencia_telefono.value = ""
        observaciones.value = ""
        mensaje_estado.value = ""
        page.update()

    def guardar_paciente(e):
        # Validaciones básicas
        campos_obligatorios = [
            (documento, "Documento"),
            (tipo_documento, "Tipo documento"),
            (nombre_completo, "Nombre completo"),
            (fecha_nacimiento, "Fecha de nacimiento"),
        ]

        for campo, nombre in campos_obligatorios:
            if not campo.value:
                mensaje_estado.value = f"El campo '{nombre}' es obligatorio."
                mensaje_estado.color = "red"
                page.update()
                return

        # Construir diccionario para la BD
        paciente = {
            "documento": documento.value.strip(),
            "tipo_documento": (tipo_documento.value or "").strip(),
            "nombre_completo": nombre_completo.value.strip(),
            "fecha_nacimiento": fecha_nacimiento.value.strip(),
            "sexo": (sexo.value or "").strip(),
            "estado_civil": (estado_civil.value or "").strip(),
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
            crear_paciente(paciente)
        except Exception as ex:
            mensaje_estado.value = f"Error al guardar paciente: {ex}"
            mensaje_estado.color = "red"
            page.update()
            return

        mensaje_estado.value = "Paciente guardado correctamente."
        mensaje_estado.color = "green"
        page.snack_bar = ft.SnackBar(ft.Text("Paciente guardado correctamente."))
        page.snack_bar.open = True

        limpiar_formulario()
        cargar_pacientes()

    # ------------- EVENTOS -------------

    buscador.on_change = aplicar_filtro_tabla

    boton_guardar = ft.ElevatedButton(
        text="Guardar paciente",
        on_click=guardar_paciente,
    )

    boton_limpiar = ft.TextButton(
        text="Limpiar formulario",
        on_click=lambda e: limpiar_formulario(),
    )

    # ------------- LAYOUT -------------

    formulario = ft.Card(
        content=ft.Container(
            padding=15,
            content=ft.Column(
                [
                    ft.Text(
                        "Registro de paciente",
                        size=20,
                        weight="bold",
                    ),
                    ft.Row(
                        [documento, tipo_documento, nombre_completo],
                        wrap=True,
                    ),
                    ft.Row(
                        [fecha_nacimiento, sexo, estado_civil],
                        wrap=True,
                    ),
                    ft.Row(
                        [escolaridad, eps],
                        wrap=True,
                    ),
                    ft.Row(
                        [direccion],
                        wrap=True,
                    ),
                    ft.Row(
                        [email, telefono],
                        wrap=True,
                    ),
                    ft.Row(
                        [contacto_emergencia_nombre, contacto_emergencia_telefono],
                        wrap=True,
                    ),
                    observaciones,
                    ft.Row(
                        [boton_guardar, boton_limpiar],
                        spacing=10,
                    ),
                    mensaje_estado,
                ],
                spacing=10,
            ),
        )
    )

    listado = ft.Card(
        content=ft.Container(
            padding=15,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                "Pacientes registrados",
                                size=20,
                                weight="bold",
                            ),
                            buscador,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        wrap=True,
                    ),
                    tabla_pacientes,
                ],
                spacing=10,
            ),
        )
    )

    layout = ft.Column(
        [
            formulario,
            listado,
        ],
        spacing=20,
    )

    # Cargar datos al iniciar la vista
    cargar_pacientes()

    return layout
