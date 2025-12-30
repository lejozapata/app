# app/google_calendar_import.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
import re
import unicodedata
from difflib import SequenceMatcher

from .google_calendar import (
    get_calendar_service,
    list_events_range,
    parse_meta,
    TIMEZONE,
    hash_event,
    save_google_mapping,
)

from .db import crear_cita, listar_pacientes, listar_servicios  # ya existe listar_pacientes :contentReference[oaicite:3]{index=3}


# ------------------ Matching simple por nombre ------------------

def _norm(s: str) -> str:
    if not s:
        return ""

    s = s.strip().lower()

    # Normaliza caracteres raros (espacios invisibles, BOM, etc.)
    s = (
        s.replace("\u00a0", " ")
         .replace("\u200b", "")
         .replace("\ufeff", "")
         .replace("\u2060", "")
    )

    # Normalización Unicode
    s = unicodedata.normalize("NFKC", s)

    # Quitar acentos
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )

    # Limpiar símbolos
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    return s


STOP_TOKENS = {
    "cita", "sesion", "sesión", "psicologia", "psicóloga", "psicologa",
    "virtual", "presencial", "meet", "google", "calendar",
    "hora", "horas"
}


def _tokens(s: str) -> list[str]:
    s = _norm(s)
    return [t for t in s.split() if t and t not in STOP_TOKENS]


def _score_nombre(query: str, nombre: str) -> int:
    qn = _norm(query)
    nn = _norm(nombre)

    if not qn or not nn:
        return 0

    # Match perfecto
    if qn == nn:
        return 100

    qt = _tokens(qn)
    nt = _tokens(nn)

    # Subconjunto directo
    if qt and nt and (set(qt).issubset(set(nt)) or set(nt).issubset(set(qt))):
        return 100

    # Similaridad textual
    q_join = " ".join(qt)
    n_join = " ".join(nt)

    seq_score = int(round(SequenceMatcher(None, q_join, n_join).ratio() * 100))

    if qt and nt:
        inter = len(set(qt) & set(nt))
        union = len(set(qt) | set(nt))
        tok_score = int(round((inter / union) * 100))
    else:
        tok_score = 0

    return max(seq_score, tok_score)


def sugerir_pacientes_por_titulo(titulo_evento: str, top: int = 5):
    """
    Devuelve una lista de candidatos ordenados por score descendente.
    Cada item:
    {
        "documento": str,
        "nombre_completo": str,
        "score": int
    }
    """
    q = _norm(titulo_evento)
    if not q:
        return []

    pacientes = listar_pacientes()
    candidatos = []

    def _get_val(p, key, fallback):
        if isinstance(p, dict):
            return p.get(key)
        try:
            if hasattr(p, "keys") and key in p.keys():
                return p[key]
        except Exception:
            pass
        for i in fallback:
            try:
                return p[i]
            except Exception:
                continue
        return None

    for p in pacientes:
        nombre = _get_val(p, "nombre_completo", [2, 1])
        doc = _get_val(p, "documento", [0, 1])

        if not nombre or not doc:
            continue

        score = _score_nombre(q, nombre)
        if score > 0:
            candidatos.append({
                "documento": doc,
                "nombre_completo": nombre,
                "score": score
            })

    candidatos.sort(key=lambda x: x["score"], reverse=True)
    return candidatos[:top]

# ------------------ Parsing times from Google event ------------------

def _get_dt(ev: dict, key: str) -> Optional[datetime]:
    """
    Lee ev['start'/'end']['dateTime'] o ['date'].
    Ojo: para citas usamos dateTime; si viene date (all-day) no lo importamos.
    """
    block = ev.get(key) or {}
    dt_str = block.get("dateTime")
    if not dt_str:
        return None
    # Google retorna ISO con offset, ej 2025-12-29T10:00:00-05:00
    return datetime.fromisoformat(dt_str)

def _fmt_local(dt: datetime) -> str:
    # Guardamos como 'YYYY-MM-DD HH:MM'
    return dt.strftime("%Y-%m-%d %H:%M")


