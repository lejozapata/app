# backup_utils.py
import glob
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .db import DB_PATH


BACKUP_PREFIX = "sarapsicologa_db_"
PRE_RESTORE_PREFIX = "pre_restore_db_"

BACKUP_GLOB_DB = f"{BACKUP_PREFIX}*.db"
BACKUP_GLOB_ZIP = f"{BACKUP_PREFIX}*.zip"

PRE_GLOB_DB = f"{PRE_RESTORE_PREFIX}*.db"
PRE_GLOB_ZIP = f"{PRE_RESTORE_PREFIX}*.zip"


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _ensure_dir(path: str) -> None:
    if not path:
        raise ValueError("Ruta vacía.")
    os.makedirs(path, exist_ok=True)


def _write_last_backup_meta(backup_dir: str, method: str, created_path: str) -> None:
    """
    Guarda metadata simple en backup_dir/last_backup.json.
    method: "native" | "windows" | "manual" | "restore_pre" | etc.
    """
    try:
        meta_path = os.path.join(backup_dir, "last_backup.json")
        payload = {
            "method": method,
            "path": created_path,
            "filename": os.path.basename(created_path),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        # No debe romper el backup por un meta
        pass


def backup_database(backup_dir: str, zip_backup: bool = True, method: str = "manual") -> str:
    """
    Crea un backup de DB_PATH en backup_dir.
    - Si zip_backup=True crea .zip (recomendado)
    - Si zip_backup=False deja .db
    Retorna el path del archivo creado.
    """
    _ensure_dir(backup_dir)

    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"No existe DB en: {DB_PATH}")

    base_name = f"{BACKUP_PREFIX}{_ts()}"
    dst_db = os.path.join(backup_dir, base_name + ".db")

    # Copia simple
    shutil.copy2(DB_PATH, dst_db)

    if not zip_backup:
        _write_last_backup_meta(backup_dir, method=method, created_path=dst_db)
        return dst_db

    dst_zip = os.path.join(backup_dir, base_name + ".zip")
    with zipfile.ZipFile(dst_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.write(dst_db, arcname=os.path.basename(dst_db))

    try:
        os.remove(dst_db)
    except Exception:
        pass

    _write_last_backup_meta(backup_dir, method=method, created_path=dst_zip)
    return dst_zip


def list_backups(backup_dir: str) -> List[Dict]:
    """
    Lista backups .db y .zip en backup_dir, ordenados por más reciente.
    Retorna: [{name, path, mtime, size_bytes}]
    """
    if not backup_dir or not os.path.isdir(backup_dir):
        return []

    paths: List[str] = []
    paths.extend(glob.glob(os.path.join(backup_dir, BACKUP_GLOB_DB)))
    paths.extend(glob.glob(os.path.join(backup_dir, BACKUP_GLOB_ZIP)))
    
    paths.extend(glob.glob(os.path.join(backup_dir, PRE_GLOB_DB)))
    paths.extend(glob.glob(os.path.join(backup_dir, PRE_GLOB_ZIP)))

    items: List[Dict] = []
    for p in paths:
        try:
            st = os.stat(p)
            items.append(
                {
                    "name": os.path.basename(p),
                    "path": p,
                    "mtime": st.st_mtime,
                    "size_bytes": st.st_size,
                }
            )
        except Exception:
            continue

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def _make_pre_restore_backup(backup_dir: str, zip_backup: bool = True) -> str:
    """
    Crea un respaldo "pre_restore" del estado actual de DB_PATH antes de restaurar.
    Se guarda en backup_dir.
    """
    _ensure_dir(backup_dir)

    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"No existe DB actual en: {DB_PATH}")

    ts = _ts()
    pre_db = os.path.join(backup_dir, f"{PRE_RESTORE_PREFIX}{ts}.db")
    shutil.copy2(DB_PATH, pre_db)

    if not zip_backup:
        _write_last_backup_meta(backup_dir, method="restore_pre", created_path=pre_db)
        return pre_db

    pre_zip = os.path.join(backup_dir, f"{PRE_RESTORE_PREFIX}{ts}.zip")
    with zipfile.ZipFile(pre_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.write(pre_db, arcname=os.path.basename(pre_db))

    try:
        os.remove(pre_db)
    except Exception:
        pass

    _write_last_backup_meta(backup_dir, method="restore_pre", created_path=pre_zip)
    return pre_zip


def restore_database_from_backup(
    backup_path: str,
    backup_dir: str,
    make_prebackup: bool = True,
    prebackup_zip: bool = True,
) -> Tuple[Optional[str], str]:
    """
    Restaura la DB desde un backup (.db o .zip con .db dentro) SOBREESCRIBIENDO DB_PATH.

    - Si make_prebackup=True: crea pre_restore antes de tocar la DB.
    Retorna (prebackup_path, restored_from_backup_path)
    """
    if not backup_path or not os.path.exists(backup_path):
        raise FileNotFoundError("Backup seleccionado no existe.")

    _ensure_dir(os.path.dirname(DB_PATH))
    _ensure_dir(backup_dir)

    pre_path: Optional[str] = None
    if make_prebackup:
        pre_path = _make_pre_restore_backup(backup_dir, zip_backup=prebackup_zip)

    src_db = backup_path
    tmp_dir: Optional[str] = None

    try:
        if backup_path.lower().endswith(".zip"):
            tmp_dir = tempfile.mkdtemp(prefix="sarapsicologa_restore_")
            with zipfile.ZipFile(backup_path, "r") as z:
                db_members = [m for m in z.namelist() if m.lower().endswith(".db")]
                if not db_members:
                    raise ValueError("El ZIP no contiene ningún archivo .db.")
                member = db_members[0]
                z.extract(member, tmp_dir)
                src_db = os.path.join(tmp_dir, member)

        if not src_db.lower().endswith(".db"):
            raise ValueError("El backup debe ser .db o .zip con .db.")

        shutil.copy2(src_db, DB_PATH)
        _write_last_backup_meta(backup_dir, method="restore", created_path=backup_path)
        return (pre_path, backup_path)

    finally:
        if tmp_dir and os.path.isdir(tmp_dir):
            try:
                shutil.rmtree(tmp_dir)
            except Exception:
                pass


def purge_backups(
    backup_dir: str,
    keep_last: int = 10,
    include_pre_restore: bool = False,
) -> List[str]:
    """
    Depura backups antiguos.
    - Backups normales: conserva los keep_last más recientes.
    - pre_restore: si include_pre_restore=True, conserva SOLO 1 (el más reciente).
    Retorna lista de paths eliminados.
    """
    if not backup_dir or not os.path.isdir(backup_dir):
        return []

    items = list_backups(backup_dir)

    def is_pre_restore(name: str) -> bool:
        return name.startswith(PRE_RESTORE_PREFIX)

    # Separar
    pre_items = [x for x in items if is_pre_restore(x["name"])]
    normal_items = [x for x in items if not is_pre_restore(x["name"])]

    # Ya vienen ordenados desc por mtime desde list_backups(), pero por si acaso:
    pre_items.sort(key=lambda x: x["mtime"], reverse=True)
    normal_items.sort(key=lambda x: x["mtime"], reverse=True)

    deleted: List[str] = []

    # 1) Depurar backups normales: dejar keep_last
    to_delete_normal = normal_items[keep_last:] if keep_last >= 0 else normal_items
    for it in to_delete_normal:
        p = it["path"]
        try:
            os.remove(p)
            deleted.append(p)
        except Exception:
            pass

    # 2) Depurar pre_restore: dejar SOLO 1 si se solicita
    if include_pre_restore:
        to_delete_pre = pre_items[1:]  # deja el más reciente (index 0)
        for it in to_delete_pre:
            p = it["path"]
            try:
                os.remove(p)
                deleted.append(p)
            except Exception:
                pass

    return deleted


def read_last_backup_meta(backup_dir: str) -> Optional[Dict]:
    """
    Lee backup_dir/last_backup.json si existe.
    Útil para mostrar 'último backup' en UI.
    """
    try:
        meta_path = os.path.join(backup_dir, "last_backup.json")
        if not os.path.exists(meta_path):
            return None
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
