# app/google_forms.py
import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# --------------------------------------------
# Config / Paths (mismo patrón que google_calendar.py)
# --------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

CREDENTIALS_FILE = os.path.join(DATA_DIR, "google_credentials.json")

# Token separado para NO afectar Calendar
TOKEN_FILE_FORMS = os.path.join(DATA_DIR, "google_token_forms.json")

# Scopes mínimos para leer Form + respuestas
SCOPES_FORMS = [
    "https://www.googleapis.com/auth/forms.body.readonly",
    "https://www.googleapis.com/auth/forms.responses.readonly",
]

STATE_FILE = os.path.join(DATA_DIR, "google_forms_state.json")


def _load_state() -> Dict[str, Any]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}
    return {}


def _save_state(state: Dict[str, Any]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        
def reset_forms_sync_state():
    # borra el state (processed_response_ids)
    _save_state({"processed_response_ids": []})


def get_forms_service():
    """Crea cliente autenticado de Google Forms API."""
    creds = None

    if os.path.exists(TOKEN_FILE_FORMS):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE_FORMS, SCOPES_FORMS)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES_FORMS)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE_FORMS, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return build("forms", "v1", credentials=creds, cache_discovery=False)


def _norm(s: str) -> str:
    # normalización básica para comparar títulos de preguntas
    return " ".join((s or "").strip().lower().split())


def get_form_question_map(form_id: str) -> Dict[str, str]:
    """
    Retorna mapping: question_id -> title
    (En Forms API, las respuestas vienen por questionId.)
    """
    service = get_forms_service()
    form = service.forms().get(formId=form_id).execute()

    qmap: Dict[str, str] = {}
    items = (form.get("items") or [])
    for it in items:
        qitem = it.get("questionItem")
        if not qitem:
            continue
        question = qitem.get("question") or {}
        qid = question.get("questionId")
        title = it.get("title") or ""
        if qid:
            qmap[qid] = title
    return qmap


def list_form_responses(form_id: str, page_size: int = 200) -> List[Dict[str, Any]]:
    """Lista respuestas del formulario (paginado)."""
    service = get_forms_service()
    out: List[Dict[str, Any]] = []

    page_token = None
    while True:
        resp = (
            service.forms()
            .responses()
            .list(formId=form_id, pageSize=page_size, pageToken=page_token)
            .execute()
        )
        out.extend(resp.get("responses") or [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return out


def extract_answers_by_title(response: Dict[str, Any], qmap: Dict[str, str]) -> Dict[str, str]:
    """
    Convierte una response a: { "titulo_pregunta_normalizado": "valor" }

    Soporta:
    - textAnswers  (respuesta corta/larga)
    - choiceAnswers (opción múltiple / dropdown)
    - dateAnswers  (fecha)
    """
    answers = response.get("answers") or {}
    out: Dict[str, str] = {}

    for qid, ans in answers.items():
        title = qmap.get(qid) or qid
        key = _norm(title)

        value = ""

        # 1) Texto
        txt = ((ans.get("textAnswers") or {}).get("answers") or [])
        if txt:
            value = (txt[0].get("value") or "").strip()

        # 2) Choice (radio / dropdown)
        if not value:
            ch = ((ans.get("choiceAnswers") or {}).get("answers") or [])
            if ch:
                # puede venir lista (selección múltiple)
                vals = [(x.get("value") or "").strip() for x in ch if (x.get("value") or "").strip()]
                value = ", ".join(vals)

        # 3) Fecha (dateAnswers)
        if not value:
            dt = ((ans.get("dateAnswers") or {}).get("answers") or [])
            if dt:
                d = dt[0] or {}
                # Form API suele dar year/month/day
                y = d.get("year")
                m = d.get("month")
                day = d.get("day")
                if y and m and day:
                    value = f"{int(y):04d}-{int(m):02d}-{int(day):02d}"

        if value:
            out[key] = value

    return out


def sync_responses_manual(
    form_id: str,
    process_row_fn,  # callback: (answers_dict, response_raw) -> ("inserted"|"updated"|"skipped", msg)
) -> Tuple[int, int, int, List[str]]:
    """
    Sincroniza manualmente:
    - solo procesa responses nuevas (por responseId) usando STATE_FILE
    - devuelve (insertados, actualizados, omitidos, mensajes)
    """
    state = _load_state()
    processed = set((state.get("processed_response_ids") or []))

    qmap = get_form_question_map(form_id)
    responses = list_form_responses(form_id)

    inserted = 0
    updated = 0
    skipped = 0
    messages: List[str] = []

    for r in responses:
        rid = r.get("responseId")
        if not rid:
            continue
        if rid in processed:
            continue

        ans = extract_answers_by_title(r, qmap)

        action, msg = process_row_fn(ans, r)
        if action == "inserted":
            inserted += 1
        elif action == "updated":
            updated += 1
        else:
            skipped += 1

        processed.add(rid)
        if msg:
            messages.append(msg)

    state["processed_response_ids"] = sorted(processed)
    state["last_sync_utc"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)

    return inserted, updated, skipped, messages
# Fin de google_forms.py

def debug_dump_latest_response(form_id: str, out_json_path: str = None) -> dict:
    """
    - Trae 1 respuesta (la más reciente que retorne la API).
    - Construye:
        - raw_response (tal cual)
        - question_map (questionId -> title)
        - answers_by_title (titulo_normalizado -> valor)
    - Opcional: lo guarda en un JSON para inspeccionarlo.
    """
    qmap = get_form_question_map(form_id)
    responses = list_form_responses(form_id, page_size=50)

    if not responses:
        payload = {"ok": False, "error": "No hay respuestas en el formulario."}
        if out_json_path:
            os.makedirs(os.path.dirname(out_json_path), exist_ok=True)
            with open(out_json_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        return payload

    raw = responses[-1]  # última del listado (en práctica suele ser la más reciente)
    ans = extract_answers_by_title(raw, qmap)

    payload = {
        "ok": True,
        "responseId": raw.get("responseId"),
        "createTime": raw.get("createTime"),
        "lastSubmittedTime": raw.get("lastSubmittedTime"),
        "answers_by_title": ans,
        "question_map_sample": dict(list(qmap.items())[:10]),
        "raw_response": raw,
    }

    if out_json_path:
        os.makedirs(os.path.dirname(out_json_path), exist_ok=True)
        with open(out_json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    return payload