# ------------------ Import core ------------------

@dataclass
class ImportItem:
    event_id: str
    summary: str
    start_dt: datetime
    end_dt: datetime
    suggested: List[Dict[str, Any]]  # candidatos pacientes
    chosen_documento: Optional[str] = None


def detectar_candidatos_semana(calendar_id: str, dt_ini: datetime, dt_fin: datetime) -> List[ImportItem]:
    """
    Candidatos = eventos en rango SIN meta [SaraPsicologa] (es decir, creados manualmente).
    """
    eventos = list_events_range(calendar_id, dt_ini, dt_fin)
    items: List[ImportItem] = []

    for ev in eventos:
        desc = ev.get("description") or ""
        tipo, local_id = parse_meta(desc)
        if tipo or local_id is not None:
            continue  # ya es nuestro

        # ignorar all-day
        sdt = _get_dt(ev, "start")
        edt = _get_dt(ev, "end")
        if not sdt or not edt:
            continue

        summary = (ev.get("summary") or "").strip()
        if not summary:
            continue

        suggested = sugerir_pacientes_por_titulo(summary, top=5)

        items.append(
            ImportItem(
                event_id=ev["id"],
                summary=summary,
                start_dt=sdt,
                end_dt=edt,
                suggested=suggested,
            )
        )

    return items

def _event_times(ev: dict):
    """
    Devuelve (start_datetime, end_datetime) desde un evento de Google Calendar.
    Soporta eventos con dateTime o date (todo el día).
    """
    start = ev.get("start", {})
    end = ev.get("end", {})

    if "dateTime" in start:
        start_dt = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end["dateTime"].replace("Z", "+00:00"))
    else:
        # Evento de día completo
        start_dt = datetime.fromisoformat(start["date"])
        end_dt = datetime.fromisoformat(end["date"])

    return start_dt, end_dt

def _build_cita_dict(
    documento: str,
    start_dt: datetime,
    end_dt: datetime,
    servicio: Dict[str, Any],
    servicio_id: str,
    canal: str,
) -> Dict[str, Any]:
    nombre = str(servicio.get("nombre") or "").strip()
    try:
        precio_num = float(servicio.get("precio") or 0)
    except Exception:
        precio_num = 0.0

    # Mantener un formato consistente con la app (tu parser busca "Servicio:" y "Precio")
    motivo = f"Servicio: {nombre} - Precio: {int(precio_num)}"
    modalidad = str(servicio.get("modalidad") or "particular").strip().lower()

    try:
        precio = float(servicio.get("precio") or 0)
    except Exception:
        precio = 0.0

    canal = (canal or "presencial").strip().lower()
    if canal not in ("presencial", "virtual"):
        canal = "presencial"

    if modalidad not in ("particular", "convenio"):
        modalidad = "particular"

    # intenta llevarlo a int si tu DB lo maneja así
    try:
        servicio_id_val = int(str(servicio_id).strip())
    except Exception:
        servicio_id_val = str(servicio_id).strip()

    return {
        "documento_paciente": documento,
        "fecha_hora": _fmt_local(start_dt),
        "fecha_hora_fin": _fmt_local(end_dt),
        "modalidad": modalidad,

        # canal (y un alias defensivo por si tu DB usa otro nombre)
        "canal": canal,
        "canal_atencion": canal,

        # servicio (y alias defensivo)
        "servicio_id": servicio_id_val,
        "id_servicio": servicio_id_val,

        "motivo": motivo,
        "notas": "",
        "estado": "reservado",
        "precio": precio,
        "pagado": 0,
    }


