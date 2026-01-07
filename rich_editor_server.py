# app/rich_editor_server.py
from __future__ import annotations

import json
import sqlite3
import socket
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import os

# OJO: importa desde tu db.py real
from .db import get_connection, init_db, DATA_DIR, DB_PATH


def _db_conn():
    conn = sqlite3.connect(DB_PATH, timeout=5)  # 👈 importantísimo
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _read_body(handler: BaseHTTPRequestHandler) -> bytes:
    length = int(handler.headers.get("Content-Length") or "0")
    return handler.rfile.read(length) if length > 0 else b""


@dataclass
class RichEditorConfig:
    host: str = "127.0.0.1"
    port: int | None = None
    # Por defecto: /data/rich_editor (coherente con tu empaquetado)
    assets_dir: Path = DATA_DIR / "rich_editor"


class RichEditorServer:
    """
    Servidor local (localhost) para el editor enriquecido.
    Guarda/lee HTML en la tabla `sesiones_clinicas.contenido_html`.

    Requisitos:
      - data/rich_editor/rich_editor.html
      - data/rich_editor/assets/* (css/js del editor)
    """

    def __init__(self, cfg: RichEditorConfig | None = None):
        self.cfg = cfg or RichEditorConfig()
        self.host = self.cfg.host
        self.port = self.cfg.port or _find_free_port()
        self.base_url = f"http://{self.host}:{self.port}"
        self.assets_dir = Path(self.cfg.assets_dir).resolve()

        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        
        self.java_path = shutil.which("java")
        self.spellcheck_enabled = bool(self.java_path)
        
            # -------- LanguageTool local --------
        self._lt_proc: subprocess.Popen | None = None
        self._lt_port: int = 0
        self._lt_url: str | None = None
        self.spellcheck_enabled = False  # ya lo usas en /api/spellcheck/status

    # -------------------- Migración DB --------------------

    @staticmethod
    def ensure_db_migration() -> None:
        """
        Asegura que exista sesiones_clinicas.contenido_html (TEXT).
        Seguro para DBs existentes.
        """
        init_db()  # crea tablas si faltan
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(sesiones_clinicas);")
            cols = [r[1] for r in cur.fetchall()]
            if "contenido_html" not in cols:
                cur.execute("ALTER TABLE sesiones_clinicas ADD COLUMN contenido_html TEXT;")
                conn.commit()
        finally:
            conn.close()

    # -------------------- Start/Stop --------------------

    def start(self) -> None:
        if self._httpd is not None:
            return

        self.ensure_db_migration()

        server = self  # captura para el handler

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                # silenciar logs
                return

            def _send(self, code: int, body: bytes, content_type: str = "text/plain; charset=utf-8"):
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _send_json(self, code: int, obj: dict):
                self._send(
                    code,
                    json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                    "application/json; charset=utf-8",
                )

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path

                if path == "/health":
                    return self._send_json(200, {"ok": True})

                if path == "/editor":
                    html_path = server.assets_dir / "rich_editor.html"
                    if not html_path.exists():
                        return self._send(
                            500,
                            f"Falta el archivo: {html_path}".encode("utf-8"),
                        )

                    qs = parse_qs(parsed.query)
                    sesion_id = (qs.get("sesion") or [""])[0].strip()

                    html = html_path.read_text(encoding="utf-8")
                    html = html.replace("__SESION_ID__", sesion_id)
                    return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

                if path.startswith("/assets/"):
                    rel = path.replace("/assets/", "").lstrip("/")
                    file_path = server.assets_dir / "assets" / rel
                    if not file_path.exists() or not file_path.is_file():
                        return self._send(404, b"Not found")

                    ct = "application/octet-stream"
                    suf = file_path.suffix.lower()
                    if suf == ".js":
                        ct = "text/javascript; charset=utf-8"
                    elif suf == ".css":
                        ct = "text/css; charset=utf-8"
                    elif suf in (".woff", ".woff2"):
                        ct = "font/woff2"
                    elif suf == ".svg":
                        ct = "image/svg+xml"

                    return self._send(200, file_path.read_bytes(), ct)

                if path.startswith("/api/sesion/"):
                    sesion_id = path.split("/api/sesion/", 1)[1].strip()
                    if not sesion_id:
                        return self._send_json(400, {"ok": False, "error": "missing sesion_id"})

                    conn = get_connection()
                    try:
                        cur = conn.cursor()
                        cur.execute(
                            "SELECT contenido_html, contenido FROM sesiones_clinicas WHERE id = ? LIMIT 1;",
                            (sesion_id,),
                        )
                        row = cur.fetchone()
                    finally:
                        conn.close()

                    if not row:
                        return self._send_json(404, {"ok": False, "error": "not found"})

                    # sqlite3.Row soporta index y keys
                    html = row[0] or ""
                    md = row[1] or ""
                    return self._send_json(200, {"ok": True, "html": html, "markdown": md})
                
                # chequeo estado corrector ortográfico
                if path == "/api/spellcheck/status":
                    return self._send_json(
                        200,
                        {
                            "ok": True,
                            "enabled": server.spellcheck_enabled,
                            "reason": None if server.spellcheck_enabled else "Java no detectado",
                        },
                    )
                    
                    
                if path == "/api/spellcheck":
                    body = _read_body(self)
                    try:
                        data = json.loads(body.decode("utf-8"))
                    except Exception:
                        return self._send_json(400, {"ok": False, "reason": "invalid json", "replacements": []})

                    word = (data.get("word") or "").strip().lower()

                    # Mock mínimo para probar UI
                    if word == "aca":
                        return self._send_json(200, {"ok": True, "replacements": ["acá", "aquí"]})

                    return self._send_json(200, {"ok": True, "replacements": []})

                return self._send(404, b"Not found")

            def do_POST(self):
                parsed = urlparse(self.path)
                path = parsed.path

                if path.startswith("/api/sesion/"):
                    sesion_id = path.split("/api/sesion/", 1)[1].strip()
                    if not sesion_id:
                        return self._send_json(400, {"ok": False, "error": "missing sesion_id"})

                    body = _read_body(self)
                    try:
                        data = json.loads(body.decode("utf-8"))
                    except Exception:
                        return self._send_json(400, {"ok": False, "error": "invalid json"})

                    html = (data.get("html") or "").strip()

                    conn = get_connection()
                    try:
                        cur = conn.cursor()
                        cur.execute(
                            "UPDATE sesiones_clinicas SET contenido_html = ? WHERE id = ?;",
                            (html, sesion_id),
                        )
                        conn.commit()
                        updated = cur.rowcount
                    finally:
                        conn.close()

                    if updated <= 0:
                        return self._send_json(404, {"ok": False, "error": "not found"})

                    return self._send_json(200, {"ok": True})
                
                
                # ✅ spellcheck: recibe POST JSON { word: "...", language: "es" }
                if path == "/api/spellcheck":
                    body = _read_body(self)
                    try:
                        data = json.loads(body.decode("utf-8"))
                    except Exception:
                        return self._send_json(400, {"ok": False, "reason": "invalid json", "replacements": []})

                    word = (data.get("word") or "").strip()
                    lang = (data.get("language") or "es").strip() or "es"

                    suggestions = server._lt_check_word(word, language=lang)

                    return self._send_json(200, {"ok": True, "replacements": suggestions})

                return self._send(404, b"Not found")

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
            self._thread = None
            
        self._stop_languagetool()

    def editor_url(self, sesion_id: int, paciente: str = "", documento: str = "") -> str:
        q = {
            "sesion": str(sesion_id),
            "paciente": paciente or "",
            "doc": documento or "",
        }
        return f"{self.base_url}/editor?{urllib.parse.urlencode(q)}"
    

    def _find_java(self) -> str | None:
        # 1) JRE portable dentro de tu app (RECOMENDADO)
        java_portable = DATA_DIR / "jre" / "bin" / ("java.exe" if os.name == "nt" else "java")
        if java_portable.exists():
            return str(java_portable)

        # 2) fallback: java del sistema
        return shutil.which("java")

    def _find_languagetool_jar(self) -> Path | None:
        """
        Busca el jar del server dentro de data/rich_editor/languagetool
        """
        lt_dir = self.assets_dir / "languagetool"
        if not lt_dir.exists():
            return None

        # Intento 1: nombre típico
        p = lt_dir / "languagetool-server.jar"
        if p.exists():
            return p

        # Intento 2: cualquiera que parezca server jar
        jars = list(lt_dir.glob("**/*server*.jar"))
        if jars:
            return jars[0]

        # Intento 3: cualquier jar (último recurso)
        jars = list(lt_dir.glob("**/*.jar"))
        return jars[0] if jars else None

    def _lt_health_ok(self, url_base: str) -> bool:
        try:
            # endpoint típico LT v2
            with urllib.request.urlopen(url_base + "/v2/languages", timeout=1.5) as r:
                return 200 <= r.status < 300
        except Exception:
            return False

    def _ensure_languagetool(self) -> bool:
        """
        Levanta LanguageTool local una sola vez.
        Devuelve True si está listo.
        """
        if self._lt_url and self._lt_health_ok(self._lt_url):
            self.spellcheck_enabled = True
            return True

        java = self._find_java()
        jar = self._find_languagetool_jar()

        if not java or not jar:
            self.spellcheck_enabled = False
            return False

        # puerto libre local para LT
        self._lt_port = _find_free_port()
        self._lt_url = f"http://127.0.0.1:{self._lt_port}"

        # Arrancar LT server (modo recomendado)
        cmd = [
            java,
            "-jar",
            str(jar),
            "--port",
            str(self._lt_port),
            "--allow-origin",
            "*",
        ]

        try:
            self._lt_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(jar.parent),
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            )
        except Exception:
            self.spellcheck_enabled = False
            return False

        # Esperar readiness
        for _ in range(40):  # ~4s
            if self._lt_health_ok(self._lt_url):
                self.spellcheck_enabled = True
                return True
            time.sleep(0.1)

        self.spellcheck_enabled = False
        return False

    def _lt_check_word(self, word: str, language: str = "es") -> list[str]:
        """
        Llama a LanguageTool local y retorna sugerencias.
        """
        if not self._ensure_languagetool() or not self._lt_url:
            return []

        text = (word or "").strip()
        if not text:
            return []

        form = urllib.parse.urlencode({
            "language": language,
            "text": text
        }).encode("utf-8")

        req = urllib.request.Request(
            self._lt_url + "/v2/check",
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=3.0) as r:
            data = json.loads(r.read().decode("utf-8"))

        matches = data.get("matches") or []
        if not matches:
            return []

        # Para una sola palabra normalmente basta el primer match
        reps = matches[0].get("replacements") or []
        return [x.get("value") for x in reps if x.get("value")][:8]

    def _stop_languagetool(self):
        if self._lt_proc:
            try:
                self._lt_proc.terminate()
            except Exception:
                pass
            self._lt_proc = None
        self._lt_url = None
        self._lt_port = 0
        self.spellcheck_enabled = False

    
    
    
