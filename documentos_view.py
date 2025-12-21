# documentos_view.py
from typing import Dict, Any, List, Optional
import os
import sqlite3
from datetime import datetime

import flet as ft

from .db import DB_PATH, listar_pacientes, listar_citas_por_paciente
from .paths import get_documentos_dir

from .documentos_pdf import (
    generar_pdf_consentimiento,
    generar_pdf_certificado_asistencia,
    generar_pdf_consentimiento_vacio,
)

from .notificaciones_email import (
    enviar_correo_con_adjunto_pdf,
    construir_email_consentimiento,
    construir_email_certificado_asistencia,
)


# -----------------------------
# Helpers de nombres/rutas (fallback si no usas tabla documentos_generados)
# -----------------------------
def _safe_filename(name: str) -> str:
    for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
        name = name.replace(ch, "-")
    return name.strip()


def _parse_fecha_hora(fecha_hora_raw) -> Optional[datetime]:
    if not fecha_hora_raw:
        return None
    s = str(fecha_hora_raw).strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt)
        except Exception:
            pass
    try:
        return datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
    except Exception:
        return None


def _format_fecha_larga_es(dt: datetime) -> str:
    meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]
    return f"{dt.day} de {meses[dt.month - 1]} de {dt.year}"


def _path_consentimiento(pac: Dict[str, Any]) -> str:
    out_dir = get_documentos_dir()
    nombre = (pac.get("nombre_completo") or "").strip()
    doc = (pac.get("documento") or "").strip()
    fname = _safe_filename(f"Consentimiento - {nombre} ({doc}).pdf")
    return os.path.join(out_dir, fname)


def _path_certificado(pac: Dict[str, Any], cita: Dict[str, Any]) -> Optional[str]:
    out_dir = get_documentos_dir()
    nombre = (pac.get("nombre_completo") or "").strip()
    doc = (pac.get("documento") or "").strip()
    dt = _parse_fecha_hora(cita.get("fecha_hora"))
    if not dt:
        return None
    fname = _safe_filename(f"Certificado Asistencia - {nombre} ({doc}) - {dt.strftime('%d-%m-%Y')}.pdf")
    return os.path.join(out_dir, fname)


def _parse_recipients(raw: str) -> List[str]:
    if not raw:
        return []
    parts = raw.replace(",", ";").split(";")
    return [p.strip() for p in parts if p.strip()]


def _get_profesional_config() -> dict:
    """
    Lee configuracion_profesional (si existe) para From dinámico.
    No exige que exista tabla/columnas.
    """
    cfg = {
        "nombre_profesional": "Sara Hernández Ramírez",
        "email": "",  # opcional
        "tp": "180733",
        "ciudad": "Medellín",
    }
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        try:
            cur.execute("SELECT nombre_profesional FROM configuracion_profesional LIMIT 1;")
            row = cur.fetchone()
            if row and row[0]:
                cfg["nombre_profesional"] = str(row[0]).strip()
        except Exception:
            pass

        try:
            cur.execute("SELECT email FROM configuracion_profesional LIMIT 1;")
            row = cur.fetchone()
            if row and row[0]:
                cfg["email"] = str(row[0]).strip()
        except Exception:
            pass

        for col in ("tarjeta_profesional", "tp", "numero_tarjeta_profesional"):
            try:
                cur.execute(f"SELECT {col} FROM configuracion_profesional LIMIT 1;")
                row = cur.fetchone()
                if row and row[0]:
                    cfg["tp"] = str(row[0]).strip()
                    break
            except Exception:
                continue

        try:
            cur.execute("SELECT ciudad FROM configuracion_profesional LIMIT 1;")
            row = cur.fetchone()
            if row and row[0]:
                cfg["ciudad"] = str(row[0]).strip()
        except Exception:
            pass

        conn.close()
    except Exception:
        pass

    return cfg


