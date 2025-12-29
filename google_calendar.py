import os
import sqlite3
import hashlib
from datetime import datetime, timezone, timedelta
import pytz
import re

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# ================= META PARSER =================

META_RE = re.compile(r"\[SaraPsicologa\]\s+tipo=(cita|bloqueo)\s+local_id=(\d+)")

def parse_meta(description: str):
    """
    Devuelve (tipo, local_id) si encuentra la firma.
    Soporta HTML y texto mezclado.
    """
    if not description:
        return (None, None)
    m = META_RE.search(description)
    if not m:
        return (None, None)
    return (m.group(1), int(m.group(2)))

TZ_CO = timezone(timedelta(hours=-5))

def _rfc3339_local(dt: datetime) -> str:
    # Si viene naive, asumimos hora local (Colombia)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ_CO)
    # Google odia microsegundos
    dt = dt.replace(microsecond=0)
    return dt.isoformat()  # queda ...-05:00

def list_events_range(calendar_id: str, dt_ini: datetime, dt_fin: datetime) -> list[dict]:
    service = get_calendar_service()
    resp = service.events().list(
        calendarId=calendar_id,
        timeMin=_rfc3339_local(dt_ini),
        timeMax=_rfc3339_local(dt_fin),
        singleEvents=True,
        orderBy="startTime",
        maxResults=2500,
    ).execute()
    return resp.get("items", [])

def delete_event_by_id(calendar_id: str, event_id: str) -> None:
    service = get_calendar_service()
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    except Exception as e:
        # Si ya no existe en Google, lo tratamos como OK
        s = str(e)
        if "404" in s or "notFound" in s:
            return
        raise

# ================= CONFIG =================

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TIMEZONE = "America/Bogota"

# Este archivo está en: E:\SaraPsicologa\app\google_calendar.py
# DATA_DIR debe ser: E:\SaraPsicologa\data
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

CREDENTIALS_FILE = os.path.join(DATA_DIR, "google_credentials.json")
TOKEN_FILE = os.path.join(DATA_DIR, "google_token.json")

APP_TAG = "[SaraPsicologa]"

# ================= COLORES =================
# https://developers.google.com/calendar/api/v3/reference/colors
GOOGLE_COLOR_BY_ESTADO = {
    "reservado": "7",     # azul
    "confirmado": "5",    # amarillo
    "no_asistio": "11",   # rojo
    "bloqueo": "8",       # gris
}

# ================= DB =================

def get_db_connection():
    return sqlite3.connect(
        os.path.join(DATA_DIR, "sara_psico.db"),
        detect_types=sqlite3.PARSE_DECLTYPES,
    )

# ================= AUTH =================

def get_calendar_service():
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES
            )
            # En Windows abre browser y usa callback localhost
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)

# ================= UTIL =================

def hash_event(data: dict) -> str:
    # Hash estable (orden de claves fijo por cómo lo construimos)
    raw = "|".join(str(v) for v in data.values())
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def get_google_mapping(cita_id: int):
    """
    Retorna tuple (event_id, last_hash) o None
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT event_id, last_hash
        FROM google_calendar_sync
        WHERE cita_id = ?;
        """,
        (cita_id,),
    )

    row = cur.fetchone()
    conn.close()
    return row

def save_google_mapping(cita_id: int, calendar_id: str, event_id: str, last_hash: str):
    """
    Upsert por cita_id (requiere cita_id PRIMARY KEY o UNIQUE)
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO google_calendar_sync (cita_id, calendar_id, event_id, last_hash)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(cita_id) DO UPDATE SET
            calendar_id = excluded.calendar_id,
            event_id = excluded.event_id,
            last_hash = excluded.last_hash,
            synced_at = datetime('now','localtime');
        """,
        (cita_id, calendar_id, event_id, last_hash),
    )

    conn.commit()
    conn.close()

def delete_google_mapping(cita_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM google_calendar_sync WHERE cita_id = ?;",
        (cita_id,),
    )
    conn.commit()
    conn.close()

