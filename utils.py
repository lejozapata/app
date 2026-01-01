from datetime import datetime
import re

def form_date_to_ddmmyyyy(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%d-%m-%Y")
    except Exception:
        return s  # fallback

def normalize_doc(s: str) -> str:
    return (s or "").strip().upper()

def normalize_phone_co(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    # dejar solo dígitos y '+'
    s2 = "".join(ch for ch in s if ch.isdigit() or ch == "+")
    if not s2:
        return ""
    if s2.startswith("+"):
        return s2
    # si viene como 57XXXXXXXXXX
    if s2.startswith("57") and len(s2) >= 10:
        return "+" + s2
    # default Colombia
    return "+57" + s2

def map_tipo_documento(form_value: str) -> str:
    v = (form_value or "").strip().upper()

    # Caso ideal: viene con (CC), (TI), etc.
    for code in ["CC", "TI", "CE"]:
        if f"({code})" in v:
            return code

    # Casos por texto
    if "PASAPORTE" in v:
        return "PASAPORTE"
    if "CÉDULA" in v or "CEDULA" in v:
        # si por alguna razón no trae el (CC)/(CE)
        if "EXTRANJER" in v:
            return "CE"
        return "CC"
    if "TARJETA" in v and "IDENT" in v:
        return "TI"
    if "OTRO" in v:
        return "OTRO"

    # fallback
    return v


def normalize_phone_for_db_colombia(raw: str) -> tuple[str, str]:
    """
    Devuelve (indicativo_pais, telefono_local)
    - indicativo_pais: '+57'
    - telefono_local: 10 dígitos (ej: '3103868947')
    """
    s = (raw or "").strip()
    if not s:
        return "", ""

    digits = "".join(ch for ch in s if ch.isdigit())

    # Si viene con 57 al inicio (con o sin +), lo removemos
    if digits.startswith("57") and len(digits) > 10:
        digits = digits[2:]

    # si aún viene más largo, nos quedamos con los últimos 10 (por seguridad)
    if len(digits) > 10:
        digits = digits[-10:]

    return "57", digits

def consent_ok(ans: dict) -> bool:
    val = (ans.get("consentimiento datos personales") or "").strip().lower()
    # acepta "sí", "si" al inicio
    return val.startswith("sí") or val.startswith("si")

