# notificaciones_email.py
import os
import smtplib
from email.message import EmailMessage
from datetime import datetime
from typing import Dict, Any
import base64
from pathlib import Path 



# Nombres de días y meses en español
DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


# ----------------- Configuración SMTP -----------------

SMTP_HOST = os.getenv("SARA_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SARA_SMTP_PORT", "587"))
SMTP_USER = os.getenv("SARA_SMTP_USER")           # ej: "tu_correo@gmail.com"
SMTP_PASSWORD = os.getenv("SARA_SMTP_PASSWORD")   

# Preferimos configuración guardada en BD (UI) y dejamos variables de entorno como fallback.
def _cargar_credenciales_gmail() -> tuple[str | None, str | None]:
    """
    Retorna (user, app_password) usando:
      1) configuracion_gmail en SQLite (si está habilitado y completo)
      2) variables de entorno SARA_SMTP_USER / SARA_SMTP_PASSWORD
    """
    try:
        from .db import obtener_configuracion_gmail  # import local para evitar ciclos
        cfg = obtener_configuracion_gmail()
        if cfg.get("habilitado") and cfg.get("gmail_user") and cfg.get("gmail_app_password"):
            from .crypto_utils import decrypt_str
            return (str(cfg.get("gmail_user")), decrypt_str(str(cfg.get("gmail_app_password"))))
    except Exception:
        # Si la BD no está disponible por algún motivo, caemos a env vars.
        pass

    return (SMTP_USER, SMTP_PASSWORD)

# app-password, etc.


class ConfigSMTPIncompleta(Exception):
    """Se lanza cuando faltan datos mínimos de configuración SMTP."""
    pass


def _fmt_ics(dt: datetime) -> str:
    """Fecha/hora a formato ICS (sin zona)."""
    return dt.strftime("%Y%m%dT%H%M00")