# ================= SYNC CITAS =================

def sync_cita_to_google(cita: dict, calendar_id: str):
    """
    Crea o actualiza una cita en Google Calendar y guarda event_id en google_calendar_sync.

    Requiere en 'cita':
      - id
      - fecha_hora (YYYY-MM-DD HH:MM)
      - fecha_hora_fin (YYYY-MM-DD HH:MM)
      - nombre_completo (ideal)
      - motivo (opcional)
      - estado (reservado/confirmado/no_asistio)
    """
    service = get_calendar_service()
    tz = pytz.timezone(TIMEZONE)

    cita_id = int(cita["id"])

    # --- Parse fechas ---
    dt_inicio = datetime.strptime(str(cita["fecha_hora"])[:16], "%Y-%m-%d %H:%M")
    dt_fin = datetime.strptime(str(cita["fecha_hora_fin"])[:16], "%Y-%m-%d %H:%M")

    dt_inicio = tz.localize(dt_inicio)
    dt_fin = tz.localize(dt_fin)

    if dt_fin <= dt_inicio:
        raise ValueError("La fecha fin debe ser mayor que la fecha inicio")

    # --- Construir texto ---
    nombre = (cita.get("nombre_completo") or "Paciente").strip()
    motivo = (cita.get("motivo") or "").strip()
    estado = (cita.get("estado") or "reservado").strip()
    canal = (cita.get("canal") or "").strip()

    summary = f"{nombre}"

    meta_line = f"{APP_TAG} tipo=cita local_id={cita_id}"
    meta_html = f"<br><br><small><i>{meta_line}</i></small>"

    desc_html = ""
    if motivo:
        desc_html += f"<b>Motivo:</b> {motivo}<br>"
    if canal:
        desc_html += f"<b>Canal:</b> {canal}"

    description = (desc_html + meta_html).strip()

    event_body = {
        "summary": summary,
        "description": (
            f"{description}\n"
        ),
        "start": {
            "dateTime": dt_inicio.isoformat(),
            "timeZone": TIMEZONE,
        },
        "end": {
            "dateTime": dt_fin.isoformat(),
            "timeZone": TIMEZONE,
        },
        "colorId": GOOGLE_COLOR_BY_ESTADO.get(estado, GOOGLE_COLOR_BY_ESTADO["reservado"]),
    }

    new_hash = hash_event({
        # hash basado en campos que definen el evento
        "summary": event_body["summary"],
        "description": event_body["description"],
        "start": event_body["start"]["dateTime"],
        "end": event_body["end"]["dateTime"],
        "colorId": event_body["colorId"],
        "calendar_id": calendar_id,
    })

    mapping = get_google_mapping(cita_id)

    # =========================
    # UPDATE BRANCH (EXACTO AQUÍ)
    # =========================
    if mapping:
        event_id, last_hash = mapping

        # Si no cambió nada, no llamamos a Google
        if last_hash == new_hash:
            return

        service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=event_body,
        ).execute()

        # Guardamos hash nuevo (event_id se mantiene)
        save_google_mapping(
            cita_id=cita_id,
            calendar_id=calendar_id,
            event_id=event_id,
            last_hash=new_hash,
        )
        return

    # =========================
    # INSERT BRANCH (crear evento)
    # =========================
    created = service.events().insert(
        calendarId=calendar_id,
        body=event_body
    ).execute()

    event_id = created.get("id")
    if not event_id:
        raise RuntimeError("Google Calendar no retornó event.id al crear el evento.")

    save_google_mapping(
        cita_id=cita_id,
        calendar_id=calendar_id,
        event_id=event_id,
        last_hash=new_hash,
    )

# ================= DELETE =================

def delete_cita_from_google(cita_id: int, calendar_id: str):
    """
    Borra evento en Google (si existe mapping) y luego elimina mapping local.
    """
    mapping = get_google_mapping(int(cita_id))
    if not mapping:
        return

    event_id, _ = mapping
    service = get_calendar_service()

    try:
        service.events().delete(
            calendarId=calendar_id,
            eventId=event_id,
        ).execute()
    finally:
        delete_google_mapping(int(cita_id))
        
        
        
