from __future__ import annotations

from pathlib import Path
import os

try:
    from cryptography.fernet import Fernet, InvalidToken  # type: ignore
except Exception:  # pragma: no cover
    Fernet = None  # type: ignore
    InvalidToken = Exception  # type: ignore

_ENC_PREFIX = "enc::"


def _data_dir() -> Path:
    base_dir = Path(__file__).resolve().parents[1]
    data_dir = base_dir / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir


def _key_path() -> Path:
    return _data_dir() / ".secret.key"


def get_or_create_key() -> bytes:
    if Fernet is None:
        raise RuntimeError("Falta dependencia 'cryptography'. Instala con: pip install cryptography")

    kp = _key_path()
    if kp.is_file():
        k = kp.read_bytes().strip()
        if k:
            return k

    k = Fernet.generate_key()
    try:
        kp.write_bytes(k)
    except Exception:
        env_k = os.getenv("SARA_SECRET_KEY")
        if env_k:
            return env_k.encode("utf-8")
        raise
    return k


def is_encrypted(value: str | None) -> bool:
    return bool(value) and str(value).startswith(_ENC_PREFIX)


def encrypt_str(plain: str) -> str:
    if Fernet is None:
        raise RuntimeError("Falta dependencia 'cryptography'. Instala con: pip install cryptography")
    f = Fernet(get_or_create_key())
    token = f.encrypt(plain.encode("utf-8")).decode("utf-8")
    return _ENC_PREFIX + token


def decrypt_str(value: str) -> str:
    if not value:
        return ""
    if not is_encrypted(value):
        return value

    if Fernet is None:
        raise RuntimeError("Falta dependencia 'cryptography'. Instala con: pip install cryptography")

    token = value[len(_ENC_PREFIX):]
    f = Fernet(get_or_create_key())
    try:
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise RuntimeError("No se pudo descifrar la clave guardada (key inválida o dato corrupto).")
