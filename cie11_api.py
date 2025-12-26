# cie11_api.py
from __future__ import annotations

import os
import time
import requests
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"
API_BASE = "https://id.who.int"

DEFAULT_RELEASE_ID = os.getenv("ICD11_RELEASE_ID", "2025-01")
DEFAULT_LINEARIZATION = "mms"


@dataclass
class ICD11Entity:
    uri: str
    code: Optional[str]
    title: str
    description: Optional[str] = None


def _load_cie11_config_from_db() -> Tuple[Optional[str], Optional[str], Optional[str], bool]:
    """
    Carga (release, client_id, client_secret_plain, habilitado) desde SQLite.

    Requiere que en db.py existan:
      - get_connection()
      - (opcional) obtener_configuracion_cie11()
    y en crypto_utils.py:
      - decrypt_str()
    """
    try:
        # Import lazy para no romper si se ejecuta como script suelto
        from .db import get_connection  # type: ignore
    except Exception:
        # Si alguien ejecuta fuera de paquete, intenta import absoluto
        try:
            from .db import get_connection  # type: ignore
        except Exception:
            return None, None, None, False

    # Intento 1: si ya creaste obtener_configuracion_cie11(), úsalo.
    try:
        from .db import obtener_configuracion_cie11  # type: ignore

        cfg = obtener_configuracion_cie11()
        # cfg normalmente NO trae el secret plano (por seguridad), así que en ese caso leemos directo tabla.
        habilitado = bool(cfg.get("habilitado"))
        release = cfg.get("release")
        client_id = cfg.get("client_id")
    except Exception:
        habilitado = False
        release = None
        client_id = None

    # Leer secret cifrado directamente de tabla (porque tu getter suele omitirlo)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT release, client_id, client_secret, habilitado
        FROM configuracion_cie11
        WHERE id = 1
        """
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None, None, None, False

    release_db, client_id_db, secret_enc, habilitado_db = row
    release = release_db or release
    client_id = client_id_db or client_id
    habilitado = bool(habilitado_db)

    if not secret_enc:
        return release, client_id, None, habilitado

    # Desencriptar (tu encrypt_str guarda prefijo "enc::..." normalmente)
    secret_plain = None
    try:
        from .crypto_utils import decrypt_str  # type: ignore

        secret_plain = decrypt_str(secret_enc)
    except Exception:
        try:
            from .crypto_utils import decrypt_str  # type: ignore

            secret_plain = decrypt_str(secret_enc)
        except Exception:
            secret_plain = None

    return release, client_id, secret_plain, habilitado


class CIE11Client:
    """
    Cliente ICD-11 MMS (ICD-API v2).

    Si NO se pasan credenciales en __init__, se intentan cargar desde BD
    (tabla configuracion_cie11) y se desencripta el secret.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        language: str = "es",
        release_id: Optional[str] = None,
        linearization: str = DEFAULT_LINEARIZATION,
        timeout: int = 20,
        require_enabled: bool = True,
    ):
        # 1) Primero intenta usar lo que venga explícito
        self.language = language
        self.linearization = linearization
        self.timeout = timeout

        # 2) Si faltan datos, carga desde BD
        if not (client_id and client_secret and release_id):
            db_release, db_client_id, db_client_secret, enabled = _load_cie11_config_from_db()

            if require_enabled and not enabled:
                raise ValueError(
                    "CIE-11 no está habilitado en Configuración (admin_view)."
                )

            release_id = release_id or db_release or DEFAULT_RELEASE_ID
            client_id = client_id or db_client_id
            client_secret = client_secret or db_client_secret

        self.release_id = release_id or DEFAULT_RELEASE_ID
        self.client_id = client_id
        self.client_secret = client_secret

        if not self.client_id or not self.client_secret:
            raise ValueError(
                "Faltan credenciales de CIE-11. Configúralas en Admin o pásalas al constructor."
            )

        self._token: Optional[str] = None
        self._token_exp: float = 0.0

    def _get_token(self) -> str:
        now = time.time()
        if self._token and now < (self._token_exp - 30):
            return self._token

        r = requests.post(
            TOKEN_URL,
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "client_credentials", "scope": "icdapi_access"},
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        self._token = data["access_token"]
        self._token_exp = now + int(data.get("expires_in", 3600))
        return self._token

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Accept": "application/json",
            "Accept-Language": self.language,
            "API-Version": "v2",
        }

    def _release_base(self) -> str:
        return f"{API_BASE}/icd/release/11/{self.release_id}/{self.linearization}"

    def get_entity(self, uri: str) -> ICD11Entity:
        if uri.startswith("http://"):
            uri = "https://" + uri[len("http://"):]
        r = requests.get(uri, headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        data = r.json()

        title = (data.get("title") or {}).get("@value") or "-"
        desc = (data.get("definition") or {}).get("@value")
        code = data.get("code")
        return ICD11Entity(uri=uri, code=code, title=title, description=desc)

    def get_chapters(self) -> List[ICD11Entity]:
        url = f"{self._release_base()}"
        r = requests.get(url, headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        data = r.json()

        out: List[ICD11Entity] = []
        for item in data.get("child", []):
            out.append(self.get_entity(item))
        return out

    def get_children(self, uri: str) -> List[ICD11Entity]:
        ent = self.get_entity(uri)
        r = requests.get(ent.uri, headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        data = r.json()

        out: List[ICD11Entity] = []
        for child_uri in data.get("child", []) or []:
            out.append(self.get_entity(child_uri))
        return out

    def search(self, q: str, limit: int = 50) -> List[ICD11Entity]:
        url = f"{self._release_base()}/search"
        r = requests.get(
            url,
            headers=self._headers(),
            params={"q": q},
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()

        out: List[ICD11Entity] = []
        for it in data.get("destinationEntities", []) or []:
            uri = it.get("id")
            title = it.get("title")
            code = it.get("theCode") or it.get("code")
            if isinstance(title, dict):
                title = title.get("@value")
            out.append(ICD11Entity(uri=uri, code=code, title=title or "-"))
        return out[:limit]

    def lookup_code(self, code: str) -> Optional["ICD11Entity"]:
        """
        Lookup exacto por código (ej: MB28.A, 6A70.3).
        Usa endpoint codeinfo (API v2) y luego resuelve la entidad para obtener título/definición.

        Retorna ICD11Entity o None si no existe.
        """
        code = (code or "").strip().upper()
        if not code:
            return None

        url = f"{self._release_base()}/codeinfo/{quote(code, safe='')}"
        try:
            r = requests.get(url, headers=self._headers(), timeout=self.timeout)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data = r.json()
        except requests.RequestException:
            return None

        # En codeinfo normalmente viene el stemId (URI de la entidad en la linearización)
        stem_uri = (
            data.get("stemId")
            or data.get("stemURI")
            or data.get("stemUri")
            or data.get("entityId")
            or data.get("id")
        )

        # Si tenemos URI, traemos el detalle para obtener título en español
        if isinstance(stem_uri, str) and stem_uri:
            ent = self.get_entity(stem_uri)
            # Mantén el código exacto que pidió el usuario (a veces codeinfo normaliza)
            ent.code = code
            return ent

        # Fallback: si no hay URI, intenta construir un título desde codeinfo
        title = None
        t = data.get("title")
        if isinstance(t, dict):
            title = t.get("@value")
        elif isinstance(t, str):
            title = t

        if not title:
            title = f"Código {code}"

        return ICD11Entity(uri=url, code=code, title=title, description=None)