# ================= SYNC BLOQUEOS =================

def get_bloqueo_mapping(bloqueo_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT event_id, last_hash
        FROM google_calendar_sync_bloqueos
        WHERE bloqueo_id = ?;
        """,
        (bloqueo_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row


def save_bloqueo_mapping(bloqueo_id: int, calendar_id: str, event_id: str, last_hash: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO google_calendar_sync_bloqueos (bloqueo_id, calendar_id, event_id, last_hash)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(bloqueo_id) DO UPDATE SET
            calendar_id = excluded.calendar_id,
            event_id = excluded.event_id,
            last_hash = excluded.last_hash,
            synced_at = datetime('now','localtime');
        """,
        (bloqueo_id, calendar_id, event_id, last_hash),
    )
    conn.commit()
    conn.close()


def delete_bloqueo_mapping(bloqueo_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM google_calendar_sync_bloqueos WHERE bloqueo_id = ?;", (bloqueo_id,))
    conn.commit()
    conn.close()


def sync_bloqueo_to_google(bloqueo: dict, calendar_id: str):
    """
    Bloqueo:
      - id
      - motivo
      - fecha_hora_inicio (YYYY-MM-DD HH:MM)
      - fecha_hora_fin (YYYY-MM-DD HH:MM)
    """
    service = get_calendar_service()
    tz = pytz.timezone(TIMEZONE)

    bloqueo_id = int(bloqueo["id"])

    dt_inicio = datetime.strptime(str(bloqueo["fecha_hora_inicio"])[:16], "%Y-%m-%d %H:%M")
    dt_fin = datetime.strptime(str(bloqueo["fecha_hora_fin"])[:16], "%Y-%m-%d %H:%M")
    dt_inicio = tz.localize(dt_inicio)
    dt_fin = tz.localize(dt_fin)

    if dt_fin <= dt_inicio:
        raise ValueError("Bloqueo: fecha fin debe ser mayor a inicio")

    motivo = (bloqueo.get("motivo") or "Bloqueo").strip()
    summary = f"{motivo}"
    meta_line = f"{APP_TAG} tipo=bloqueo local_id={bloqueo_id}"
    meta_html = f"<br><br><small><i>{meta_line}</i></small>"

    description = (motivo or "").strip() + meta_html

    event_body = {
        "summary": summary,
        "description": f"{description}\n",
        "start": {"dateTime": dt_inicio.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": dt_fin.isoformat(), "timeZone": TIMEZONE},
        "colorId": GOOGLE_COLOR_BY_ESTADO.get("bloqueo", "8"),
    }

    new_hash = hash_event({
        "summary": event_body["summary"],
        "description": event_body["description"],
        "start": event_body["start"]["dateTime"],
        "end": event_body["end"]["dateTime"],
        "colorId": event_body["colorId"],
        "calendar_id": calendar_id,
    })

    mapping = get_bloqueo_mapping(bloqueo_id)

    # UPDATE
    if mapping:
        event_id, last_hash = mapping
        if last_hash == new_hash:
            return

        service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=event_body,
        ).execute()

        save_bloqueo_mapping(bloqueo_id, calendar_id, event_id, new_hash)
        return

    # INSERT
    created = service.events().insert(calendarId=calendar_id, body=event_body).execute()
    event_id = created.get("id")
    if not event_id:
        raise RuntimeError("Google Calendar no retornó event.id al crear bloqueo.")

    save_bloqueo_mapping(bloqueo_id, calendar_id, event_id, new_hash)


def delete_bloqueo_from_google(bloqueo_id: int, calendar_id: str):
    mapping = get_bloqueo_mapping(int(bloqueo_id))
    if not mapping:
        return

    event_id, _ = mapping
    service = get_calendar_service()

    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    finally:
        delete_bloqueo_mapping(int(bloqueo_id))
        
        
        
# ================= END =================