def link_existing_event_to_cita(cita_id: int, calendar_id: str, event: dict) -> None:
    """
    Crea mapping local->google apuntando a un event existente (importado).
    """
    event_id = event["id"]
    color_id = event.get("colorId") or ""
    desc = event.get("description") or ""
    start_dt = (event.get("start") or {}).get("dateTime") or ""
    end_dt = (event.get("end") or {}).get("dateTime") or ""
    summary = event.get("summary") or ""

    last_hash = hash_event({
        "summary": summary,
        "description": desc,
        "start": start_dt,
        "end": end_dt,
        "colorId": color_id,
        "calendar_id": calendar_id,
    })

    save_google_mapping(
        cita_id=int(cita_id),
        calendar_id=calendar_id,
        event_id=event_id,
        last_hash=last_hash,
    )


def adopt_event_add_meta(calendar_id: str, event_id: str, cita_id: int) -> None:
    """
    Actualiza el evento para que quede marcado como de la app y no vuelva a salir en candidatos.
    Mantiene lo que ya escribió Sara (solo añade firma al final).
    """
    service = get_calendar_service()
    ev = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

    desc = ev.get("description") or ""
    # Añadimos un bloque separado y "discreto"
    firma = f"<br><br><i>[SaraPsicologa] tipo=cita local_id={int(cita_id)}</i>"

    if "[SaraPsicologa]" in desc:
        return  # ya está marcado

    ev["description"] = desc + firma

    service.events().update(
        calendarId=calendar_id,
        eventId=event_id,
        body=ev
    ).execute()