def enviar_correo_cita(
    paciente: Dict[str, Any],
    datos_cita: Dict[str, Any],
    hora_fin_str: str,
    cita_id: int,
    cfg_profesional: Dict[str, Any],
    es_nueva: bool,
) -> None:
    """
    Envía un correo al paciente con la información de la cita y adjunta un .ics.

    - paciente: dict con al menos 'nombre_completo', 'email'
    - datos_cita: dict con al menos 'fecha_hora' (YYYY-MM-DD HH:MM), 'motivo', 'modalidad'
    - hora_fin_str: "HH:MM"
    - cita_id: id de la cita en BD
    - cfg_profesional: configuración leída de la BD
    - es_nueva: True si es cita nueva, False si se actualizó

    Puede lanzar:
      - ConfigSMTPIncompleta
      - Exception genérica si falla el envío
    """
    email_paciente = (paciente.get("email") or "").strip()
    if not email_paciente:
        # Nada que enviar
        return

    smtp_user, smtp_password = _cargar_credenciales_gmail()

    if not (SMTP_HOST and smtp_user and smtp_password):
        raise ConfigSMTPIncompleta(
            "Faltan SARA_SMTP_HOST / SARA_SMTP_USER / SARA_SMTP_PASSWORD"
        )
    

    # Logo y enlaces de redes / reseñas
    # Logo y enlaces de redes / reseñas
    LOGO_FILENAME = os.getenv("SARA_LOGO_FILENAME", "logo 1.png")  # nombre del archivo
    BASE_DIR = Path(__file__).resolve().parent                      # carpeta donde está este .py
    LOGO_PATH = BASE_DIR / LOGO_FILENAME
    GOOGLE_REVIEW_URL = "https://www.google.com/search?sca_esv=d66c42d153706fad&hl=es-419&authuser=0&sxsrf=ACQVn08X1s9kLuXojTDiDjeimxVE9teP1g:1709915095679&q=Sara+Hern%C3%A1ndez+psic%C3%B3loga&ludocid=15239444784275656350&lsig=AB86z5UkyK7Bgli9_fkGpOJaCti0&kgs=2a2a639d348f50e4&shndl=-1&shem=lsp&source=sh/x/loc/act/m1/3#lkt=LocalPoiReviews&lpg=cid:CgIgAQ%3D%3D"
    INSTAGRAM_URL = "https://www.instagram.com/psicologa_sarahdz"

    # ----------------- Preparar datos de la cita -----------------

    dt_inicio = datetime.strptime(datos_cita["fecha_hora"], "%Y-%m-%d %H:%M")

    # Fecha en español
    dia_sem = DIAS_ES[dt_inicio.weekday()]
    mes_nom = MESES_ES[dt_inicio.month - 1]
    fecha_str_humano = f"{dia_sem.capitalize()} {dt_inicio.day:02d} de {mes_nom} de {dt_inicio.year}"

    # Hora en formato 12h con AM/PM
    hora_inicio_humano = dt_inicio.strftime("%I:%M %p").lstrip("0")  # ej: "8:00 PM"

    fecha_solo = datos_cita["fecha_hora"].split(" ")[0]
    dt_fin = datetime.strptime(f"{fecha_solo} {hora_fin_str}", "%Y-%m-%d %H:%M")

    nombre_prof = cfg_profesional.get("nombre_profesional") or "Tu profesional"
    email_prof = (cfg_profesional.get("email") or smtp_user or "").strip()
    direccion = cfg_profesional.get("direccion") or ""
    telefono_prof = cfg_profesional.get("telefono") or ""
    # "Modalidad" en el correo debe reflejar el CANAL (presencial/virtual)
    canal_raw = (datos_cita.get("canal") or "").strip()

    canal_map = {
        "presencial": "Presencial",
        "virtual": "Virtual",
    }

    # Compatibilidad con modelos antiguos
    if not canal_raw:
        fallback = (datos_cita.get("modalidad") or "").strip()
        if fallback in canal_map:
            canal_raw = fallback

    modalidad = canal_map.get(canal_raw, "Presencial")
    motivo_raw = datos_cita.get("motivo") or ""
    # En el correo preferimos mostrar "Valor" en vez de "Precio"
    motivo = motivo_raw.replace("Precio", "Valor")

    # Texto para mostrar en el cuerpo
    accion_texto = "nueva cita" if es_nueva else "actualización de tu cita"

    # Texto para el asunto
    sujeto_accion = "Reservada nueva cita" if es_nueva else "Actualizada cita"
    subject = f"{sujeto_accion} el {fecha_str_humano} a las {hora_inicio_humano}"

    nombre_paciente = (paciente.get("nombre_completo") or "").strip() or "paciente"

    # ----------------- Cuerpo del mensaje (texto plano) -----------------

    body_text = (
        f"Hola {nombre_paciente},\n\n"
        f"Se ha registrado una {accion_texto}.\n\n"
        f"Profesional: {nombre_prof}\n"
        f"Modalidad: {modalidad}\n"
        f"Servicio / motivo: {motivo}\n"
        f"Fecha: {fecha_str_humano}\n"
        f"Hora: {hora_inicio_humano}\n"
    )

    if direccion:
        body_text += f"Dirección: {direccion}\n"
    if telefono_prof:
        body_text += f"Teléfono: {telefono_prof}\n"

    body_text += (
        "\nAdjuntamos un archivo de calendario (.ics) para que puedas "
        "agregar la cita a tu calendario (Google, Outlook, etc.).\n\n"
        "Si no reconoces este correo, puedes ignorarlo."
    )

    # Logo en base64 (si el archivo existe)
     # Logo en base64 (si el archivo existe)
    logo_src = None
    try:
        if LOGO_PATH.is_file():
            with LOGO_PATH.open("rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
                logo_src = f"data:image/png;base64,{b64}"
    except Exception:
        logo_src = None

    # ----------------- Cuerpo HTML (un poco más 'pro') -----------------

    estado_chip = "Agendada" if es_nueva else "Actualizada"

    body_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background-color:#f5f5f5; padding:16px;">
        <div style="max-width:600px; margin:0 auto; background-color:#ffffff; border-radius:8px; overflow:hidden; box-shadow:0 2px 6px rgba(0,0,0,0.08);">
          <div style="background:linear-gradient(90deg,#f7b267,#f4845f); padding:16px 20px; color:#ffffff; text-align:center;">
    """



    body_html += f"""
            <div style="font-size:18px; font-weight:bold;">{nombre_prof}</div>
            <div style="font-size:13px; opacity:0.9;">Psicología / Atención clínica</div>
          </div>
          <div style="padding:20px;">
            <p style="font-size:16px; font-weight:bold; margin:0 0 8px 0;">
              ¡Hola {nombre_paciente}!
            </p>
            <p style="margin:0 0 16px 0; font-size:14px;">
              Te informamos que se ha registrado una <strong>{accion_texto}</strong>.
            </p>

            <div style="display:inline-block; padding:4px 10px; border-radius:16px; background-color:#e1bee7; color:#4a148c; font-size:11px; font-weight:bold; margin-bottom:12px;">
              {estado_chip}
            </div>

            <table style="width:100%; font-size:14px; border-collapse:collapse;">
              <tr>
                <td style="padding:4px 0; width:120px; color:#555;"><strong>Fecha</strong></td>
                <td style="padding:4px 0;">{fecha_str_humano}</td>
              </tr>
              <tr>
                <td style="padding:4px 0; color:#555;"><strong>Hora</strong></td>
                <td style="padding:4px 0;">{hora_inicio_humano}</td>
              </tr>
              <tr>
                <td style="padding:4px 0; color:#555;"><strong>Modalidad</strong></td>
                <td style="padding:4px 0;">{modalidad}</td>
              </tr>
              <tr>
                <td style="padding:4px 0; color:#555;"><strong>Servicio / valor</strong></td>
                <td style="padding:4px 0;">{motivo}</td>
              </tr>
              <tr>
                <td style="padding:4px 0; color:#555;"><strong>Profesional</strong></td>
                <td style="padding:4px 0;">{nombre_prof}</td>
              </tr>
    """


    if direccion:
        body_html += f"""
              <tr>
                <td style="padding:4px 0; color:#555;"><strong>Dirección</strong></td>
                <td style="padding:4px 0;">{direccion}</td>
              </tr>
        """

    if telefono_prof:
        body_html += f"""
              <tr>
                <td style="padding:4px 0; color:#555;"><strong>Teléfono</strong></td>
                <td style="padding:4px 0;">{telefono_prof}</td>
              </tr>
        """

    body_html += """
            </table>

            <p style="margin-top:16px; font-size:13px;">
              Adjuntamos un archivo de calendario (<strong>.ics</strong>) para que puedas
              agregar la cita a tu calendario (Google Calendar, Outlook, etc.).
            </p>

            <p style="margin-top:16px; font-size:11px; color:#777;">
              Si no reconoces este correo, puedes ignorarlo.
            </p>
          </div>
        </div>
      </body>
    </html>
    """

    # ----------------- ICS -----------------

    uid = f"cita-{cita_id}-{paciente.get('documento','')}@sara-psicologa"
    dtstamp = _fmt_ics(datetime.utcnow())

    resumen_ics = f"Cita psicológica con {nombre_prof}"
    descripcion_ics = f"{motivo} - Paciente: {nombre_paciente}"

    ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//SaraPsicologa//Agenda//ES
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{dtstamp}Z
DTSTART:{_fmt_ics(dt_inicio)}
DTEND:{_fmt_ics(dt_fin)}
SUMMARY:{resumen_ics}
DESCRIPTION:{descripcion_ics}
END:VEVENT
END:VCALENDAR
"""

    # ----------------- Enviar correo -----------------

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{nombre_prof} <{email_prof or smtp_user}>"
    msg["To"] = email_paciente

    msg.set_content(body_text)
    msg.add_alternative(body_html, subtype="html")

    msg.add_attachment(
        ics.encode("utf-8"),
        maintype="text",
        subtype="calendar",
        filename="cita.ics",
    )

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(msg)


# ----------------- Notificación de cancelación -----------------

def enviar_correo_cancelacion(
    paciente: Dict[str, Any],
    datos_cita: Dict[str, Any],
    cfg_profesional: Dict[str, Any],
) -> None:
    """
    Envía un correo informando que la cita fue cancelada.
    - paciente: dict con 'nombre_completo', 'email'
    - datos_cita: dict con al menos 'fecha_hora' (YYYY-MM-DD HH:MM), 'modalidad', 'motivo'
    - cfg_profesional: configuración del profesional
    """
    email_paciente = (paciente.get("email") or "").strip()
    if not email_paciente:
        return

    smtp_user, smtp_password = _cargar_credenciales_gmail()

    if not (SMTP_HOST and smtp_user and smtp_password):
        raise ConfigSMTPIncompleta(
            "Faltan SARA_SMTP_HOST / SARA_SMTP_USER / SARA_SMTP_PASSWORD"
        )

    dt_inicio = datetime.strptime(datos_cita["fecha_hora"], "%Y-%m-%d %H:%M")
    dia_sem = DIAS_ES[dt_inicio.weekday()]
    mes_nom = MESES_ES[dt_inicio.month - 1]
    fecha_str_humano = f"{dia_sem.capitalize()} {dt_inicio.day:02d} de {mes_nom} de {dt_inicio.year}"
    hora_inicio_humano = dt_inicio.strftime("%I:%M %p").lstrip("0")

    nombre_prof = cfg_profesional.get("nombre_profesional") or "Tu profesional"
    email_prof = (cfg_profesional.get("email") or smtp_user or "").strip()

    # "Modalidad" en el correo debe reflejar el CANAL (presencial/virtual)
    canal_raw = (datos_cita.get("canal") or "").strip()

    canal_map = {
        "presencial": "Presencial",
        "virtual": "Virtual",
    }

    # Compatibilidad con modelos antiguos
    if not canal_raw:
        fallback = (datos_cita.get("modalidad") or "").strip()
        if fallback in canal_map:
            canal_raw = fallback

    modalidad = canal_map.get(canal_raw, "Presencial")

    motivo_raw = datos_cita.get("motivo") or ""
    motivo = motivo_raw.replace("Precio", "Valor")

    nombre_paciente = (paciente.get("nombre_completo") or "").strip() or "paciente"

    subject = f"Cancelada cita el {fecha_str_humano} a las {hora_inicio_humano}"

    body_text = (
        f"Hola {nombre_paciente},\n\n"
        f"Tu cita ha sido CANCELADA.\n\n"
        f"Profesional: {nombre_prof}\n"
        f"Modalidad: {modalidad}\n"
        f"Servicio / motivo: {motivo}\n"
        f"Fecha: {fecha_str_humano}\n"
        f"Hora: {hora_inicio_humano}\n\n"
        "Si necesitas reagendar una nueva cita, por favor ponte en contacto con nosotros.\n"
    )

    body_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background-color:#f5f5f5; padding:16px;">
        <div style="max-width:600px; margin:0 auto; background-color:#ffffff; border-radius:8px; overflow:hidden; box-shadow:0 2px 6px rgba(0,0,0,0.08);">
          <div style="background:linear-gradient(90deg,#f28b82,#e57373); padding:16px 20px; color:#ffffff; text-align:center;">
            <div style="font-size:18px; font-weight:bold;">{nombre_prof}</div>
            <div style="font-size:13px; opacity:0.9;">Psicología / Atención clínica</div>
          </div>
          <div style="padding:20px;">
            <p style="font-size:16px; font-weight:bold; margin:0 0 8px 0;">
              Hola {nombre_paciente},
            </p>
            <p style="margin:0 0 16px 0; font-size:14px;">
              Te informamos que tu cita ha sido <strong>cancelada</strong>.
            </p>

            <div style="display:inline-block; padding:4px 10px; border-radius:16px; background-color:#ffcdd2; color:#b71c1c; font-size:11px; font-weight:bold; margin-bottom:12px;">
              Cancelada
            </div>

            <table style="width:100%; font-size:14px; border-collapse:collapse;">
              <tr>
                <td style="padding:4px 0; width:120px; color:#555;"><strong>Fecha</strong></td>
                <td style="padding:4px 0;">{fecha_str_humano}</td>
              </tr>
              <tr>
                <td style="padding:4px 0; color:#555;"><strong>Hora</strong></td>
                <td style="padding:4px 0;">{hora_inicio_humano}</td>
              </tr>
              <tr>
                <td style="padding:4px 0; color:#555;"><strong>Modalidad</strong></td>
                <td style="padding:4px 0;">{modalidad}</td>
              </tr>
              <tr>
                <td style="padding:4px 0; color:#555;"><strong>Servicio / motivo</strong></td>
                <td style="padding:4px 0;">{motivo}</td>
              </tr>
            </table>

            <p style="margin-top:16px; font-size:13px;">
              Si necesitas reagendar una nueva cita, puedes ponerte en contacto con nosotros.
            </p>

            <p style="margin-top:16px; font-size:11px; color:#777;">
              Si no reconoces este correo, puedes ignorarlo.
            </p>
          </div>
        </div>
      </body>
    </html>
    """

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{nombre_prof} <{email_prof or smtp_user}>"
    msg["To"] = email_paciente

    msg.set_content(body_text)
    msg.add_alternative(body_html, subtype="html")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(msg)


#################################################
# =======ENVIO DE DOCUMENTOS/CERTIFICADOS=======#
#################################################

# ----------------- Envío de documentos (PDF adjunto) -----------------
from email.utils import formataddr
from mimetypes import guess_type

def _parse_recipients(raw: str) -> list[str]:
    """
    Acepta correos separados por ';' o ','.
    Retorna lista limpia, sin vacíos.
    """
    if not raw:
        return []
    parts = raw.replace(",", ";").split(";")
    emails = [p.strip() for p in parts if p.strip()]
    return emails


def enviar_correo_con_adjunto_pdf(
    to_emails: list[str],
    subject: str,
    body_text: str,
    body_html: str,
    pdf_path: str,
    cfg_profesional: Dict[str, Any],
) -> None:
    """
    Envía un correo con adjunto PDF usando configuración SMTP ya existente.
    """
    if not to_emails:
        return

    if not pdf_path or not os.path.exists(pdf_path):
        raise FileNotFoundError(f"No existe el adjunto: {pdf_path}")

    smtp_user, smtp_password = _cargar_credenciales_gmail()
    if not (SMTP_HOST and smtp_user and smtp_password):
        raise ConfigSMTPIncompleta("Faltan credenciales SMTP (Gmail).")

    nombre_prof = (cfg_profesional.get("nombre_profesional") or "Profesional").strip()
    email_from = (cfg_profesional.get("email") or smtp_user or "").strip()

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((nombre_prof, email_from))
    msg["To"] = "; ".join(to_emails)

    msg.set_content(body_text)
    msg.add_alternative(body_html, subtype="html")

    mime, _ = guess_type(pdf_path)
    maintype, subtype = ("application", "pdf")
    if mime and "/" in mime:
        maintype, subtype = mime.split("/", 1)

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    msg.add_attachment(
        pdf_bytes,
        maintype=maintype,
        subtype=subtype,
        filename=os.path.basename(pdf_path),
    )

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(msg)


def construir_email_consentimiento(
    nombre_paciente: str,
) -> tuple[str, str, str]:
    """
    Retorna (subject, body_text, body_html) para consentimiento.
    """
    subject = f"Consentimiento informado – {nombre_paciente}".strip(" –")

    body_text = (
        f"Buenas tardes {nombre_paciente},\n\n"
        "Adjunto encontrarás el consentimiento informado para el proceso de atención psicológica.\n"
        "Te agradezco leerlo con calma y, si estás de acuerdo, devolverlo firmado.\n\n"
        "Si tienes alguna pregunta, con gusto la resolvemos.\n\n"
        "Saludos cordiales."
    )

    body_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background:#f5f5f5; padding:16px;">
        <div style="max-width:640px; margin:0 auto; background:#fff; border-radius:10px; padding:18px 20px; box-shadow:0 2px 10px rgba(0,0,0,.06);">
          <p style="margin:0 0 12px 0;">Buenas tardes <b>{nombre_paciente}</b>,</p>
          <p style="margin:0 0 12px 0;">
            Adjunto encontrarás el <b>consentimiento informado</b> para el proceso de atención psicológica.
            Te agradezco leerlo con calma y, si estás de acuerdo, devolverlo firmado.
          </p>
          <p style="margin:0 0 12px 0;">Si tienes alguna pregunta, con gusto la resolvemos.</p>
          <p style="margin:0;">Saludos cordiales.</p>
          <hr style="border:none; border-top:1px solid #eee; margin:16px 0;" />
          <p style="font-size:11px; color:#777; margin:0;">
            Este mensaje y sus adjuntos pueden contener información confidencial. Si lo recibiste por error,
            por favor elimínalo e infórmanos.
          </p>
        </div>
      </body>
    </html>
    """
    return subject, body_text, body_html


def construir_email_certificado_asistencia(
    nombre_paciente: str,
    fecha_cita_humano: str,
) -> tuple[str, str, str]:
    """
    Retorna (subject, body_text, body_html) para certificado.
    fecha_cita_humano: texto tipo '27 de enero de 2025' o similar.
    """
    subject = f"Certificado de asistencia – {nombre_paciente}".strip(" –")

    body_text = (
        f"Buenas tardes,\n\n"
        f"Se adjunta el certificado de asistencia de {nombre_paciente}"
        + (f" correspondiente a la consulta del {fecha_cita_humano}.\n\n" if fecha_cita_humano else ".\n\n")
        + "Quedo atenta/o a cualquier inquietud.\n\n"
        "Saludos cordiales."
    )

    body_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background:#f5f5f5; padding:16px;">
        <div style="max-width:640px; margin:0 auto; background:#fff; border-radius:10px; padding:18px 20px; box-shadow:0 2px 10px rgba(0,0,0,.06);">
          <p style="margin:0 0 12px 0;">Buenas tardes,</p>
          <p style="margin:0 0 12px 0;">
            Se adjunta el <b>certificado de asistencia</b> de <b>{nombre_paciente}</b>
            {f"correspondiente a la consulta del <b>{fecha_cita_humano}</b>." if fecha_cita_humano else "."}
          </p>
          <p style="margin:0 0 12px 0;">Quedo atenta/o a cualquier inquietud.</p>
          <p style="margin:0;">Saludos cordiales.</p>

          <hr style="border:none; border-top:1px solid #eee; margin:16px 0;" />
          <p style="font-size:11px; color:#777; margin:0;">
            Este documento contiene información confidencial y es de uso exclusivo para fines relacionados con el proceso terapéutico.
            Se recomienda almacenarlo de forma segura y no modificar su contenido.
          </p>
        </div>
      </body>
    </html>
    """
    return subject, body_text, body_html