def build_documentos_view(page: ft.Page) -> ft.Control:
    pacientes_cache: List[Dict[str, Any]] = [dict(p) for p in listar_pacientes()]
    paciente_actual: Dict[str, Optional[Dict[str, Any]]] = {"value": None}

    cita_actual: Dict[str, Optional[Dict[str, Any]]] = {"value": None}
    citas_cache: Dict[str, Dict[str, Any]] = {}

    cfg_prof = _get_profesional_config()
    msg_consent = ft.Text("", size=12, weight=ft.FontWeight.W_600)
    msg_cert = ft.Text("", size=12, weight=ft.FontWeight.W_600)

    # -----------------------------
    # Helpers UI
    # -----------------------------
    def snack(msg: str, success: bool = False):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(msg),
            bgcolor=ft.Colors.GREEN_600 if success else ft.Colors.RED_600,
        )
        page.snack_bar.open = True
        page.update()

    def paciente_label(p: Dict[str, Any]) -> str:
        return f"{p.get('nombre_completo','')} ({p.get('documento','')})"

    def formato_cita_label(c: Dict[str, Any]) -> str:
        fh = str(c.get("fecha_hora") or "")
        fecha = fh[:10] if len(fh) >= 10 else fh
        hora = fh[11:16] if len(fh) >= 16 else ""
        motivo = str(c.get("motivo") or "Sesión")
        estado = str(c.get("estado") or "").strip()
        canal = str(c.get("canal") or "").strip()
        modalidad = str(c.get("modalidad") or "").strip()
        extras = " · ".join([x for x in [canal, modalidad, estado] if x])
        base = f"{fecha} {hora} - {motivo}".strip()
        return f"{base} ({extras})" if extras else base

    # -----------------------------
    # FilePicker (Guardar como...) para formato vacío
    # -----------------------------
    save_picker = ft.FilePicker()

    def _on_save_result(e: ft.FilePickerResultEvent):
        if not e.path:
            return
        try:
            generar_pdf_consentimiento_vacio(e.path, abrir=True, force=True)
            snack("✅ Formato vacío generado.")
        except Exception as ex:
            snack(f"❌ Error generando formato vacío: {ex}")

    save_picker.on_result = _on_save_result
    page.overlay.append(save_picker)

    # -----------------------------
    # Encabezado panel derecho
    # -----------------------------
    header_paciente = ft.Text(
        "Selecciona un paciente a la izquierda",
        size=18,
        weight=ft.FontWeight.BOLD,
        color=ft.Colors.BLUE_900,
    )

    info_paciente = ft.Text(
        "Aquí podrás generar consentimiento informado y certificados de asistencia.",
        color=ft.Colors.GREY_700,
    )

    # -----------------------------
    # Dropdown de citas
    # -----------------------------
    dd_citas = ft.Dropdown(
        label="Selecciona una cita para certificar asistencia",
        width=720,
        options=[],
    )

    # -----------------------------
    # Botones e hints (Consentimiento)
    # -----------------------------
    btn_send_consent = ft.OutlinedButton("Enviar por correo", icon=ft.Icons.EMAIL, disabled=True)
    hint_consent = ft.Text("", size=11, color=ft.Colors.GREY_700)
    chk_firma_consent = ft.Checkbox(
        label="Firma consentimiento",
        value=False,   # 👈 desmarcado por defecto
    )

    # -----------------------------
    # Botones e hints (Certificado)
    # -----------------------------
    chk_cert_to_patient = ft.Checkbox(label="Enviar a paciente", value=True)
    txt_cert_emails = ft.TextField(
        label="Correo(s) destino (separados por ;)",
        hint_text="ej: convenio@empresa.com; rrhh@empresa.com",
        width=520,
        dense=True,
        visible=False,     # 👈 solo se muestra si desmarcas el checkbox
        disabled=False,
    )
    btn_send_cert = ft.OutlinedButton("Enviar por correo", icon=ft.Icons.EMAIL, disabled=True)
    hint_cert = ft.Text("", size=11, color=ft.Colors.GREY_700)

    def _toggle_cert_dest(_=None):
        # Si está marcado "Enviar a paciente", ocultamos por completo el textfield
        txt_cert_emails.visible = not bool(chk_cert_to_patient.value)
        page.update()

    chk_cert_to_patient.on_change = _toggle_cert_dest

    # -----------------------------
    # Estados habilitación según existencia PDF
    # -----------------------------
    def refresh_state_consentimiento():
        pac = paciente_actual["value"]
        if not pac:
            btn_send_consent.disabled = True
            hint_consent.value = ""
            page.update()
            return

        pdf_path = _path_consentimiento(pac)
        if os.path.exists(pdf_path):
            btn_send_consent.disabled = False
            hint_consent.value = f"Listo para enviar: {os.path.basename(pdf_path)}"
        else:
            btn_send_consent.disabled = True
            hint_consent.value = "No hay consentimiento generado para este paciente."
        page.update()

    def refresh_state_certificado():
        pac = paciente_actual["value"]
        cita = cita_actual["value"]
        if not pac or not cita:
            btn_send_cert.disabled = True
            hint_cert.value = ""
            page.update()
            return

        pdf_path = _path_certificado(pac, cita)
        if pdf_path and os.path.exists(pdf_path):
            btn_send_cert.disabled = False
            hint_cert.value = f"Listo para enviar: {os.path.basename(pdf_path)}"
        else:
            btn_send_cert.disabled = True
            hint_cert.value = "No hay certificado generado para esta cita."
        page.update()

    # -----------------------------
    # Cargar citas
    # -----------------------------
    def cargar_citas():
        dd_citas.options.clear()
        dd_citas.value = None
        citas_cache.clear()
        cita_actual["value"] = None

        pac = paciente_actual["value"]
        if not pac:
            refresh_state_certificado()
            return

        try:
            citas = [dict(c) for c in listar_citas_por_paciente(pac["documento"])]
        except Exception:
            citas = []

        for c in citas:
            cid = str(c.get("id"))
            citas_cache[cid] = c
            dd_citas.options.append(ft.dropdown.Option(cid, formato_cita_label(c)))

        if not citas:
            dd_citas.options.append(ft.dropdown.Option("", "Este paciente no tiene citas agendadas."))
            dd_citas.value = ""
            cita_actual["value"] = None

        refresh_state_certificado()
        page.update()

    def on_cita_change(e):
        if dd_citas.value and dd_citas.value in citas_cache:
            cita_actual["value"] = citas_cache[dd_citas.value]
        else:
            cita_actual["value"] = None
        refresh_state_certificado()

    dd_citas.on_change = on_cita_change

    # -----------------------------
    # Acciones PDF
    # -----------------------------
    def generar_consentimiento_vacio_ui(_):
        try:
            save_picker.save_file(
                dialog_title="Guardar consentimiento vacío",
                file_name="Consentimiento_vacio.pdf",
                allowed_extensions=["pdf"],
            )
        except Exception as ex:
            snack(f"❌ No se pudo abrir el diálogo de guardado: {ex}")

    def generar_consentimiento_ui(_):
        pac = paciente_actual["value"]
        if not pac:
            return snack("Selecciona un paciente primero.")
        try:
            generar_pdf_consentimiento(pac["documento"], abrir=True, force=True, incluir_firma_profesional=bool(chk_firma_consent.value))
            snack("✅ Consentimiento generado.")
            refresh_state_consentimiento()
        except Exception as ex:
            snack(f"❌ Error generando consentimiento: {ex}")

    def generar_certificado_ui(_):
        pac = paciente_actual["value"]
        if not pac:
            return snack("Selecciona un paciente primero.")
        if not dd_citas.value or dd_citas.value == "" or dd_citas.value not in citas_cache:
            return snack("Selecciona una cita válida primero.")
        try:
            generar_pdf_certificado_asistencia(int(dd_citas.value), abrir=True, force=True)
            snack("✅ Certificado generado.")
            cita_actual["value"] = citas_cache.get(dd_citas.value)
            refresh_state_certificado()
        except Exception as ex:
            snack(f"❌ Error generando certificado: {ex}")

    # -----------------------------
    # Envío correos
    # -----------------------------
    def enviar_consentimiento_email(_):
        pac = paciente_actual["value"]
        if not pac:
            return snack("Selecciona un paciente primero.")

        pdf_path = _path_consentimiento(pac)
        if not os.path.exists(pdf_path):
            refresh_state_consentimiento()
            return snack("No hay consentimiento generado para este paciente.")

        email_paciente = (pac.get("email") or "").strip()
        if not email_paciente:
            return snack("El paciente no tiene email registrado.")

        nombre_paciente = pac.get("nombre_completo") or "Paciente"
        subject, body_text, body_html = construir_email_consentimiento(nombre_paciente)

        try:
            enviar_correo_con_adjunto_pdf(
                to_emails=[email_paciente],
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                pdf_path=pdf_path,
                cfg_profesional=cfg_prof,
            )
            snack("✅ Correo enviado con el consentimiento adjunto.", success=True)
            msg_consent.value = "✅ Correo enviado correctamente."
            msg_consent.color = ft.Colors.GREEN_700
            msg_consent.update()
            page.run_task(_clear_msg_consent)
        except Exception as ex:
            snack(f"❌ Error enviando correo: {ex}")
            msg_consent.value = f"❌ Error enviando correo: {ex}"
            msg_consent.color = ft.Colors.RED_700
            msg_consent.update()

    def enviar_certificado_email(_):
        pac = paciente_actual["value"]
        cita = cita_actual["value"]
        if not pac:
            return snack("Selecciona un paciente primero.")
        if not cita:
            return snack("Selecciona una cita primero.")

        pdf_path = _path_certificado(pac, cita)
        if not pdf_path or not os.path.exists(pdf_path):
            refresh_state_certificado()
            return snack("No hay certificado generado para esta cita.")

        if chk_cert_to_patient.value:
            recipients = [(pac.get("email") or "").strip()]
            recipients = [r for r in recipients if r]
            if not recipients:
                return snack("El paciente no tiene email registrado.")
        else:
            recipients = _parse_recipients(txt_cert_emails.value or "")
            if not recipients:
                return snack("Debes ingresar al menos un correo destino (separados por ;).")

        nombre_paciente = pac.get("nombre_completo") or "Paciente"
        dt = _parse_fecha_hora(cita.get("fecha_hora"))
        fecha_humano = _format_fecha_larga_es(dt) if dt else ""

        subject, body_text, body_html = construir_email_certificado_asistencia(nombre_paciente, fecha_humano)

        try:
            enviar_correo_con_adjunto_pdf(
                to_emails=recipients,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                pdf_path=pdf_path,
                cfg_profesional=cfg_prof,
            )
            snack("✅ Correo enviado con el certificado adjunto.", success=True)
            msg_cert.value = "✅ Correo enviado correctamente."
            msg_cert.color = ft.Colors.GREEN_700
            msg_cert.update()
            page.run_task(_clear_msg_cert)
        except Exception as ex:
            snack(f"❌ Error enviando correo: {ex}")
            msg_cert.value = f"❌ Error enviando correo: {ex}"
            msg_cert.color = ft.Colors.RED_700
            msg_cert.update()

    btn_send_consent.on_click = enviar_consentimiento_email
    btn_send_cert.on_click = enviar_certificado_email
    
    
    import asyncio

    async def _clear_msg_consent():
        await asyncio.sleep(3)
        msg_consent.value = ""
        msg_consent.update()

    async def _clear_msg_cert():
        await asyncio.sleep(3)
        msg_cert.value = ""
        msg_cert.update()

    # -----------------------------
    # Selección de paciente
    # -----------------------------
    def seleccionar_paciente(p: Dict[str, Any]):
        paciente_actual["value"] = p
        header_paciente.value = paciente_label(p)

        telefono = p.get("telefono") or ""
        email = p.get("email") or ""
        bullets = []
        if telefono:
            bullets.append(f"📞 {telefono}")
        if email:
            bullets.append(f"✉️ {email}")

        info_paciente.value = " · ".join(bullets) if bullets else "Paciente seleccionado. Genera documentos desde los botones."

        cargar_citas()
        refresh_state_consentimiento()
        _toggle_cert_dest()
        page.update()

    # -----------------------------
    # Cards (sin “bloques grises”)
    # -----------------------------
    btn_formato_vacio = ft.OutlinedButton(
        "Formato vacío",
        icon=ft.Icons.DESCRIPTION_OUTLINED,
        on_click=generar_consentimiento_vacio_ui,
    )

    card_consentimiento = ft.Container(
        padding=16,
        border=ft.border.all(1, ft.Colors.GREY_300),
        border_radius=14,
        bgcolor=ft.Colors.WHITE,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Container(
                            width=54,
                            height=54,
                            border_radius=14,
                            bgcolor=ft.Colors.ORANGE_50,
                            alignment=ft.alignment.center,
                            content=ft.Icon(ft.Icons.ASSIGNMENT, size=28, color=ft.Colors.ORANGE_700),
                        ),
                        ft.Container(width=10),
                        ft.Column(
                            [
                                ft.Text("Consentimiento informado", size=16, weight=ft.FontWeight.BOLD),
                                ft.Text(
                                    "Genera un PDF con los datos del paciente y plantilla para firma. Luego puedes enviarlo por correo.",
                                    color=ft.Colors.GREY_700,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                ft.Container(height=10),
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Generar consentimiento (PDF)",
                            icon=ft.Icons.PICTURE_AS_PDF,
                            on_click=generar_consentimiento_ui,
                        ),
                        btn_send_consent,
                        btn_formato_vacio,
                    ],
                    spacing=10,
                    wrap=True,
                ),
                hint_consent,
                chk_firma_consent,
                msg_consent,
            ],
            spacing=0,
        ),
    )

    card_certificado = ft.Container(
        padding=16,
        border=ft.border.all(1, ft.Colors.GREY_300),
        border_radius=14,
        bgcolor=ft.Colors.WHITE,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Container(
                            width=54,
                            height=54,
                            border_radius=14,
                            bgcolor=ft.Colors.GREEN_50,
                            alignment=ft.alignment.center,
                            content=ft.Icon(ft.Icons.VERIFIED, size=28, color=ft.Colors.GREEN_700),
                        ),
                        ft.Container(width=10),
                        ft.Column(
                            [
                                ft.Text("Certificado de asistencia", size=16, weight=ft.FontWeight.BOLD),
                                ft.Text(
                                    "Elige una cita, genera el certificado y envíalo por correo si existe el PDF.",
                                    color=ft.Colors.GREY_700,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                ft.Container(height=10),
                dd_citas,
                ft.Container(height=8),
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Generar certificado (PDF)",
                            icon=ft.Icons.PICTURE_AS_PDF,
                            on_click=generar_certificado_ui,
                        ),
                        ft.TextButton(
                            "Recargar citas",
                            icon=ft.Icons.REFRESH,
                            on_click=lambda e: (cargar_citas(), page.update()),
                        ),
                        btn_send_cert,
                    ],
                    spacing=10,
                    wrap=True,
                ),
                hint_cert,
                msg_cert,
                ft.Container(height=8),
                chk_cert_to_patient,
                txt_cert_emails,
            ],
            spacing=0,
        ),
    )

    panel_derecho = ft.Column(
        [
            header_paciente,
            info_paciente,
            ft.Container(height=12),
            ft.Text("Acciones", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_800),
            ft.Container(height=6),
            card_consentimiento,
            ft.Container(height=10),
            card_certificado,
        ],
        spacing=6,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )

    # -----------------------------
    # Sidebar izquierda
    # -----------------------------
    txt_buscar = ft.TextField(
        label="Buscar paciente",
        hint_text="nombre o documento",
        prefix_icon=ft.Icons.SEARCH,
        dense=True,
    )

    lista_pacientes = ft.ListView(expand=True, spacing=2, padding=0)

    def render_lista(q: str = ""):
        lista_pacientes.controls.clear()
        qq = (q or "").strip().lower()

        data = pacientes_cache
        if qq and len(qq) >= 2:
            data = [
                p for p in pacientes_cache
                if qq in (f"{p.get('nombre_completo','')} {p.get('documento','')}".lower())
            ]

        data = data[:80]

        for p in data:
            label = paciente_label(p)
            lista_pacientes.controls.append(
                ft.Container(
                    border_radius=10,
                    padding=8,
                    ink=True,
                    on_click=lambda e, pac=p: seleccionar_paciente(pac),
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.PERSON, color=ft.Colors.BLUE_700),
                            ft.Text(label, expand=True),
                        ],
                        spacing=10,
                    ),
                )
            )
        page.update()

    txt_buscar.on_change = lambda e: render_lista(txt_buscar.value)

    sidebar = ft.Container(
        width=360,
        padding=12,
        border=ft.border.all(1, ft.Colors.GREY_300),
        border_radius=14,
        bgcolor=ft.Colors.WHITE,
        content=ft.Column(
            [
                ft.Text("Pacientes", size=16, weight=ft.FontWeight.BOLD),
                ft.Text("Selecciona uno para generar documentos.", color=ft.Colors.GREY_700),
                ft.Container(height=8),
                txt_buscar,
                ft.Container(height=8),
                lista_pacientes,
            ],
            spacing=6,
            expand=True,
        ),
    )

    render_lista("")

    return ft.Container(
        padding=12,
        content=ft.Row(
            [
                sidebar,
                ft.Container(width=12),
                ft.Container(
                    padding=12,
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    border_radius=14,
                    bgcolor=ft.Colors.WHITE,
                    expand=True,
                    content=panel_derecho,
                ),
            ],
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        expand=True,
    )