def importar_seleccionados(calendar_id: str, seleccionados: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Importa eventos existentes de Google Calendar hacia la BD local como citas.

    seleccionados: lista de dicts:
      {
        "event_id": "...",
        "documento_paciente": "...",
        "servicio_id": "...",          # requerido (id de servicios)
        "canal": "presencial|virtual"  # opcional (default presencial)
      }

    Retorna:
      {"importados": int, "fallos": int}
    """
    service = get_calendar_service()

    # Cargar servicios y mapear por id (string)
    servicios = listar_servicios(incluir_inactivos=False) or []
    srv_map: Dict[str, Dict[str, Any]] = {str(s.get("id")): s for s in servicios if s.get("id") is not None}

    ok = 0
    fail = 0

    for it in (seleccionados or []):
        try:
            # --------- Validación de entrada ----------
            event_id = str(it.get("event_id") or "").strip()
            documento = str(it.get("documento_paciente") or "").strip()

            # servicio_id viene desde el dialog (default)
            servicio_id = str(it.get("servicio_id") or "").strip()

            # canal viene desde el dialog (default)
            canal = str(it.get("canal") or "presencial").strip().lower()
            if canal not in ("presencial", "virtual"):
                canal = "presencial"

            if not event_id:
                raise ValueError("event_id vacío")
            if not documento:
                raise ValueError("documento_paciente vacío")
            if not servicio_id or servicio_id not in srv_map:
                raise ValueError(f"Servicio inválido: {servicio_id}")

            srv = srv_map[servicio_id]

            # --------- Leer evento Google ----------
            ev = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

            sdt = _get_dt(ev, "start")
            edt = _get_dt(ev, "end")
            if not sdt or not edt:
                raise ValueError("Evento sin dateTime (all-day o formato raro).")

            # --------- 1) Crear cita local COMPLETA ----------
            # _build_cita_dict debe:
            # - poner motivo/modalidad/precio desde srv (si aplica)
            # - poner canal según parámetro
            # - estado reservado/confirmado según tu estándar
            cita_dict = _build_cita_dict(documento, sdt, edt, srv, servicio_id, canal)
            cita_id = crear_cita(cita_dict)

            # --------- 2) Linkear evento existente a la cita (para futuras ediciones/sync) ----------
            # Si en tu implementación esto hace patch del evento o guarda mapping local,
            # perfecto. Si no existe, coméntalo, pero ideal mantenerlo.
            link_existing_event_to_cita(cita_id, calendar_id, ev)

            # --------- 3) Marcar/adoptar evento con meta (para no reimportarlo + PRUNE) ----------
            # Debe hacer PATCH description agregando:
            # [SaraPsicologa] tipo=cita local_id=<cita_id>
            adopt_event_add_meta(calendar_id, event_id, cita_id)

            ok += 1

        except Exception as ex:
            fail += 1
            print("⚠️ Error import Google->Local:", ex)

    return {"importados": ok, "fallos": fail}

# ================= UI (Flet) para revisar/importar =================
# Pégalo al FINAL del archivo google_calendar_import.py

import asyncio
import flet as ft

def mostrar_dialogo_revisar_import(
    page,
    calendar_id,
    candidatos,
    titulo="Importar desde Google Calendar",
    on_import_done: Optional[Callable[[], None]] = None,
):
    """
    Dialog para:
    - ver candidatos (eventos en Google sin metadata SaraPsicologa)
    - seleccionar eventos
    - asignar paciente (dropdown sugerencias o doc manual)
    - definir SERVICIO/CANAL por defecto (una sola vez, arriba)
    Luego importa creando la cita con esos valores y marca el evento en Google con metadata.
    """

    if not candidatos:
        page.snack_bar = ft.SnackBar(
            content=ft.Text("No encontré reservas en Google para importar."),
            bgcolor=ft.Colors.GREY_300,
            duration=2500,
        )
        page.snack_bar.open = True
        page.update()
        return

    # ----------------- Cargar servicios (para defaults) -----------------
    try:
        servicios = listar_servicios(incluir_inactivos=False)  # <- tu función existente
    except Exception:
        servicios = []

    # Mapa id->servicio
    serv_by_id: Dict[str, Dict[str, Any]] = {str(s.get("id")): s for s in (servicios or []) if s.get("id") is not None}

    opciones_serv = [ft.dropdown.Option(str(s["id"]), str(s.get("nombre") or "")) for s in (servicios or [])]
    opciones_canal = [
        ft.dropdown.Option("presencial", "Presencial"),
        ft.dropdown.Option("virtual", "Virtual"),
    ]

    dd_serv_default = ft.Dropdown(
        label="Servicio (default)",
        options=opciones_serv,
        value=(opciones_serv[0].key if opciones_serv else None),
        width=390,
        dense=True,
    )

    dd_canal_default = ft.Dropdown(
        label="Canal (default)",
        options=opciones_canal,
        value="presencial",
        width=390,
        dense=True,
    )

    # ----------------- Lista de tarjetas -----------------
    rows_container = ft.ListView(spacing=10, expand=True)

    ui_items: List[Dict[str, Any]] = []

    def _fmt_rango(it) -> str:
        try:
            ini = it.start_dt.strftime("%Y-%m-%d %H:%M")
            fin = it.end_dt.strftime("%H:%M")
            return f"{ini} - {fin}"
        except Exception:
            return ""

    for it in candidatos:
        chk = ft.Checkbox(value=False)

        # Dropdown sugerencias paciente
        opts = []
        for s in (it.suggested or []):
            label = f"{s.get('nombre_completo','')}  ({int(s.get('score',0))}%)"
            opts.append(ft.dropdown.Option(str(s.get("documento")), label))

        dd_paciente = ft.Dropdown(
            expand=True,
            options=opts,
            hint_text="Selecciona paciente (sugerencias)",
            dense=True,
        )

        # Autoselección si top score = 100
        if it.suggested:
            top = it.suggested[0]
            if int(top.get("score", 0)) >= 100:
                dd_paciente.value = str(top.get("documento"))
                chk.value = True

        txt_doc = ft.TextField(
            width=190,
            label="Documento (manual)",
            hint_text="Opcional",
            dense=True,
        )

        card = ft.Container(
            padding=12,
            border=ft.border.all(1, ft.Colors.GREY_300),
            border_radius=10,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            chk,
                            ft.Column(
                                [
                                    ft.Text(it.summary or "(Sin título)", weight="bold"),
                                    ft.Text(_fmt_rango(it), size=12, color=ft.Colors.GREY_700),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Row([dd_paciente, txt_doc], spacing=10),
                ],
                spacing=8,
            ),
        )

        rows_container.controls.append(card)

        ui_items.append(
            {
                "event_id": it.event_id,
                "chk": chk,
                "dd_paciente": dd_paciente,
                "txt_doc": txt_doc,
            }
        )

    status = ft.Text("", size=12, color=ft.Colors.GREY_700)

    # ----------------- Dialog + acciones -----------------
    dlg = ft.AlertDialog(modal=True)

    def cerrar_dialogo(e=None):
        dlg.open = False
        page.update()

    async def _ui_done_ok(msg: str, color):
        dlg.open = False

        # 🔥 refrescar vista (si el caller lo pasó)
        try:
            if on_import_done:
                on_import_done()
        except Exception as ex:
            print("⚠️ on_import_done falló:", ex)

        page.update()

        page.snack_bar = ft.SnackBar(
            content=ft.Text(msg),
            bgcolor=color,
            duration=4500,
        )
        page.snack_bar.open = True
        page.update()

    async def _ui_done_err(msg: str):
        status.value = msg
        btn_importar.disabled = False
        btn_cerrar.disabled = False
        page.update()

    def confirmar_import(e=None):
        # defaults (una sola vez)
        servicio_default_id = (dd_serv_default.value or "").strip()
        canal_default = (dd_canal_default.value or "").strip()

        if not servicio_default_id:
            status.value = "Selecciona un servicio (default)."
            page.update()
            return
        if canal_default not in ("presencial", "virtual"):
            status.value = "Selecciona un canal válido (default)."
            page.update()
            return

        seleccionados: List[Dict[str, Any]] = []

        for u in ui_items:
            if not bool(u["chk"].value):
                continue

            doc = (u["dd_paciente"].value or "").strip()
            if not doc:
                doc = (u["txt_doc"].value or "").strip()

            if not doc:
                continue

            seleccionados.append(
                {
                    "event_id": u["event_id"],
                    "documento_paciente": doc,
                    "servicio_id": servicio_default_id,  # <- aquí va el fix
                    "canal": canal_default,              # <- aquí va el fix
                }
            )

        if not seleccionados:
            status.value = "Selecciona al menos 1 evento y asigna un paciente."
            page.update()
            return

        btn_importar.disabled = True
        btn_cerrar.disabled = True
        status.value = "Importando..."
        page.update()

        def tarea_import():
            try:
                res = importar_seleccionados(calendar_id, seleccionados)
                ok = int(res.get("importados", 0))
                fail = int(res.get("fallos", 0))

                color = ft.Colors.GREEN_300 if fail == 0 else ft.Colors.AMBER_300

                async def _notify_ok():
                    await _ui_done_ok(f"📥 Import listo ✅  Importados: {ok} · Fallos: {fail}", color)

                page.run_task(_notify_ok)

            except Exception as ex:
                print("⚠️ Error import UI:", ex)

                async def _notify_err():
                    await _ui_done_err("⚠️ Error importando. Revisa consola.")

                page.run_task(_notify_err)

        page.run_thread(tarea_import)

    btn_importar = ft.ElevatedButton("Importar seleccionados", on_click=confirmar_import)
    btn_cerrar = ft.TextButton("Cerrar", on_click=cerrar_dialogo)

    dlg.title = ft.Text(titulo)
    dlg.content = ft.Container(
        width=820,
        height=520,
        content=ft.Column(
            [
                ft.Text(
                    "Detecté reservas en Google Calendar sin metadata de SaraPsicóloga.\n"
                    "Marca las que quieras traer a la app, asigna el paciente y define el servicio/canal.",
                    size=12,
                    color=ft.Colors.GREY_700,
                ),
                ft.Row([dd_serv_default, dd_canal_default], spacing=12),
                rows_container,
                status,
            ],
            spacing=10,
            tight=True,
            expand=True,
        ),
    )
    dlg.actions = [btn_cerrar, btn_importar]
    dlg.actions_alignment = ft.MainAxisAlignment.END

    page.open(dlg)
    dlg.open = True
    page.update()