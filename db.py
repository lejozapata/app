import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import date, datetime, timedelta
import os
import sys


# ----------------- Reglas de negocio de citas -----------------

# Precios por modalidad (puedes ajustar estos valores cuando quieras)
PRECIOS_MODALIDAD: Dict[str, int] = {
    # Se mantiene por compatibilidad; hoy el precio real viene de Servicios y se puede
    # ajustar por cita. Esta tabla solo es un fallback.
    "particular": 0,
    "convenio": 0,
}

# Estados posibles de una cita.
# Estos valores se usan en la UI de agenda.
ESTADOS_CITA: Dict[str, str] = {
    "reservado": "Reservado",
    "confirmado": "Confirmado",
    "no_asistio": "No asistió",
}



# --------------------------------------------------------------


# Ruta del archivo de base de datos: ../data/sara_psico.db
def get_base_dir() -> Path:
    # Si el wrapper lo setea, perfecto.
    env = os.environ.get("SARA_BASE_DIR")
    if env:
        return Path(env)

    # DEV: base = root del repo (app/db.py -> parents[1])
    repo_base = Path(__file__).resolve().parents[1]
    if (repo_base / "data").exists():
        return repo_base

    # EXE: fallback a carpeta Roaming donde Flet instala "app"
    roaming = Path(os.environ.get("APPDATA", str(repo_base)))
    # OJO: esto depende del company + project que usaste en build
    candidate = roaming / "Your Company" / "SaraPsicologa" / "flet" / "app"
    return candidate

# BASE_DIR = get_base_dir()
# DATA_DIR = BASE_DIR / "data"
# DATA_DIR.mkdir(parents=True, exist_ok=True)

# DB_PATH = DATA_DIR / "sara_psico.db"

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # .../flet/app  (packaged) o E:/SaraPsicologa (dev)
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "sara_psico.db"
SECRET_KEY_PATH = DATA_DIR / ".secret.key"
IMAGES_DIR = DATA_DIR / "imagenes"
FACTURAS_DIR = DATA_DIR / "facturas_pdf"
HISTORIAS_DIR = DATA_DIR / "historias_pdf"


def get_connection() -> sqlite3.Connection:
    """Devuelve una conexión a la base de datos SQLite."""
    conn = sqlite3.connect(DB_PATH)
    # Activar foreign keys en SQLite
    conn.execute("PRAGMA foreign_keys = ON;")
    # Para poder obtener filas como diccionarios si se quiere
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Crea las tablas necesarias si no existen."""
    conn = get_connection()
    cur = conn.cursor()

    #######################TABLAS ########################
    # Tabla de pacientes
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pacientes (
            documento TEXT PRIMARY KEY,
            tipo_documento TEXT NOT NULL,
            nombre_completo TEXT NOT NULL,
            fecha_nacimiento TEXT NOT NULL,
            sexo TEXT,
            estado_civil TEXT,
            escolaridad TEXT,
            eps TEXT,
            direccion TEXT,
            email TEXT,
            indicativo_pais TEXT NOT NULL DEFAULT '57',
            telefono TEXT,
            contacto_emergencia_nombre TEXT,
            contacto_emergencia_telefono TEXT,
            observaciones TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        """
    )


    # Migración segura: agregar indicativo_pais si la tabla ya existía
    cur.execute("PRAGMA table_info(pacientes);")
    columnas_pacientes = [row[1] for row in cur.fetchall()]
    if "indicativo_pais" not in columnas_pacientes:
        cur.execute("ALTER TABLE pacientes ADD COLUMN indicativo_pais TEXT NOT NULL DEFAULT '57';")

      # Tabla de citas
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS citas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento_paciente TEXT NOT NULL,
            fecha_hora TEXT NOT NULL,
            modalidad TEXT NOT NULL CHECK (modalidad IN ('particular', 'convenio')),
            canal TEXT NOT NULL CHECK (canal IN ('presencial', 'virtual')),
            motivo TEXT,
            notas TEXT,
            estado TEXT,
            precio REAL DEFAULT 0,
            pagado INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (documento_paciente) REFERENCES pacientes (documento)
        );
        """
    )
# Migraciones seguras para BD ya creadas
    cur.execute("PRAGMA table_info(citas);")
    columnas_citas = [row[1] for row in cur.fetchall()]
    if "precio" not in columnas_citas:
        cur.execute("ALTER TABLE citas ADD COLUMN precio REAL DEFAULT 0;")
    if "pagado" not in columnas_citas:
        cur.execute("ALTER TABLE citas ADD COLUMN pagado INTEGER NOT NULL DEFAULT 0;")

    # Tabla de antecedentes médicos
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS antecedentes_medicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento_paciente TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            fecha_registro TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (documento_paciente) REFERENCES pacientes (documento)
        );
        """
    )

    # Tabla de antecedentes psicológicos
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS antecedentes_psicologicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento_paciente TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            fecha_registro TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (documento_paciente) REFERENCES pacientes (documento)
        );
        """
    )

     # Tabla de configuración del profesional (siempre un solo registro id=1)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS configuracion_profesional (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            nombre_profesional TEXT,
            hora_inicio TEXT NOT NULL DEFAULT '07:00',
            hora_fin TEXT NOT NULL DEFAULT '21:00',
            dias_atencion TEXT NOT NULL DEFAULT '0,1,2,3,4',
            direccion TEXT,
            zona_horaria TEXT,
            telefono TEXT,
            email TEXT
        );
        """
    )

    # Tabla de configuración de facturación (siempre un solo registro id=1)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS configuracion_facturacion (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            prefijo_factura TEXT NOT NULL DEFAULT 'PS',   -- ej: "PS"
            ultimo_consecutivo INTEGER NOT NULL DEFAULT 0,
            banco TEXT,
            beneficiario TEXT,
            nit TEXT,
            numero_cuenta TEXT,
            forma_pago TEXT,
            notas TEXT
        );
        """
    )

        

    # Tabla de configuración de GMAIL (siempre un solo registro id=1)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS configuracion_gmail (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            gmail_user TEXT,
            gmail_app_password TEXT,
            habilitado INTEGER NOT NULL DEFAULT 0
        );
        """
    )

# Tabla de servicios / modalidades de cita
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS servicios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            modalidad TEXT NOT NULL CHECK (modalidad IN ('particular','convenio')),
            precio REAL NOT NULL,
            empresa TEXT,
            activo INTEGER NOT NULL DEFAULT 1
        );
        """
    )

    # Evitar duplicados: mismo nombre + modalidad + empresa (cuando aplique)
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_servicios_nombre_modalidad_empresa
        ON servicios (nombre, modalidad, IFNULL(empresa, ''));
        """
    )

    # Tabla de empresas de convenio
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS empresas_convenio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            nit TEXT,
            direccion TEXT,
            ciudad TEXT,
            pais TEXT,
            telefono TEXT,
            email_facturacion TEXT,
            contacto TEXT,
            activa INTEGER NOT NULL DEFAULT 1
        );
        """
    )


    # Tabla de facturas de convenio (encabezado)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS facturas_convenio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT NOT NULL UNIQUE,             -- PS0004
            fecha TEXT NOT NULL,                     -- 'YYYY-MM-DD'
            empresa_id INTEGER NOT NULL,
            paciente_documento TEXT,
            paciente_nombre TEXT,
            subtotal REAL NOT NULL DEFAULT 0,
            iva REAL NOT NULL DEFAULT 0,
            total REAL NOT NULL DEFAULT 0,
            total_letras TEXT,
            forma_pago TEXT,
            estado TEXT NOT NULL DEFAULT 'pendiente', -- pendiente/pagada/anulada
            ruta_pdf TEXT,
            creada_en TEXT DEFAULT (datetime('now','localtime')),
            actualizada_en TEXT,
            FOREIGN KEY (empresa_id) REFERENCES empresas_convenio(id)
        );
        """
    )

    # Detalle de facturas (puede haber varias filas por factura)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS facturas_convenio_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            factura_id INTEGER NOT NULL,
            descripcion TEXT NOT NULL,
            cantidad REAL NOT NULL DEFAULT 1,
            valor_unitario REAL NOT NULL,
            valor_total REAL NOT NULL,
            FOREIGN KEY (factura_id) REFERENCES facturas_convenio(id)
        );
        """
    )

    # Tabla de gastos financieros (arriendo de consultorio, otros gastos)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS gastos_financieros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,          -- 'YYYY-MM-DD'
            tipo TEXT NOT NULL,           -- ej: 'arriendo_consultorio', 'otro'
            descripcion TEXT,
            monto REAL NOT NULL           -- siempre positivo
        );
        """
    )

    # Tabla de horario por día (0=Lunes .. 6=Domingo)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS horarios_atencion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dia INTEGER NOT NULL UNIQUE CHECK(dia BETWEEN 0 AND 6),
            habilitado INTEGER NOT NULL DEFAULT 0,
            hora_inicio TEXT NOT NULL DEFAULT '08:00',
            hora_fin TEXT NOT NULL DEFAULT '17:00'
        );
        """
    )

    # Asegurar que existan las 7 filas (una por día)
    for d in range(7):
        cur.execute(
            """
            INSERT OR IGNORE INTO horarios_atencion (dia, habilitado, hora_inicio, hora_fin)
            VALUES (?, 0, '08:00', '17:00');
            """,
            (d,),
        )

    # Tabla de bloqueos de agenda (bloqueo de horario sin paciente)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bloqueos_agenda (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            motivo TEXT NOT NULL,
            fecha_hora_inicio TEXT NOT NULL,
            fecha_hora_fin TEXT NOT NULL
        )
        """
    )

    ########### Historia clínica ################
     # Tabla de historia clínica (una por paciente)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS historia_clinica (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento_paciente TEXT NOT NULL UNIQUE,
            fecha_apertura TEXT NOT NULL,
            motivo_consulta_inicial TEXT,
            informacion_adicional TEXT,
            FOREIGN KEY (documento_paciente) REFERENCES pacientes (documento)
        );
        """
    )

    # Tabla de sesiones clínicas (múltiples por historia)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sesiones_clinicas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            historia_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            titulo TEXT,
            contenido TEXT NOT NULL,
            observaciones TEXT,
            FOREIGN KEY (historia_id) REFERENCES historia_clinica (id)
        );
        """
    )

    # Tabla de paquetes de arriendo de consultorio
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS paquetes_arriendo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_compra TEXT NOT NULL,   -- 'YYYY-MM-DD'
            cantidad_citas INTEGER NOT NULL,
            costo_total REAL NOT NULL,
            citas_usadas INTEGER NOT NULL DEFAULT 0,
            notas TEXT
        );
        """
    )
    
    # Tabla de consumo de paquetes de arriendo
    cur.execute("""
    CREATE TABLE IF NOT EXISTS consumo_paquetes_arriendo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paquete_id INTEGER NOT NULL,
        cita_id INTEGER NOT NULL UNIQUE,
        fecha_consumo TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        consumido_por TEXT,
        FOREIGN KEY(paquete_id) REFERENCES paquetes_arriendo(id) ON DELETE CASCADE,
        FOREIGN KEY(cita_id) REFERENCES citas(id) ON DELETE CASCADE
    );
    """)

    # Índices (van aparte)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS ix_consumo_paquetes_arriendo_fecha
    ON consumo_paquetes_arriendo (fecha_consumo);
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS ix_consumo_paquetes_arriendo_paquete
    ON consumo_paquetes_arriendo (paquete_id);
    """)
    
    

    # Tabla de paquetes de consultorio (sesiones prepagadas)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS paquetes_consultorio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_compra TEXT NOT NULL,
            descripcion TEXT,
            precio_total REAL NOT NULL,
            cantidad_sesiones INTEGER NOT NULL,
            sesiones_restantes INTEGER NOT NULL,
            activo INTEGER NOT NULL DEFAULT 1
        );
        """
    )
    

    # Tabla de consumo de paquetes de consultorio
    cur.execute(
    """

        CREATE TABLE IF NOT EXISTS consumo_paquetes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paquete_id INTEGER NOT NULL,
            cita_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            FOREIGN KEY(paquete_id) REFERENCES paquetes_consultorio(id),
            FOREIGN KEY(cita_id) REFERENCES citas(id)
        );
        """
    )

    
    # Tabla para guardar información de archivos generados
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS documentos_generados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL CHECK (tipo IN ('consentimiento', 'certificado_asistencia')),
            documento_paciente TEXT NOT NULL,
            cita_id INTEGER,
            path TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(tipo, documento_paciente, cita_id)
        );
        """
    )
    
    conn.commit()
    conn.close()

#######################FIN TABLAS ########################

# ------------ PACIENTES -------------


def crear_paciente(paciente: Dict[str, Any]) -> None:
    """Inserta un nuevo paciente en la base de datos."""
    conn = get_connection()
    cur = conn.cursor()

    datos = dict(paciente)
    # Compatibilidad: si no viene indicativo_pais, asumimos Colombia (57)
    datos.setdefault('indicativo_pais', '57')

    cur.execute(
        """
        INSERT INTO pacientes (
            documento,
            tipo_documento,
            nombre_completo,
            fecha_nacimiento,
            sexo,
            estado_civil,
            escolaridad,
            eps,
            direccion,
            email,
            indicativo_pais,
            telefono,
            contacto_emergencia_nombre,
            contacto_emergencia_telefono,
            observaciones
        ) VALUES (
            :documento,
            :tipo_documento,
            :nombre_completo,
            :fecha_nacimiento,
            :sexo,
            :estado_civil,
            :escolaridad,
            :eps,
            :direccion,
            :email,
            :indicativo_pais,
            :telefono,
            :contacto_emergencia_nombre,
            :contacto_emergencia_telefono,
            :observaciones
        );
        """,
        datos,
    )

    conn.commit()
    conn.close()


def listar_pacientes() -> List[sqlite3.Row]:
    """Devuelve todos los pacientes ordenados por nombre."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM pacientes
        ORDER BY nombre_completo COLLATE NOCASE;
        """
    )

    filas = cur.fetchall()
    conn.close()
    return filas


def obtener_paciente(documento: str) -> Optional[sqlite3.Row]:
    """Obtiene un paciente por su documento."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM pacientes WHERE documento = ?;",
        (documento,),
    )
    fila = cur.fetchone()
    conn.close()
    return fila


def actualizar_paciente(paciente: Dict[str, Any]) -> None:
    """Actualiza los datos de un paciente existente (identificado por documento)."""
    conn = get_connection()
    cur = conn.cursor()

    datos = dict(paciente)
    datos.setdefault('indicativo_pais', '57')

    cur.execute(
        """
        UPDATE pacientes
        SET
            tipo_documento = :tipo_documento,
            nombre_completo = :nombre_completo,
            fecha_nacimiento = :fecha_nacimiento,
            sexo = :sexo,
            estado_civil = :estado_civil,
            escolaridad = :escolaridad,
            eps = :eps,
            direccion = :direccion,
            email = :email,
            indicativo_pais = :indicativo_pais,
            telefono = :telefono,
            contacto_emergencia_nombre = :contacto_emergencia_nombre,
            contacto_emergencia_telefono = :contacto_emergencia_telefono,
            observaciones = :observaciones,
            updated_at = datetime('now','localtime')
        WHERE documento = :documento;
        """,
        paciente,
    )

    conn.commit()
    conn.close()


def eliminar_paciente(documento: str) -> None:
    """Elimina un paciente y sus datos relacionados (citas, antecedentes)."""
    conn = get_connection()
    cur = conn.cursor()

    # Eliminar datos relacionados primero por foreign keys si fuera necesario
    cur.execute("DELETE FROM citas WHERE documento_paciente = ?;", (documento,))
    cur.execute("DELETE FROM antecedentes_medicos WHERE documento_paciente = ?;", (documento,))
    cur.execute("DELETE FROM antecedentes_psicologicos WHERE documento_paciente = ?;", (documento,))

    # Eliminar sesiones e historia clínica asociada
    cur.execute(
        """
        DELETE FROM sesiones_clinicas
        WHERE historia_id IN (
            SELECT id FROM historia_clinica WHERE documento_paciente = ?
        );
        """,
        (documento,),
    )
    cur.execute("DELETE FROM historia_clinica WHERE documento_paciente = ?;", (documento,))

    # Luego el paciente
    cur.execute("DELETE FROM pacientes WHERE documento = ?;", (documento,))

    conn.commit()
    conn.close()


# --------- ANTECEDENTES MÉDICOS / PSICOLÓGICOS ---------


def crear_antecedente_medico(documento_paciente: str, descripcion: str) -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO antecedentes_medicos (
            documento_paciente,
            descripcion
        ) VALUES (?, ?);
        """,
        (documento_paciente, descripcion),
    )

    conn.commit()
    conn.close()


def crear_antecedente_psicologico(documento_paciente: str, descripcion: str) -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO antecedentes_psicologicos (
            documento_paciente,
            descripcion
        ) VALUES (?, ?);
        """,
        (documento_paciente, descripcion),
    )

    conn.commit()
    conn.close()

############### LISTAR ANTECEDENTES ################
def listar_antecedentes_medicos(documento_paciente: str) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM antecedentes_medicos
        WHERE documento_paciente = ?
        ORDER BY fecha_registro DESC, id DESC;
        """,
        (documento_paciente,),
    )

    filas = cur.fetchall()
    conn.close()
    return filas


def listar_antecedentes_psicologicos(documento_paciente: str) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM antecedentes_psicologicos
        WHERE documento_paciente = ?
        ORDER BY fecha_registro DESC, id DESC;
        """,
        (documento_paciente,),
    )

    filas = cur.fetchall()
    conn.close()
    return filas

############### ACTUALIZAR ANTECEDENTES ################
def actualizar_antecedente_medico(antecedente_id: int, descripcion: str) -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE antecedentes_medicos
        SET descripcion = ?, fecha_registro = datetime('now','localtime')
        WHERE id = ?;
        """,
        (descripcion, antecedente_id),
    )

    conn.commit()
    conn.close()


def actualizar_antecedente_psicologico(antecedente_id: int, descripcion: str) -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE antecedentes_psicologicos
        SET descripcion = ?, fecha_registro = datetime('now','localtime')
        WHERE id = ?;
        """,
        (descripcion, antecedente_id),
    )

    conn.commit()
    conn.close()

############### ELIMINAR ANTECEDENTES ################
def eliminar_antecedente_medico(antecedente_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM antecedentes_medicos WHERE id = ?;",
        (antecedente_id,),
    )

    conn.commit()
    conn.close()


def eliminar_antecedente_psicologico(antecedente_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM antecedentes_psicologicos WHERE id = ?;",
        (antecedente_id,),
    )

    conn.commit()
    conn.close()

# --------- HISTORIA CLÍNICA Y SESIONES CLÍNICAS ---------


def obtener_historia_clinica(documento_paciente: str) -> Optional[sqlite3.Row]:
    """Obtiene la historia clínica de un paciente (si existe)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM historia_clinica
        WHERE documento_paciente = ?;
        """,
        (documento_paciente,),
    )
    fila = cur.fetchone()
    conn.close()
    return fila


def guardar_historia_clinica(datos: Dict[str, Any]) -> int:
    """
    Crea o actualiza la historia clínica de un paciente.
    Si datos["id"] existe, actualiza; si no, crea y devuelve el nuevo id.
    Espera:
      - id (opcional)
      - documento_paciente
      - fecha_apertura (YYYY-MM-DD)
      - motivo_consulta_inicial
      - informacion_adicional
    """
    conn = get_connection()
    cur = conn.cursor()

    if datos.get("id"):
        cur.execute(
            """
            UPDATE historia_clinica
            SET fecha_apertura = ?, motivo_consulta_inicial = ?, informacion_adicional = ?
            WHERE id = ?;
            """,
            (
                datos.get("fecha_apertura"),
                datos.get("motivo_consulta_inicial"),
                datos.get("informacion_adicional"),
                datos.get("id"),
            ),
        )
        historia_id = datos["id"]
    else:
        cur.execute(
            """
            INSERT INTO historia_clinica (
                documento_paciente,
                fecha_apertura,
                motivo_consulta_inicial,
                informacion_adicional
            ) VALUES (?, ?, ?, ?);
            """,
            (
                datos.get("documento_paciente"),
                datos.get("fecha_apertura"),
                datos.get("motivo_consulta_inicial"),
                datos.get("informacion_adicional"),
            ),
        )
        historia_id = cur.lastrowid

    conn.commit()
    conn.close()
    return historia_id


def listar_sesiones_clinicas(historia_id: int) -> List[sqlite3.Row]:
    """Lista sesiones clínicas de una historia, ordenadas de la más reciente a la más antigua."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM sesiones_clinicas
        WHERE historia_id = ?
        ORDER BY fecha DESC, id DESC;
        """,
        (historia_id,),
    )
    filas = cur.fetchall()
    conn.close()
    return filas


def guardar_sesion_clinica(datos: Dict[str, Any]) -> int:
    """
    Crea o actualiza una sesión clínica.
    Espera:
      - id (opcional)
      - historia_id
      - fecha (YYYY-MM-DD)
      - titulo
      - contenido
      - observaciones
    """
    conn = get_connection()
    cur = conn.cursor()

    if datos.get("id"):
        cur.execute(
            """
            UPDATE sesiones_clinicas
            SET fecha = ?, titulo = ?, contenido = ?, observaciones = ?
            WHERE id = ?;
            """,
            (
                datos.get("fecha"),
                datos.get("titulo"),
                datos.get("contenido"),
                datos.get("observaciones"),
                datos.get("id"),
            ),
        )
        sesion_id = datos["id"]
    else:
        cur.execute(
            """
            INSERT INTO sesiones_clinicas (
                historia_id,
                fecha,
                titulo,
                contenido,
                observaciones
            ) VALUES (?, ?, ?, ?, ?);
            """,
            (
                datos.get("historia_id"),
                datos.get("fecha"),
                datos.get("titulo"),
                datos.get("contenido"),
                datos.get("observaciones"),
            ),
        )
        sesion_id = cur.lastrowid

    conn.commit()
    conn.close()
    return sesion_id


def eliminar_sesion_clinica(sesion_id: int) -> None:
    """Elimina una sesión clínica por id."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM sesiones_clinicas WHERE id = ?;", (sesion_id,))
    conn.commit()
    conn.close()





# ===================== C I T A S =====================

def crear_cita(cita: Dict[str, Any]) -> int:
    """
    Inserta una nueva cita en la base de datos.

    Espera un diccionario con llaves:
      - documento_paciente (str)
      - fecha_hora (str, formato 'YYYY-MM-DD HH:MM')
      - modalidad (str: 'virtual' | 'presencial' | 'convenio_empresarial')
      - motivo (str, opcional)
      - notas (str, opcional)
      - estado (str: 'reservado', 'confirmado', 'no_asistio', etc.)
      - pagado (int: 0 o 1, opcional -> default 0)
    Devuelve el ID autogenerado de la cita.
    """
    conn = get_connection()
    cur = conn.cursor()

    datos = dict(cita)
    # Compatibilidad: si no viene pagado en el dict, se asume 0 (no pagado)
    if "pagado" not in datos:
        datos["pagado"] = 0

    # Compatibilidad: si no viene canal, asumimos presencial
    if "canal" not in datos or not str(datos.get("canal") or "").strip():
        datos["canal"] = "presencial"

    cur.execute(
        """
        INSERT INTO citas (
            documento_paciente,
            fecha_hora,
            modalidad,
            canal,
            motivo,
            notas,
            estado,
            precio,
            pagado
        ) VALUES (
            :documento_paciente,
            :fecha_hora,
            :modalidad,
            :canal,
            :motivo,
            :notas,
            :estado,
            :precio,
            :pagado
        );
        """,
        datos,
    )

    cita_id = cur.lastrowid
    conn.commit()
    conn.close()
    return cita_id


def listar_citas_rango(fecha_inicio: str, fecha_fin: str) -> List[sqlite3.Row]:
    """
    Lista las citas entre dos fechas (inclusive), ordenadas por fecha_hora.

    fecha_inicio y fecha_fin deben estar en formato 'YYYY-MM-DD HH:MM'
    o 'YYYY-MM-DD HH:MM:SS' para que datetime() de SQLite las compare bien.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM citas
        WHERE datetime(fecha_hora) >= datetime(?)
          AND datetime(fecha_hora) <= datetime(?)
        ORDER BY datetime(fecha_hora) ASC;
        """,
        (fecha_inicio, fecha_fin),
    )

    filas = cur.fetchall()
    conn.close()
    return filas


def listar_citas_con_paciente_rango(fecha_inicio: str, fecha_fin: str) -> List[sqlite3.Row]:
    """
    Lista citas entre dos fechas incluyendo datos básicos del paciente.
    Devuelve columnas de 'citas' +:
      - nombre_completo
      - telefono
      - email
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            c.*,
            p.nombre_completo,
            p.indicativo_pais,
            p.telefono,
            p.email
        FROM citas c
        JOIN pacientes p
            ON p.documento = c.documento_paciente
        WHERE datetime(c.fecha_hora) >= datetime(?)
          AND datetime(c.fecha_hora) <= datetime(?)
        ORDER BY datetime(c.fecha_hora) ASC;
        """,
        (fecha_inicio, fecha_fin),
    )

    filas = cur.fetchall()
    conn.close()
    return filas

def existe_cita_en_fecha(fecha_hora: str, cita_id_excluir: Optional[int] = None) -> bool:
    """
    Devuelve True si ya hay una cita exactamente en fecha_hora.
    Si cita_id_excluir no es None, se excluye ese id de la verificación
    (útil cuando estás editando una cita).
    """
    conn = get_connection()
    cur = conn.cursor()

    if cita_id_excluir is None:
        cur.execute(
            "SELECT COUNT(*) FROM citas WHERE fecha_hora = ?;",
            (fecha_hora,),
        )
    else:
        cur.execute(
            "SELECT COUNT(*) FROM citas WHERE fecha_hora = ? AND id != ?;",
            (fecha_hora, cita_id_excluir),
        )

    count = cur.fetchone()[0]
    conn.close()
    return count > 0


def actualizar_cita(cita_id: int, campos: Dict[str, Any]) -> None:
    """
    Actualiza una cita existente.

    'campos' es un diccionario con las columnas a actualizar, por ejemplo:
      {
        "fecha_hora": "2025-12-02 08:00",
        "modalidad": "presencial",
        "motivo": "...",
        "notas": "...",
        "estado": "confirmado",
        "pagado": 1,
        "documento_paciente": "1152..."
      }
    """
    if not campos:
        return

    conn = get_connection()
    cur = conn.cursor()

    set_clauses = []
    values: List[Any] = []
    for columna, valor in campos.items():
        set_clauses.append(f"{columna} = ?")
        values.append(valor)

    values.append(cita_id)

    sql = f"UPDATE citas SET {', '.join(set_clauses)} WHERE id = ?;"
    cur.execute(sql, values)

    conn.commit()
    conn.close()

def existe_cita_en_rango(fecha_inicio: str, fecha_fin: str, cita_id_excluir: int | None = None) -> bool:
    """
    Retorna True si existe al menos una cita con fecha_hora dentro del rango [fecha_inicio, fecha_fin).
    Formato: 'YYYY-MM-DD HH:MM'
    """
    conn = get_connection()
    cur = conn.cursor()

    if cita_id_excluir is None:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM citas
            WHERE datetime(fecha_hora) >= datetime(?)
              AND datetime(fecha_hora) < datetime(?);
            """,
            (fecha_inicio, fecha_fin),
        )
    else:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM citas
            WHERE datetime(fecha_hora) >= datetime(?)
              AND datetime(fecha_hora) < datetime(?)
              AND id != ?;
            """,
            (fecha_inicio, fecha_fin, cita_id_excluir),
        )

    count = cur.fetchone()[0]
    conn.close()
    return count > 0


def eliminar_cita(cita_id: int) -> None:
    """Elimina una cita de la base de datos."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM citas WHERE id = ?;", (cita_id,))

    conn.commit()
    conn.close()

# ------------ CONFIGURACIÓN PROFESIONAL -------------


def obtener_configuracion_profesional() -> dict:
    """
    Devuelve la configuración del profesional.
    Si no existe el registro id=1, lo crea con valores por defecto.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM configuracion_profesional WHERE id = 1;")
    row = cur.fetchone()

    if row is None:
        cur.execute(
            """
            INSERT INTO configuracion_profesional (
                id, nombre_profesional, hora_inicio, hora_fin, dias_atencion,
                direccion, zona_horaria, telefono, email
            )
            VALUES (1, 'Sara Hernández', '07:00', '21:00', '1,2,3,4,5', NULL, '(GMT-5) Bogotá', NULL, NULL);
            """
        )
        conn.commit()
        cur.execute("SELECT * FROM configuracion_profesional WHERE id = 1;")
        row = cur.fetchone()

    cfg = {
        "id": row["id"],
        "nombre_profesional": row["nombre_profesional"],
        "hora_inicio": row["hora_inicio"],
        "hora_fin": row["hora_fin"],
        "dias_atencion": row["dias_atencion"],
        "direccion": row["direccion"],
        "zona_horaria": row["zona_horaria"],
        "telefono": row["telefono"],
        "email": row["email"],
    }

    conn.close()
    return cfg


def guardar_configuracion_profesional(cfg: dict) -> None:
    """
    Actualiza la configuración del profesional (siempre id=1).
    Espera claves:
      nombre_profesional, hora_inicio, hora_fin, dias_atencion,
      direccion, zona_horaria, telefono, email
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO configuracion_profesional (
            id, nombre_profesional, hora_inicio, hora_fin, dias_atencion,
            direccion, zona_horaria, telefono, email
        )
        VALUES (
            1, :nombre_profesional, :hora_inicio, :hora_fin, :dias_atencion,
            :direccion, :zona_horaria, :telefono, :email
        )
        ON CONFLICT(id) DO UPDATE SET
            nombre_profesional = excluded.nombre_profesional,
            hora_inicio = excluded.hora_inicio,
            hora_fin = excluded.hora_fin,
            dias_atencion = excluded.dias_atencion,
            direccion = excluded.direccion,
            zona_horaria = excluded.zona_horaria,
            telefono = excluded.telefono,
            email = excluded.email;
        """,
        {
            "nombre_profesional": cfg.get("nombre_profesional"),
            "hora_inicio": cfg.get("hora_inicio"),
            "hora_fin": cfg.get("hora_fin"),
            "dias_atencion": cfg.get("dias_atencion"),
            "direccion": cfg.get("direccion"),
            "zona_horaria": cfg.get("zona_horaria"),
            "telefono": cfg.get("telefono"),
            "email": cfg.get("email"),
        },
    )

    conn.commit()
    conn.close()

# ------------ HORARIOS POR DÍA -------------

def obtener_horarios_atencion() -> List[sqlite3.Row]:
    """Devuelve las 7 filas de horarios (0=Lunes..6=Domingo)."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT dia, habilitado, hora_inicio, hora_fin
        FROM horarios_atencion
        ORDER BY dia ASC;
        """
    )
    filas = cur.fetchall()
    conn.close()
    return filas


def guardar_horarios_atencion(lista_horarios: List[Dict[str, Any]]) -> None:
    """
    Guarda horarios por día.
    Espera lista de dicts con:
      - dia (int 0..6)
      - habilitado (bool/int)
      - hora_inicio (str 'HH:MM')
      - hora_fin (str 'HH:MM')
    """
    conn = get_connection()
    cur = conn.cursor()

    for h in lista_horarios or []:
        dia = int(h.get("dia"))
        habilitado = 1 if bool(h.get("habilitado")) else 0
        hora_inicio = (h.get("hora_inicio") or "08:00").strip()
        hora_fin = (h.get("hora_fin") or "17:00").strip()

        cur.execute(
            """
            UPDATE horarios_atencion
            SET habilitado = ?, hora_inicio = ?, hora_fin = ?
            WHERE dia = ?;
            """,
            (habilitado, hora_inicio, hora_fin, dia),
        )

    conn.commit()
    conn.close()


# ================== FIN C I T A S ====================



# ===================== B L O Q U E O S   A G E N D A =====================

def crear_bloqueo(bloqueo: Dict[str, Any]) -> int:
    """
    Crea un bloqueo de horario.
    Espera:
      - motivo (str)
      - fecha_hora (str: 'YYYY-MM-DD HH:MM')
    Devuelve el id autogenerado.
    """
    conn = get_connection()
    cur = conn.cursor()

    datos = dict(bloqueo)
    cur.execute(
        """
        INSERT INTO bloqueos_agenda (
            motivo,
            fecha_hora_inicio,
            fecha_hora_fin
        ) VALUES (
            :motivo,
            :fecha_hora_inicio,
            :fecha_hora_fin
        );
        """,
        datos,
    )

    bloqueo_id = cur.lastrowid
    conn.commit()
    conn.close()
    return bloqueo_id


def listar_bloqueos_rango(fecha_inicio: str, fecha_fin: str) -> List[Any]:
    """
    Lista bloqueos entre dos fechas/horas (inclusive), ordenados por fecha_hora.
    Formato de fechas: 'YYYY-MM-DD HH:MM'
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM bloqueos_agenda
        WHERE NOT (fecha_hora_fin <= ? OR fecha_hora_inicio >= ?)
        ORDER BY fecha_hora_inicio;
        """,
        (fecha_inicio, fecha_fin),
    )

    filas = cur.fetchall()
    conn.close()
    return filas


def actualizar_bloqueo(bloqueo_id: int, datos: Dict[str, Any]) -> None:
    """
    Actualiza un bloqueo (solo motivo y fecha_hora por ahora).
    """
    conn = get_connection()
    cur = conn.cursor()

    params = dict(datos)
    params["id"] = bloqueo_id

    cur.execute(
        """
        UPDATE bloqueos_agenda
        SET motivo = :motivo,
            fecha_hora_inicio = :fecha_hora_inicio,
            fecha_hora_fin = :fecha_hora_fin
        WHERE id = :id;
        """,
        params,
    )

    conn.commit()
    conn.close()


def eliminar_bloqueo(bloqueo_id: int) -> None:
    """Elimina un bloqueo de agenda."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM bloqueos_agenda WHERE id = ?;",
        (bloqueo_id,),
    )

    conn.commit()
    conn.close()


def existe_bloqueo_en_rango(fecha_inicio: str, fecha_fin: str, bloqueo_id_excluir: Optional[int] = None) -> bool:
    """
    Devuelve True si existe algún bloqueo que se SOLAPE con el rango [fecha_inicio, fecha_fin).
    Formato: 'YYYY-MM-DD HH:MM'
    """
    conn = get_connection()
    cur = conn.cursor()

    if bloqueo_id_excluir is None:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM bloqueos_agenda
            WHERE NOT (fecha_hora_fin <= ? OR fecha_hora_inicio >= ?);
            """,
            (fecha_inicio, fecha_fin),
        )
    else:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM bloqueos_agenda
            WHERE NOT (fecha_hora_fin <= ? OR fecha_hora_inicio >= ?)
              AND id != ?;
            """,
            (fecha_inicio, fecha_fin, bloqueo_id_excluir),
        )

    count = cur.fetchone()[0]
    conn.close()
    return count > 0


def existe_bloqueo_en_fecha(fecha_hora: str, bloqueo_id_excluir: Optional[int] = None) -> bool:
    """
    Compat: considera un bloqueo de 1 hora a partir de fecha_hora.
    """
    # rango [fecha_hora, fecha_hora+60min)
    try:
        dt = datetime.strptime(fecha_hora[:16], "%Y-%m-%d %H:%M")
    except Exception:
        return False
    dt_fin = dt + timedelta(minutes=60)
    return existe_bloqueo_en_rango(dt.strftime("%Y-%m-%d %H:%M"), dt_fin.strftime("%Y-%m-%d %H:%M"), bloqueo_id_excluir)



def crear_servicio(nombre: str, modalidad: str, precio: float, empresa: str | None = None, activo: bool = True) -> int:
    """
    Crea un servicio. modalidad: 'particular' | 'convenio'. empresa solo para convenio.
    Devuelve el id del servicio creado.
    """
    nombre = (nombre or "").strip()
    modalidad = (modalidad or "").strip().lower()

    if modalidad not in ("particular", "convenio"):
        raise ValueError("Modalidad inválida. Debe ser 'particular' o 'convenio'.")

    if modalidad != "convenio":
        empresa = None
    else:
        empresa = (empresa or "").strip() or None

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO servicios (nombre, modalidad, precio, empresa, activo)
        VALUES (?, ?, ?, ?, ?);
        """,
        (nombre, modalidad, float(precio), empresa, 1 if activo else 0),
    )
    servicio_id = cur.lastrowid
    conn.commit()
    conn.close()
    return servicio_id


def listar_servicios(incluir_inactivos: bool = False) -> list[dict]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if incluir_inactivos:
        cur.execute("SELECT * FROM servicios ORDER BY nombre ASC;")
    else:
        cur.execute("SELECT * FROM servicios WHERE activo = 1 ORDER BY nombre ASC;")

    rows = cur.fetchall() or []
    conn.close()
    return [dict(r) for r in rows]


def actualizar_servicio(
    servicio_id: int,
    nombre: str,
    modalidad: str,
    precio: float,
    empresa: str | None,
    activo: bool,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE servicios
        SET nombre = ?, modalidad = ?, precio = ?, empresa = ?, activo = ?
        WHERE id = ?;
        """,
        (nombre, modalidad, precio, empresa, 1 if activo else 0, servicio_id),
    )
    conn.commit()
    conn.close()



def eliminar_servicio(servicio_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM servicios WHERE id = ?;", (servicio_id,))
    conn.commit()
    conn.close()


# ---------------- Empresas de convenio ----------------


def listar_empresas_convenio(activa_only: bool = True) -> List[Dict[str, Any]]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if activa_only:
        cur.execute(
            "SELECT * FROM empresas_convenio WHERE activa = 1 ORDER BY nombre;"
        )
    else:
        cur.execute("SELECT * FROM empresas_convenio ORDER BY nombre;")

    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def obtener_empresa_convenio(empresa_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM empresas_convenio WHERE id = ?;", (empresa_id,))
    row = cur.fetchone()
    conn.close()

    return dict(row) if row else None


def guardar_empresa_convenio(datos: Dict[str, Any]) -> int:
    """
    Crea o actualiza una empresa de convenio.
    Si datos["id"] existe, actualiza; si no, crea y devuelve el nuevo id.
    """
    conn = get_connection()
    cur = conn.cursor()

    if datos.get("id"):
        cur.execute(
            """
            UPDATE empresas_convenio
            SET nombre = ?, nit = ?, direccion = ?, ciudad = ?, pais = ?,
                telefono = ?, email_facturacion = ?, contacto = ?, activa = ?
            WHERE id = ?;
            """,
            (
                datos.get("nombre"),
                datos.get("nit"),
                datos.get("direccion"),
                datos.get("ciudad"),
                datos.get("pais"),
                datos.get("telefono"),
                datos.get("email_facturacion"),
                datos.get("contacto"),
                1 if datos.get("activa", True) else 0,
                datos["id"],
            ),
        )
        empresa_id = datos["id"]
    else:
        cur.execute(
            """
            INSERT INTO empresas_convenio (
                nombre, nit, direccion, ciudad, pais,
                telefono, email_facturacion, contacto, activa
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1);
            """,
            (
                datos.get("nombre"),
                datos.get("nit"),
                datos.get("direccion"),
                datos.get("ciudad"),
                datos.get("pais"),
                datos.get("telefono"),
                datos.get("email_facturacion"),
                datos.get("contacto"),
            ),
        )
        empresa_id = cur.lastrowid

    conn.commit()
    conn.close()
    return empresa_id

# ---------------- FACTURAS DE CONVENIO ----------------


def crear_factura_convenio(
    datos_cabecera: Dict[str, Any],
    items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Crea una factura de convenio (encabezado + detalle) y actualiza el consecutivo.

    datos_cabecera espera claves:
      - fecha (str 'YYYY-MM-DD')
      - empresa_id (int)
      - paciente_documento (str, opcional)
      - paciente_nombre (str)
      - forma_pago (str, opcional -> se puede tomar de configuracion_facturacion)
      - estado (str, opcional -> 'pendiente' por defecto)
      - total_letras (str, opcional -> "OCHENTA Y CINCO MIL PESOS", se implementará luego)

    items es una lista de dicts con:
      - descripcion (str)
      - cantidad (float/int)
      - valor_unitario (float)

    Devuelve dict con:
      {"id": factura_id, "numero": numero_factura, "subtotal": ..., "total": ...}
    """
    if not items:
        raise ValueError("La factura debe tener al menos un ítem de detalle.")

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        # --- Obtener / asegurar configuración de facturación en ESTA conexión ---
        cur.execute("SELECT * FROM configuracion_facturacion WHERE id = 1;")
        row_cfg = cur.fetchone()

        if row_cfg is None:
            cur.execute(
                """
                INSERT INTO configuracion_facturacion (
                    id, prefijo_factura, ultimo_consecutivo
                ) VALUES (1, 'PS', 0);
                """
            )
            conn.commit()
            cur.execute("SELECT * FROM configuracion_facturacion WHERE id = 1;")
            row_cfg = cur.fetchone()

        prefijo = row_cfg["prefijo_factura"]
        ultimo = row_cfg["ultimo_consecutivo"] or 0
        nuevo_consecutivo = ultimo + 1

        # PS0001, PS0002, ..., PS9999, PS10000, etc.
        numero_factura = f"{prefijo}{nuevo_consecutivo:04d}"

        # --- Calcular subtotal, iva, total ---
        subtotal = 0.0
        for it in items:
            cant = float(it.get("cantidad", 0) or 0)
            vu = float(it.get("valor_unitario", 0) or 0)
            subtotal += cant * vu

        iva = float(datos_cabecera.get("iva", 0) or 0)
        total = subtotal + iva

         # total_letras: si no viene en datos_cabecera, se calcula automáticamente
        total_letras = datos_cabecera.get("total_letras")
        if not total_letras:
            total_letras = total_a_letras_pesos(total)

        # --- Insertar encabezado ---
        forma_pago = datos_cabecera.get("forma_pago")
        estado = datos_cabecera.get("estado") or "pendiente"

        cur.execute(
            """
            INSERT INTO facturas_convenio (
                numero, fecha, empresa_id,
                paciente_documento, paciente_nombre,
                subtotal, iva, total,
                total_letras, forma_pago, estado, ruta_pdf, creada_en, actualizada_en
            ) VALUES (
                ?, ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?, ?, NULL, datetime('now','localtime'), NULL
            );
            """,
            (
                numero_factura,
                datos_cabecera["fecha"],
                datos_cabecera["empresa_id"],
                datos_cabecera.get("paciente_documento"),
                datos_cabecera.get("paciente_nombre"),
                subtotal,
                iva,
                total,
                total_letras,
                forma_pago,
                estado,
            ),
        )

        factura_id = cur.lastrowid

        # --- Insertar detalle ---
        for it in items:
            desc = it.get("descripcion") or ""
            cant = float(it.get("cantidad", 0) or 0)
            vu = float(it.get("valor_unitario", 0) or 0)
            vt = cant * vu

            cur.execute(
                """
                INSERT INTO facturas_convenio_detalle (
                    factura_id, descripcion, cantidad, valor_unitario, valor_total
                ) VALUES (?, ?, ?, ?, ?);
                """,
                (factura_id, desc, cant, vu, vt),
            )

        # --- Actualizar consecutivo ---
        cur.execute(
            """
            UPDATE configuracion_facturacion
            SET ultimo_consecutivo = ?
            WHERE id = 1;
            """,
            (nuevo_consecutivo,),
        )

        conn.commit()

        return {
            "id": factura_id,
            "numero": numero_factura,
            "subtotal": subtotal,
            "iva": iva,
            "total": total,
        }

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
        
def actualizar_factura_convenio(
    factura_id: int,
    datos_cabecera: Dict[str, Any],
    items: List[Dict[str, Any]],
) -> None:
    conn = get_connection()
    cur = conn.cursor()

    # 1) Update encabezado (NO toco numero si no quieres)
    cur.execute(
        """
        UPDATE facturas_convenio
        SET fecha = ?,
            empresa_id = ?,
            paciente_documento = ?,
            paciente_nombre = ?,
            subtotal = ?,
            iva = ?,
            total = ?,
            total_letras = ?,
            forma_pago = ?,
            estado = ?,
            actualizada_en = datetime('now','localtime')
        WHERE id = ?;
        """,
        (
            datos_cabecera.get("fecha"),
            datos_cabecera.get("empresa_id"),
            datos_cabecera.get("paciente_documento"),
            datos_cabecera.get("paciente_nombre"),
            datos_cabecera.get("subtotal", 0),
            datos_cabecera.get("iva", 0),
            datos_cabecera.get("total", 0),
            datos_cabecera.get("total_letras"),
            datos_cabecera.get("forma_pago"),
            datos_cabecera.get("estado", "pendiente"),
            factura_id,
        ),
    )

    # 2) Reemplazar detalle
    cur.execute("DELETE FROM facturas_convenio_detalle WHERE factura_id = ?;", (factura_id,))
    for it in items:
        cur.execute(
            """
            INSERT INTO facturas_convenio_detalle
              (factura_id, descripcion, cantidad, valor_unitario, valor_total)
            VALUES (?, ?, ?, ?, ?);
            """,
            (
                factura_id,
                it.get("descripcion"),
                it.get("cantidad", 1),
                it.get("valor_unitario", 0),
                it.get("valor_total", 0),
            ),
        )

    # 3) (Opcional pero recomendado) invalidar ruta_pdf para forzar regen
    cur.execute(
        """
        UPDATE facturas_convenio
        SET ruta_pdf = NULL, actualizada_en = datetime('now','localtime')
        WHERE id = ?;
        """,
        (factura_id,),
    )

    conn.commit()
    conn.close()
    
def eliminar_factura_convenio(factura_id: int, borrar_pdf: bool = True) -> None:
    # 1) buscar ruta_pdf antes de borrar
    factura = obtener_factura_convenio(factura_id)
    ruta_pdf = None
    if factura and factura.get("encabezado"):
        ruta_pdf = factura["encabezado"].get("ruta_pdf")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM facturas_convenio_detalle WHERE factura_id = ?;", (factura_id,))
    cur.execute("DELETE FROM facturas_convenio WHERE id = ?;", (factura_id,))
    conn.commit()
    conn.close()

    if borrar_pdf and ruta_pdf and os.path.exists(ruta_pdf):
        try:
            os.remove(ruta_pdf)
        except Exception:
            pass

# ---------------- Utilidades para facturación ----------------


def _numero_a_letras_es(n: int) -> str:
    """
    Convierte un entero positivo en su representación en letras en español, en MAYÚSCULAS.
    Soporta hasta millones (más que suficiente para el contexto de Sara).
    """
    if n == 0:
        return "CERO"
    if n < 0:
        return "MENOS " + _numero_a_letras_es(-n)

    unidades = [
        "",
        "UNO",
        "DOS",
        "TRES",
        "CUATRO",
        "CINCO",
        "SEIS",
        "SIETE",
        "OCHO",
        "NUEVE",
    ]
    especiales_10_19 = [
        "DIEZ",
        "ONCE",
        "DOCE",
        "TRECE",
        "CATORCE",
        "QUINCE",
        "DIECISEIS",
        "DIECISIETE",
        "DIECIOCHO",
        "DIECINUEVE",
    ]
    decenas = [
        "",
        "DIEZ",
        "VEINTE",
        "TREINTA",
        "CUARENTA",
        "CINCUENTA",
        "SESENTA",
        "SETENTA",
        "OCHENTA",
        "NOVENTA",
    ]
    centenas = [
        "",
        "CIENTO",
        "DOSCIENTOS",
        "TRESCIENTOS",
        "CUATROCIENTOS",
        "QUINIENTOS",
        "SEISCIENTOS",
        "SETECIENTOS",
        "OCHOCIENTOS",
        "NOVECIENTOS",
    ]

    def tres_cifras(num: int) -> str:
        c = num // 100
        r = num % 100
        d = r // 10
        u = r % 10
        palabras = []

        if num == 0:
            return ""
        if num == 100:
            return "CIEN"

        if c:
            palabras.append(centenas[c])

        if 10 <= r <= 19:
            palabras.append(especiales_10_19[r - 10])
        else:
            if d:
                if d == 2 and u != 0:
                    # 21-29: VEINTIUNO, VEINTIDOS, ...
                    palabras.append("VEINTI" + unidades[u])
                    u = 0
                else:
                    palabras.append(decenas[d])
            if u:
                if d >= 3:
                    palabras.append("Y")
                palabras.append(unidades[u])

        return " ".join(palabras)

    partes = []
    millones = n // 1_000_000
    miles = (n % 1_000_000) // 1000
    resto = n % 1000

    if millones:
        if millones == 1:
            partes.append("UN MILLON")
        else:
            partes.append(tres_cifras(millones) + " MILLONES")

    if miles:
        if miles == 1:
            partes.append("MIL")
        else:
            partes.append(tres_cifras(miles) + " MIL")

    if resto:
        partes.append(tres_cifras(resto))

    return " ".join(p for p in partes if p)


def total_a_letras_pesos(total: float) -> str:
    """
    Convierte un valor numérico a texto tipo:
    85000  -> 'OCHENTA Y CINCO MIL PESOS'
    110000 -> 'CIENTO DIEZ MIL PESOS'
    """
    entero = int(round(total or 0))
    return f"{_numero_a_letras_es(entero)} PESOS"


def obtener_factura_convenio(factura_id: int) -> Optional[Dict[str, Any]]:
    """
    Devuelve una factura con sus detalles:
      {
        "encabezado": {...},
        "detalles": [ {...}, {...}, ... ]
      }
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT f.*, e.nombre AS empresa_nombre, e.nit AS empresa_nit,
               e.direccion AS empresa_direccion, e.ciudad AS empresa_ciudad,
               e.pais AS empresa_pais, e.telefono AS empresa_telefono
        FROM facturas_convenio f
        JOIN empresas_convenio e ON e.id = f.empresa_id
        WHERE f.id = ?;
        """,
        (factura_id,),
    )
    enc = cur.fetchone()
    if enc is None:
        conn.close()
        return None

    cur.execute(
        """
        SELECT *
        FROM facturas_convenio_detalle
        WHERE factura_id = ?
        ORDER BY id;
        """,
        (factura_id,),
    )
    det_rows = cur.fetchall()
    conn.close()

    return {
        "encabezado": dict(enc),
        "detalles": [dict(d) for d in det_rows],
    }
    
def actualizar_ruta_pdf_factura_convenio(factura_id: int, ruta_pdf: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE facturas_convenio
        SET ruta_pdf = ?, actualizada_en = datetime('now','localtime')
        WHERE id = ?;
        """,
        (ruta_pdf, factura_id),
    )
    conn.commit()
    conn.close()


def listar_facturas_convenio(
    empresa_id: Optional[int] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Lista facturas de convenio con filtros opcionales:
      - empresa_id
      - fecha_desde / fecha_hasta (str 'YYYY-MM-DD')
    Ordenadas por fecha DESC, numero DESC.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    condiciones = []
    params: List[Any] = []

    if empresa_id is not None:
        condiciones.append("f.empresa_id = ?")
        params.append(empresa_id)

    if fecha_desde:
        condiciones.append("date(f.fecha) >= date(?)")
        params.append(fecha_desde)

    if fecha_hasta:
        condiciones.append("date(f.fecha) <= date(?)")
        params.append(fecha_hasta)

    where_clause = ""
    if condiciones:
        where_clause = "WHERE " + " AND ".join(condiciones)

    sql = f"""
        SELECT
            f.id,
            f.numero,
            f.fecha,
            f.empresa_id,
            e.nombre AS empresa_nombre,
            f.paciente_nombre,
            f.total,
            f.estado
        FROM facturas_convenio f
        JOIN empresas_convenio e ON e.id = f.empresa_id
        {where_clause}
        ORDER BY date(f.fecha) DESC, f.numero DESC;
    """
    cur.execute(sql, params)

    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def actualizar_estado_factura_convenio(factura_id: int, nuevo_estado: str) -> None:
    """
    Actualiza el estado de una factura de convenio:
    estados típicos: 'pendiente', 'pagada', 'anulada'
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE facturas_convenio
        SET estado = ?, actualizada_en = datetime('now','localtime')
        WHERE id = ?;
        """,
        (nuevo_estado, factura_id),
    )

    conn.commit()
    conn.close()

def eliminar_gasto_financiero(gasto_id: int) -> None:
    """
    Elimina un gasto financiero por id.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM gastos_financieros WHERE id = ?;",
        (gasto_id,),
    )

    conn.commit()
    conn.close()




# ===================== FINANZAS =====================


def registrar_gasto_financiero(gasto: Dict[str, Any]) -> None:
    """
    Registra un gasto financiero.

    Espera claves:
      - fecha (str 'YYYY-MM-DD')
      - tipo (str, ej: 'arriendo_consultorio', 'otro')
      - descripcion (str opcional)
      - monto (float positivo)
    """
    conn = get_connection()
    cur = conn.cursor()

    fecha = (gasto.get("fecha") or "").strip()
    if not fecha:
        # Si no viene fecha, usar hoy
        fecha = date.today().strftime("%Y-%m-%d")

    tipo = (gasto.get("tipo") or "otro").strip() or "otro"
    descripcion = (gasto.get("descripcion") or "").strip()
    monto = float(gasto.get("monto") or 0)

    cur.execute(
        """
        INSERT INTO gastos_financieros (fecha, tipo, descripcion, monto)
        VALUES (?, ?, ?, ?);
        """,
        (fecha, tipo, descripcion, monto),
    )

    conn.commit()
    conn.close()


def listar_gastos_financieros(
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    tipo: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Devuelve una lista de gastos financieros con filtros opcionales:
      - fecha_desde, fecha_hasta (str 'YYYY-MM-DD')
      - tipo (str)
    Ordenados por fecha ASC.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    condiciones = []
    params: List[Any] = []

    if fecha_desde:
        condiciones.append("date(fecha) >= date(?)")
        params.append(fecha_desde)

    if fecha_hasta:
        condiciones.append("date(fecha) <= date(?)")
        params.append(fecha_hasta)

    if tipo:
        condiciones.append("tipo = ?")
        params.append(tipo)

    where_clause = ""
    if condiciones:
        where_clause = "WHERE " + " AND ".join(condiciones)

    sql = f"""
        SELECT id, fecha, tipo, descripcion, monto
        FROM gastos_financieros
        {where_clause}
        ORDER BY date(fecha) ASC, id ASC;
    """

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    return [dict(r) for r in rows]


def _primer_y_ultimo_dia_mes(anio: int, mes: int) -> tuple[str, str]:
    """
    Devuelve (fecha_desde, fecha_hasta) del mes indicado en formato 'YYYY-MM-DD'.
    """
    primer_dia = date(anio, mes, 1)
    # calcular primer día del mes siguiente
    if mes == 12:
        siguiente_mes = date(anio + 1, 1, 1)
    else:
        siguiente_mes = date(anio, mes + 1, 1)

    ultimo_dia = siguiente_mes - timedelta(days=1)

    return (
        primer_dia.strftime("%Y-%m-%d"),
        ultimo_dia.strftime("%Y-%m-%d"),
    )


def resumen_financiero_periodo(fecha_desde: str, fecha_hasta: str) -> Dict[str, Any]:
    """
    Calcula un resumen financiero entre fecha_desde y fecha_hasta (incluidas).

    - Ingresos por citas particulares (virtual/presencial) que estén pagadas.
    - Conteo de citas de convenio.
    - Ingresos por facturas de convenio (por estado).
      * Para no duplicar ingresos, solo se toma el valor económico de las
        facturas de convenio, no el campo 'precio' de las citas de tipo
        'convenio_empresarial'.
    - Gastos (arriendo de consultorio y otros).
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ---- Ingresos por citas particulares (virtual/presencial) pagadas ----
    cur.execute(
        """
        SELECT
            canal,
            COUNT(*) AS cantidad,
            COALESCE(SUM(precio), 0) AS total
        FROM citas
        WHERE pagado = 1
        AND modalidad = 'particular'
        AND canal IN ('presencial', 'virtual')
        AND date(fecha_hora) BETWEEN date(?) AND date(?)
        GROUP BY canal;
        """,
        (fecha_desde, fecha_hasta),
    )
    filas_citas = cur.fetchall()

    ingresos_citas = {
        "presencial": {"cantidad": 0, "total": 0.0},
        "virtual": {"cantidad": 0, "total": 0.0},
    }

    for r in filas_citas:
        ch = r["canal"]
        if ch in ingresos_citas:
            ingresos_citas[ch]["cantidad"] = int(r["cantidad"] or 0)
            ingresos_citas[ch]["total"] = float(r["total"] or 0)

    # ---- Conteo de citas de convenio (solo conteo, no valor económico) ----
    cur.execute(
        """
        SELECT COUNT(*) AS cantidad
        FROM citas
        WHERE modalidad = 'convenio_empresarial'
          AND date(fecha_hora) BETWEEN date(?) AND date(?);
        """,
        (fecha_desde, fecha_hasta),
    )
    row_convenios_citas = cur.fetchone()
    cantidad_citas_convenio = int(row_convenios_citas["cantidad"] or 0)

    # ---- Facturas de convenio (ingresos por convenio) ----
    # Ignoramos las facturas anuladas para el cálculo de ingresos.
    cur.execute(
        """
        SELECT
            estado,
            COUNT(*) AS cantidad,
            COALESCE(SUM(total), 0) AS total
        FROM facturas_convenio
        WHERE estado != 'anulada'
          AND date(fecha) BETWEEN date(?) AND date(?)
        GROUP BY estado;
        """,
        (fecha_desde, fecha_hasta),
    )
    filas_facturas = cur.fetchall()

    facturas_por_estado: Dict[str, Dict[str, Any]] = {}
    total_facturas_emitidas = 0.0
    total_facturas_pagadas = 0.0

    for r in filas_facturas:
        estado = (r["estado"] or "").lower()
        cantidad = int(r["cantidad"] or 0)
        total = float(r["total"] or 0)

        facturas_por_estado[estado] = {"cantidad": cantidad, "total": total}
        total_facturas_emitidas += total
        if estado == "pagada":
            total_facturas_pagadas += total

    # Defaults (después del loop)
    facturas_por_estado.setdefault("pagada", {"cantidad": 0, "total": 0.0})
    facturas_por_estado.setdefault("pendiente", {"cantidad": 0, "total": 0.0})

    cantidad_facturas_pagadas = int(facturas_por_estado["pagada"]["cantidad"] or 0)
    cantidad_facturas_pendientes = int(facturas_por_estado["pendiente"]["cantidad"] or 0)
    total_facturas_pendientes = float(facturas_por_estado["pendiente"]["total"] or 0)
    cantidad_facturas_emitidas = sum(int(v.get("cantidad") or 0) for v in facturas_por_estado.values())

    # ---- Gastos financieros ----
    cur.execute(
        """
        SELECT
            tipo,
            COALESCE(SUM(monto), 0) AS total
        FROM gastos_financieros
        WHERE date(fecha) BETWEEN date(?) AND date(?)
        GROUP BY tipo;
        """,
        (fecha_desde, fecha_hasta),
    )
    filas_gastos = cur.fetchall()
    conn.close()
    
     # ---- Paquetes de consultorio comprados (se consideran GASTO) ----
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            COUNT(*) AS cantidad,
            COALESCE(SUM(precio_total), 0) AS total
        FROM paquetes_consultorio
        WHERE date(fecha_compra) BETWEEN date(?) AND date(?);
        """,
        (fecha_desde, fecha_hasta),
    )
    row_pkg = cur.fetchone()
    
    cur.execute(
        """
        SELECT COALESCE(SUM(costo_total), 0) AS total
        FROM paquetes_arriendo
        WHERE date(fecha_compra) BETWEEN date(?) AND date(?);
        """,
        (fecha_desde, fecha_hasta),
    )
    row_paq = cur.fetchone()
    total_paquetes_arriendo = float((row_paq["total"] if row_paq else 0) or 0)
    
    conn.close()
    
    # ---- KPI Bolsillo próximo paquete (consumo de citas de paquetes) ----
    # Se calcula como la suma del costo promedio por cita de cada consumo registrado
    # (NO afecta utilidad neta; es informativo).
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            COUNT(*) AS cantidad_consumos,
            COALESCE(SUM(
                CASE
                    WHEN p.cantidad_citas > 0 THEN (p.costo_total * 1.0 / p.cantidad_citas)
                    ELSE 0
                END
            ), 0) AS bolsillo_total
        FROM consumo_paquetes_arriendo c
        JOIN paquetes_arriendo p ON p.id = c.paquete_id
        WHERE date(c.fecha_consumo) BETWEEN date(?) AND date(?);
        """,
        (fecha_desde, fecha_hasta),
    )
    row_bolsillo = cur.fetchone()
    conn.close()

    bolsillo_proximo_paquete = float((row_bolsillo["bolsillo_total"] if row_bolsillo else 0) or 0)
    cantidad_consumos_paquete = int((row_bolsillo["cantidad_consumos"] if row_bolsillo else 0) or 0)

    total_paquetes = float((row_pkg["total"] if row_pkg else 0) or 0)

    gastos_por_tipo: Dict[str, float] = {}
    total_gastos = 0.0

    for r in filas_gastos:
        tipo = r["tipo"]
        total = float(r["total"] or 0)
        gastos_por_tipo[tipo] = total
        total_gastos += total
        
    # Agregar paquetes de consultorio como gasto
    if total_paquetes > 0:
        gastos_por_tipo["paquetes_consultorio"] = total_paquetes
        total_gastos += total_paquetes
        
    if total_paquetes_arriendo > 0:
        gastos_por_tipo["paquetes_arriendo"] = total_paquetes_arriendo
        total_gastos += total_paquetes_arriendo

    total_presencial = ingresos_citas["presencial"]["total"]
    total_virtual = ingresos_citas["virtual"]["total"]
    total_citas_particulares = total_presencial + total_virtual

    total_ingresos_cobrados = total_citas_particulares + total_facturas_pagadas
    total_ingresos_facturados = total_citas_particulares + total_facturas_emitidas

    utilidad_neta_cobrada = total_ingresos_cobrados - total_gastos
    utilidad_neta_facturada = total_ingresos_facturados - total_gastos
    
    

    return {
        "rango": {
            "desde": fecha_desde,
            "hasta": fecha_hasta,
        },
        "ingresos": {
            "citas": {
                "presencial": ingresos_citas["presencial"],
                "virtual": ingresos_citas["virtual"],
                "total_particulares": total_citas_particulares,
                "cantidad_citas_pagadas": int(
                    ingresos_citas["presencial"]["cantidad"] + ingresos_citas["virtual"]["cantidad"]
                ),
            },
            "convenios": {
                "cantidad_citas": cantidad_citas_convenio,
                "facturas_por_estado": facturas_por_estado,
                "total_facturas_emitidas": total_facturas_emitidas,
                "total_facturas_pagadas": total_facturas_pagadas,
                
                "cantidad_facturas_emitidas": cantidad_facturas_emitidas,
                "cantidad_facturas_pagadas": cantidad_facturas_pagadas,
                "cantidad_facturas_pendientes": cantidad_facturas_pendientes,
                "total_facturas_pendientes": total_facturas_pendientes,
            },
            "total_cobrado": total_ingresos_cobrados,
            "total_facturado": total_ingresos_facturados,
        },
        "gastos": {
            "por_tipo": gastos_por_tipo,
            "total_gastos": total_gastos,
        },
        "utilidad": {
            "neta_cobrada": utilidad_neta_cobrada,
            "neta_facturada": utilidad_neta_facturada,
        },
        "kpis": {
            "bolsillo_proximo_paquete": bolsillo_proximo_paquete,
            "citas_consumidas_de_paquete": cantidad_consumos_paquete,
        },
    }


def resumen_financiero_mensual(anio: int, mes: int) -> Dict[str, Any]:
    """
    Atajo para obtener el resumen financiero de un mes específico.
    """
    desde, hasta = _primer_y_ultimo_dia_mes(anio, mes)
    data = resumen_financiero_periodo(desde, hasta)
    data["periodo"] = {"anio": anio, "mes": mes}
    return data


# =========================================================
#  FINANZAS: GASTOS Y RESUMEN MENSUAL
# =========================================================

def registrar_gasto_financiero(gasto: Dict[str, Any]) -> int:
    """
    Registra un gasto financiero en la tabla gastos_financieros.

    gasto debe tener:
      - fecha: 'YYYY-MM-DD'
      - tipo: 'arriendo_consultorio', 'otro', etc.
      - descripcion: texto (puede ser None)
      - monto: float (positivo)
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO gastos_financieros (fecha, tipo, descripcion, monto)
        VALUES (:fecha, :tipo, :descripcion, :monto);
        """,
        gasto,
    )
    conn.commit()
    gasto_id = cur.lastrowid
    conn.close()
    return gasto_id


def _rango_mes(anio: int, mes: int) -> Dict[str, str]:
    """
    Devuelve {'desde': 'YYYY-MM-DD', 'hasta': 'YYYY-MM-DD'} para el mes completo.
    """
    inicio = date(anio, mes, 1)
    if mes == 12:
        siguiente = date(anio + 1, 1, 1)
    else:
        siguiente = date(anio, mes + 1, 1)

    fin = siguiente - timedelta(days=1)

    return {
        "desde": inicio.strftime("%Y-%m-%d"),
        "hasta": fin.strftime("%Y-%m-%d"),
    }


def resumen_financiero_mensual_legacy(anio: int, mes: int) -> Dict[str, Any]:
    """
    Calcula el resumen financiero del mes usando el modelo ACTUAL:

      - Ingresos por citas particulares (virtual / presencial) pagadas
        (modalidad = 'virtual' o 'presencial', pagado = 1).

      - Convenios:
        * cantidad de citas modalidad = 'convenio_empresarial' (carga de trabajo)
        * facturas de convenio (tabla facturas_convenio) agrupadas por estado.

      - Gastos:
        * de la tabla gastos_financieros, por tipo y total.

      - Utilidad:
        * ingresos_brutos        = particulares + total_facturas_emitidas
        * ingresos_cobrados      = particulares + facturas estado 'pagada'
        * utilidad_neta_cobrada  = ingresos_cobrados - total_gastos
    """
    rango = _rango_mes(anio, mes)
    f_desde = rango["desde"]
    f_hasta = rango["hasta"]

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ----- Citas particulares pagadas (virtual + presencial) -----
    cur.execute(
        """
        SELECT
            canal,
            COUNT(*) AS cantidad,
            IFNULL(SUM(precio), 0) AS total
        FROM citas
        WHERE date(fecha_hora) BETWEEN ? AND ?
        AND pagado = 1
        AND modalidad = 'particular'
        AND canal IN ('presencial', 'virtual')
        GROUP BY canal;
        """,
        (f_desde, f_hasta),
    )
    filas_citas = cur.fetchall()

    citas_presencial = {"cantidad": 0, "total": 0.0}
    citas_virtual = {"cantidad": 0, "total": 0.0}

    for fila in filas_citas:
        canal = fila["canal"]
        if canal == "presencial":
            citas_presencial["cantidad"] = fila["cantidad"]
            citas_presencial["total"] = float(fila["total"] or 0)
        elif canal == "virtual":
            citas_virtual["cantidad"] = fila["cantidad"]
            citas_virtual["total"] = float(fila["total"] or 0)

    total_particulares = citas_presencial["total"] + citas_virtual["total"]
    cantidad_citas_pagadas = (
        citas_presencial["cantidad"] + citas_virtual["cantidad"]
    )
    

    # ----- Citas de convenio en el mes (carga de trabajo) -----
    cur.execute(
        """
        SELECT COUNT(*) AS cantidad
        FROM citas
        WHERE date(fecha_hora) BETWEEN ? AND ?
          AND modalidad = 'convenio_empresarial';
        """,
        (f_desde, f_hasta),
    )
    fila_conv = cur.fetchone()
    cantidad_citas_convenio = int(fila_conv["cantidad"] or 0) if fila_conv else 0

    # ----- Facturas de convenio emitidas en el mes -----
    cur.execute(
        """
        SELECT estado,
               COUNT(*)             AS cantidad,
               IFNULL(SUM(total),0) AS total
        FROM facturas_convenio
        WHERE date(fecha) BETWEEN ? AND ?
        GROUP BY estado;
        """,
        (f_desde, f_hasta),
    )
    filas_facturas = cur.fetchall()

    facturas_por_estado: Dict[str, Dict[str, Any]] = {}
    total_facturas_emitidas = 0.0
    total_facturas_pagadas = 0.0

    for fila in filas_facturas:
        estado = fila["estado"]
        cantidad = int(fila["cantidad"] or 0)
        total = float(fila["total"] or 0)

        facturas_por_estado[estado] = {
            "cantidad": cantidad,
            "total": total,
        }

        total_facturas_emitidas += total
        if estado == "pagada":
            total_facturas_pagadas += total

    # ----- Gastos del mes -----
    cur.execute(
        """
        SELECT tipo,
               IFNULL(SUM(monto),0) AS total
        FROM gastos_financieros
        WHERE fecha BETWEEN ? AND ?
        GROUP BY tipo;
        """,
        (f_desde, f_hasta),
    )
    filas_gastos = cur.fetchall()
    # ----- Paquetes de arriendo comprados en el mes (se consideran GASTO) -----
    cur.execute(
        """
        SELECT IFNULL(SUM(costo_total), 0) AS total
        FROM paquetes_arriendo
        WHERE date(fecha_compra) BETWEEN date(?) AND date(?);
        """,
        (f_desde, f_hasta),
    )
    row_pkg = cur.fetchone()
    total_paquetes_arriendo = float((row_pkg["total"] if row_pkg else 0) or 0)
    conn.close()

    gastos_por_tipo: Dict[str, float] = {}
    total_gastos = 0.0

    for fila in filas_gastos:
        tipo = fila["tipo"]
        total = float(fila["total"] or 0)
        gastos_por_tipo[tipo] = total
        total_gastos += total
        
        # Agregar paquetes de arriendo como gasto
    if total_paquetes_arriendo > 0:
        gastos_por_tipo["paquetes_arriendo"] = total_paquetes_arriendo
        total_gastos += total_paquetes_arriendo

    # ----- Utilidad -----
    ingresos_brutos = total_particulares + total_facturas_emitidas
    ingresos_cobrados = total_particulares + total_facturas_pagadas
    utilidad_neta_cobrada = ingresos_cobrados - total_gastos

    return {
        "rango": rango,
        "ingresos": {
            "citas": {
                "presencial": citas_presencial,
                "virtual": citas_virtual,
                "total_particulares": total_particulares,
                "cantidad_citas_pagadas": int(
                    citas_presencial["cantidad"] + citas_virtual["cantidad"]
                ),
            },
            "convenios": {
                "cantidad_citas": cantidad_citas_convenio,
                "facturas_por_estado": facturas_por_estado,
                "total_facturas_emitidas": total_facturas_emitidas,
                "total_facturas_pagadas": total_facturas_pagadas,
            },
        },
        "gastos": {
            "por_tipo": gastos_por_tipo,
            "total_gastos": total_gastos,
        },
        "utilidad": {
            "bruta": ingresos_brutos,
            "cobrada": ingresos_cobrados,
            "neta_cobrada": utilidad_neta_cobrada,
        },
    }

# ===================== PAQUETES DE CONSULTORIO =====================

def crear_paquete_consultorio(datos):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO paquetes_consultorio (
            fecha_compra, descripcion, precio_total,
            cantidad_sesiones, sesiones_restantes, activo
        )
        VALUES (?, ?, ?, ?, ?, 1)
    """, (
        datos["fecha_compra"],
        datos.get("descripcion", ""),
        datos["precio_total"],
        datos["cantidad_sesiones"],
        datos["cantidad_sesiones"],  # sesiones restantes iniciales
    ))

    conn.commit()
    conn.close()

def obtener_paquete_activo():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM paquetes_consultorio
        WHERE activo = 1
        ORDER BY id DESC
        LIMIT 1
    """)

    row = cur.fetchone()
    conn.close()
    return row

def consumir_sesion_paquete(paquete_id, cita_id, fecha):
    conn = get_connection()
    cur = conn.cursor()

    # Registrar consumo
    cur.execute("""
        INSERT INTO consumo_paquetes (paquete_id, cita_id, fecha)
        VALUES (?, ?, ?)
    """, (paquete_id, cita_id, fecha))

    # Restar sesión
    cur.execute("""
        UPDATE paquetes_consultorio
        SET sesiones_restantes = sesiones_restantes - 1
        WHERE id = ?
    """, (paquete_id,))

    conn.commit()
    conn.close()


def registrar_paquete_arriendo(datos: dict):
    """
    Registra un paquete de arriendo de consultorio.
    datos = {
        'fecha_compra': 'YYYY-MM-DD',
        'cantidad_citas': int,
        'precio_total': float,
        'descripcion': str
    }
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO paquetes_arriendo (
            fecha_compra,
            cantidad_citas,
            costo_total,
            notas,
            citas_usadas
        )
        VALUES (?, ?, ?, ?, 0)
        """,
        (
            datos["fecha_compra"],
            datos["cantidad_citas"],
            datos["precio_total"],
            datos.get("descripcion", ""),
        ),
    )

    conn.commit()
    conn.close()
    
def listar_paquetes_arriendo(solo_activos: bool = False) -> list[dict]:
    """
    Lista paquetes de arriendo (para mostrar/editar/eliminar en UI).

    - solo_activos=False (default): devuelve TODOS (incluye consumidos) -> no rompe llamadas existentes.
    - solo_activos=True: devuelve solo los que aún tienen citas disponibles.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    where = ""
    if solo_activos:
        # disponibles = cantidad_citas - citas_usadas > 0
        where = "WHERE (cantidad_citas - citas_usadas) > 0"

    cur.execute(f"""
        SELECT
            id,
            fecha_compra,
            cantidad_citas,
            citas_usadas,
            costo_total,
            notas
        FROM paquetes_arriendo
        {where}
        ORDER BY date(fecha_compra) DESC, id DESC;
    """)

    filas = cur.fetchall()
    conn.close()

    return [
        {
            "id": int(r["id"]),
            "fecha_compra": r["fecha_compra"],
            "cantidad_citas": int(r["cantidad_citas"] or 0),
            "citas_usadas": int(r["citas_usadas"] or 0),
            "costo_total": float(r["costo_total"] or 0),
            "notas": (r["notas"] or ""),
        }
        for r in filas
    ]



def obtener_paquete_arriendo(paquete_id: int) -> dict | None:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id, fecha_compra, cantidad_citas, citas_usadas, costo_total, notas
        FROM paquetes_arriendo
        WHERE id = ?;
    """, (paquete_id,))

    r = cur.fetchone()
    conn.close()

    if not r:
        return None

    return {
        "id": int(r["id"]),
        "fecha_compra": r["fecha_compra"],
        "cantidad_citas": int(r["cantidad_citas"] or 0),
        "citas_usadas": int(r["citas_usadas"] or 0),
        "costo_total": float(r["costo_total"] or 0),
        "notas": (r["notas"] or ""),
    }


def actualizar_paquete_arriendo(paquete_id: int, datos: dict) -> None:
    """
    datos esperados:
      - fecha_compra (YYYY-MM-DD)
      - cantidad_citas (int)
      - precio_total (float)
      - descripcion (str)
    Regla: si reduces cantidad_citas por debajo de citas_usadas -> error.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT citas_usadas FROM paquetes_arriendo WHERE id = ?;", (paquete_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError("El paquete no existe.")

    usadas = int(row["citas_usadas"] or 0)
    nuevas_totales = int(datos["cantidad_citas"])

    if nuevas_totales < usadas:
        conn.close()
        raise ValueError(
            f"No puedes dejar el paquete con {nuevas_totales} citas si ya hay {usadas} consumidas."
        )

    cur.execute("""
        UPDATE paquetes_arriendo
        SET
            fecha_compra = ?,
            cantidad_citas = ?,
            costo_total = ?,
            notas = ?
        WHERE id = ?;
    """, (
        datos["fecha_compra"],
        nuevas_totales,
        float(datos["precio_total"]),
        (datos.get("descripcion") or ""),
        paquete_id
    ))

    conn.commit()
    conn.close()


def eliminar_paquete_arriendo(paquete_id: int) -> None:
    """
    Elimina paquete y sus consumos asociados.
    Como la BD está vacía/de prueba, esto es seguro y mantiene coherencia.
    """
    conn = get_connection()
    cur = conn.cursor()

    # borrar consumos primero (por si no tienes ON DELETE CASCADE)
    cur.execute("DELETE FROM consumo_paquetes_arriendo WHERE paquete_id = ?;", (paquete_id,))
    cur.execute("DELETE FROM paquetes_arriendo WHERE id = ?;", (paquete_id,))

    conn.commit()
    conn.close()

def resumen_paquetes_arriendo(solo_activos: bool = False) -> dict:
    """
    Retorna:
      - total_citas
      - citas_usadas
      - citas_disponibles
      - costo_total
      - costo_promedio_cita (si aplica)
    Si solo_activos=True, solo suma paquetes con disponibles > 0.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Usadas por paquete = count(consumos)
    where_activos = ""
    if solo_activos:
        # disponibles = cantidad_citas - usadas > 0
        where_activos = """
        WHERE (pa.cantidad_citas - IFNULL(u.usadas,0)) > 0
        """

    cur.execute(
        f"""
        SELECT
            IFNULL(SUM(pa.cantidad_citas), 0) AS total_citas,
            IFNULL(SUM(IFNULL(u.usadas,0)), 0) AS citas_usadas,
            IFNULL(SUM(CASE 
                WHEN (pa.cantidad_citas - IFNULL(u.usadas,0)) > 0 THEN (pa.cantidad_citas - IFNULL(u.usadas,0))
                ELSE 0
            END), 0) AS citas_disponibles,

            IFNULL(SUM(pa.costo_total), 0) AS costo_total
        FROM paquetes_arriendo pa
        LEFT JOIN (
            SELECT paquete_id, COUNT(*) AS usadas
            FROM consumo_paquetes_arriendo
            GROUP BY paquete_id
        ) u ON u.paquete_id = pa.id
        {where_activos};
        """
    )

    row = cur.fetchone() or {}
    conn.close()

    total_citas = int(row["total_citas"] or 0)
    costo_total = float(row["costo_total"] or 0)
    costo_promedio = (costo_total / total_citas) if total_citas > 0 else 0.0

    return {
        "total_citas": total_citas,
        "citas_usadas": int(row["citas_usadas"] or 0),
        "citas_disponibles": int(row["citas_disponibles"] or 0),
        "costo_total": costo_total,
        "costo_promedio_cita": costo_promedio,
    }

def listar_consumos_paquetes_arriendo(fecha_desde: str, fecha_hasta: str):
    """
    Retorna consumos de paquetes en un rango (para tabla informativa en Finanzas).
    Cada consumo corresponde a 1 cita presencial (normalmente).
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            cpa.id                 AS consumo_id,
            cpa.fecha_consumo      AS fecha_consumo,
            cpa.cita_id            AS cita_id,
            cpa.paquete_id         AS paquete_id,
            cpa.consumido_por      AS consumido_por,

            p.nombre_completo      AS paciente_nombre,
            ci.canal               AS canal,
            ci.modalidad           AS modalidad,

            pa.costo_total         AS paquete_costo_total,
            pa.cantidad_citas      AS paquete_cantidad_citas,

            (pa.costo_total * 1.0 / pa.cantidad_citas) AS costo_promedio_cita
        FROM consumo_paquetes_arriendo cpa
        JOIN citas ci
            ON ci.id = cpa.cita_id
        JOIN pacientes p
            ON p.documento = ci.documento_paciente
        JOIN paquetes_arriendo pa
            ON pa.id = cpa.paquete_id
        WHERE date(cpa.fecha_consumo) BETWEEN ? AND ?
        ORDER BY cpa.fecha_consumo ASC, cpa.id ASC;
        """,
        (fecha_desde, fecha_hasta),
    )

    filas = cur.fetchall()
    conn.close()

    return [
        {
            "consumo_id": int(r["consumo_id"]),
            "fecha_consumo": r["fecha_consumo"],
            "cita_id": int(r["cita_id"]),
            "paquete_id": int(r["paquete_id"]),
            "consumido_por": (r["consumido_por"] or ""),
            "paciente_nombre": (r["paciente_nombre"] or ""),
            "canal": (r["canal"] or ""),
            "modalidad": (r["modalidad"] or ""),
            "costo_promedio_cita": float(r["costo_promedio_cita"] or 0),
        }
        for r in filas
    ]
    
#==================== Descontar Paquetes para citas presenciales =====================

def _obtener_paquete_arriendo_disponible(cur):
    cur.execute("""
        SELECT *
        FROM paquetes_arriendo
        WHERE (cantidad_citas - citas_usadas) > 0
        ORDER BY date(fecha_compra) DESC, id DESC
        LIMIT 1;
    """)
    return cur.fetchone()


def consumir_cita_paquete_arriendo(cita_id: int, fecha_consumo: str) -> bool:
    """
    Descuenta 1 cita del paquete (si hay disponible) y registra el consumo ligado a cita_id.
    Retorna True si consumió, False si no había paquete disponible o ya estaba consumida.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Si ya consumió antes, no hacemos nada
    cur.execute("SELECT 1 FROM consumo_paquetes_arriendo WHERE cita_id = ?;", (cita_id,))
    if cur.fetchone():
        conn.close()
        return False

    paquete = _obtener_paquete_arriendo_disponible(cur)
    if not paquete:
        conn.close()
        return False

    # Marcar consumo (1) y subir citas_usadas
    cur.execute("""
        INSERT INTO consumo_paquetes_arriendo (paquete_id, cita_id, fecha_consumo)
        VALUES (?, ?, ?);
    """, (paquete["id"], cita_id, fecha_consumo))

    cur.execute("""
        UPDATE paquetes_arriendo
        SET citas_usadas = citas_usadas + 1
        WHERE id = ?;
    """, (paquete["id"],))

    conn.commit()
    conn.close()
    return True


def devolver_cita_paquete_arriendo(cita_id: int) -> bool:
    """
    Devuelve 1 cita al paquete si existía consumo asociado a cita_id.
    Retorna True si devolvió, False si no había consumo.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT paquete_id
        FROM consumo_paquetes_arriendo
        WHERE cita_id = ?;
    """, (cita_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False

    paquete_id = row["paquete_id"]

    # borrar consumo y restar usadas (sin bajar de 0)
    cur.execute("DELETE FROM consumo_paquetes_arriendo WHERE cita_id = ?;", (cita_id,))
    cur.execute("""
        UPDATE paquetes_arriendo
        SET citas_usadas = CASE WHEN citas_usadas > 0 THEN citas_usadas - 1 ELSE 0 END
        WHERE id = ?;
    """, (paquete_id,))

    conn.commit()
    conn.close()
    return True


# ------------ CONFIGURACIÓN FACTURACIÓN -------------

def obtener_configuracion_facturacion() -> dict:
    """
    Devuelve la configuración de facturación (prefijo, consecutivo, datos bancarios).
    Si no existe el registro id=1, lo crea con valores por defecto.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM configuracion_facturacion WHERE id = 1;")
    row = cur.fetchone()

    if row is None:
        cur.execute(
            """
            INSERT INTO configuracion_facturacion (id, prefijo_factura, ultimo_consecutivo)
            VALUES (1, 'PS', 0);
            """
        )
        conn.commit()
        cur.execute("SELECT * FROM configuracion_facturacion WHERE id = 1;")
        row = cur.fetchone()

    cfg = {
        "prefijo_factura": row["prefijo_factura"],
        "ultimo_consecutivo": row["ultimo_consecutivo"],
        "banco": row["banco"],
        "beneficiario": row["beneficiario"],
        "nit": row["nit"],
        "numero_cuenta": row["numero_cuenta"],
        "forma_pago": row["forma_pago"],
        "notas": row["notas"],
    }

    conn.close()
    return cfg


def guardar_configuracion_facturacion(cfg: dict) -> None:
    """
    Actualiza la configuración de facturación (siempre id=1).
    Espera claves:
      prefijo_factura, ultimo_consecutivo, banco, beneficiario, nit,
      numero_cuenta, forma_pago, notas
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO configuracion_facturacion (
            id, prefijo_factura, ultimo_consecutivo,
            banco, beneficiario, nit, numero_cuenta, forma_pago, notas
        )
        VALUES (
            1, :prefijo_factura, :ultimo_consecutivo,
            :banco, :beneficiario, :nit, :numero_cuenta, :forma_pago, :notas
        )
        ON CONFLICT(id) DO UPDATE SET
            prefijo_factura     = excluded.prefijo_factura,
            ultimo_consecutivo  = excluded.ultimo_consecutivo,
            banco               = excluded.banco,
            beneficiario        = excluded.beneficiario,
            nit                 = excluded.nit,
            numero_cuenta       = excluded.numero_cuenta,
            forma_pago          = excluded.forma_pago,
            notas               = excluded.notas;
        """,
        {
            "prefijo_factura": cfg.get("prefijo_factura", "PS"),
            "ultimo_consecutivo": int(cfg.get("ultimo_consecutivo", 0) or 0),
            "banco": cfg.get("banco"),
            "beneficiario": cfg.get("beneficiario"),
            "nit": cfg.get("nit"),
            "numero_cuenta": cfg.get("numero_cuenta"),
            "forma_pago": cfg.get("forma_pago"),
            "notas": cfg.get("notas"),
        },
    )

    conn.commit()
    conn.close()


# ------------ CONFIGURACIÓN GMAIL -------------

def obtener_configuracion_gmail() -> dict:
    """
    Devuelve la configuración de Gmail para envío de correos.
    Si no existe el registro id=1, lo crea con valores por defecto.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM configuracion_gmail WHERE id = 1;")
    row = cur.fetchone()

    if row is None:
        cur.execute(
            """
            INSERT INTO configuracion_gmail (id, gmail_user, gmail_app_password, habilitado)
            VALUES (1, NULL, NULL, 0);
            """
        )
        conn.commit()
        cur.execute("SELECT * FROM configuracion_gmail WHERE id = 1;")
        row = cur.fetchone()

    cfg = {
        "gmail_user": row["gmail_user"],
        "gmail_app_password": row["gmail_app_password"],  # OJO: cifrado (enc::...) o plano legacy
        "habilitado": bool(row["habilitado"]),
        "tiene_password": bool(row["gmail_app_password"]),
    }

    conn.close()
    return cfg


def guardar_configuracion_gmail(cfg: dict) -> None:
    """
    Guarda la configuración de Gmail (siempre id=1).
    - gmail_user: correo gmail
    - gmail_app_password: clave de aplicación (se guarda cifrada).
      Si viene vacío/None, se conserva la clave existente.
    - habilitado: bool (si no viene, se habilita solo si hay user+password)
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM configuracion_gmail WHERE id = 1;")
    actual = cur.fetchone()

    gmail_user = (cfg.get("gmail_user") or "").strip() or None
    new_password = (cfg.get("gmail_app_password") or "").strip() or None

    # Si el usuario no escribió una nueva, preservamos la existente
    if not new_password and actual is not None:
        new_password = actual["gmail_app_password"]

    # Cifrar si es nueva y aún no está cifrada
    if new_password and not str(new_password).startswith("enc::"):
        from .crypto_utils import encrypt_str
        new_password = encrypt_str(str(new_password))

    habilitado = cfg.get("habilitado")
    if habilitado is None:
        habilitado = 1 if (gmail_user and new_password) else 0
    else:
        habilitado = 1 if bool(habilitado) else 0

    if actual is None:
        cur.execute(
            """
            INSERT INTO configuracion_gmail (id, gmail_user, gmail_app_password, habilitado)
            VALUES (1, ?, ?, ?);
            """,
            (gmail_user, new_password, habilitado),
        )
    else:
        cur.execute(
            """
            UPDATE configuracion_gmail
            SET gmail_user = ?,
                gmail_app_password = ?,
                habilitado = ?
            WHERE id = 1;
            """,
            (gmail_user, new_password, habilitado),
        )

    conn.commit()
    conn.close()
    
def obtener_cita_con_paciente(cita_id: int):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            c.*,
            p.nombre_completo,
            p.indicativo_pais,
            p.telefono,
            p.email
        FROM citas c
        JOIN pacientes p ON p.documento = c.documento_paciente
        WHERE c.id = ?
        LIMIT 1;
        """,
        (int(cita_id),),
    )
    row = cur.fetchone()
    conn.close()
    return row

def listar_citas_por_paciente(documento_paciente: str) -> List[sqlite3.Row]:
    """
    Lista citas de un paciente, ordenadas por fecha/hora descendente (más reciente primero).
    Devuelve sqlite3.Row con columnas de la tabla citas.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM citas
        WHERE documento_paciente = ?
        ORDER BY datetime(fecha_hora) DESC, id DESC;
        """,
        (documento_paciente,),
    )

    filas = cur.fetchall()
    conn.close()
    return filas

####### Funciones para documentos PDF #######

def upsert_documento_generado(tipo: str, documento_paciente: str, path: str, cita_id: int | None = None) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO documentos_generados (tipo, documento_paciente, cita_id, path, updated_at)
        VALUES (?, ?, ?, ?, datetime('now','localtime'))
        ON CONFLICT(tipo, documento_paciente, cita_id) DO UPDATE SET
            path = excluded.path,
            updated_at = datetime('now','localtime');
        """,
        (tipo, documento_paciente, cita_id, path),
    )
    conn.commit()
    conn.close()


def get_documento_generado(tipo: str, documento_paciente: str, cita_id: int | None = None) -> str | None:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT path
        FROM documentos_generados
        WHERE tipo = ? AND documento_paciente = ? AND
              ( (cita_id IS NULL AND ? IS NULL) OR (cita_id = ?) )
        ORDER BY updated_at DESC
        LIMIT 1;
        """,
        (tipo, documento_paciente, cita_id, cita_id),
    )
    row = cur.fetchone()
    conn.close()
    return row["path"] if row else None





# ------------ FIN -------------



if __name__ == "__main__":
    print(f"Inicializando base de datos en: {DB_PATH}")
    init_db()
    print("Tablas listas.")

    # ---------------- Datos de prueba (idempotentes) ----------------
    # try:
    #     conn = get_connection()
    #     cur = conn.cursor()

    #     # Profesional (config id=1)
    #     cur.execute(
    #         """
    #         INSERT OR IGNORE INTO configuracion_profesional (id, nombre_profesional, hora_inicio, hora_fin, dias_atencion, direccion, zona_horaria, telefono, email)
    #         VALUES (1, 'Sara Psicóloga', '08:00', '18:00', 'Lunes,Martes,Miercoles,Jueves,Viernes', 'Consultorio', 'America/Bogota', '', '');
    #         """
    #     )

    #     # Empresa convenio de prueba
    #     cur.execute(
    #         "INSERT OR IGNORE INTO empresas_convenio (nombre) VALUES ('Empresa Prueba S.A');"
    #     )
    #     cur.execute("SELECT id FROM empresas_convenio WHERE nombre = 'Empresa Prueba S.A' LIMIT 1;")
    #     emp_id = cur.fetchone()[0]

    #     # Servicios de prueba
    #     # Particular
    #     cur.execute(
    #         """
    #         INSERT OR IGNORE INTO servicios (nombre, modalidad, precio, empresa, activo)
    #         VALUES ('Atención Psicológica', 'particular', 110000, NULL, 1);
    #         """
    #     )
    #     # Convenio (empresa por nombre)
    #     cur.execute(
    #         """
    #         INSERT OR IGNORE INTO servicios (nombre, modalidad, precio, empresa, activo)
    #         VALUES ('Atención Convenio', 'convenio', 85000, 'Empresa Prueba S.A', 1);
    #         """
    #     )

    #     # Paciente de prueba
    #     cur.execute(
    #         """
    #         INSERT OR IGNORE INTO pacientes (
    #         documento, 
    #         tipo_documento, 
    #         nombre_completo, 
    #         fecha_nacimiento, 
    #         sexo, 
    #         estado_civil, 
    #         escolaridad,
    #         eps,
    #         direccion, 
    #         email,
    #         indicativo_pais, 
    #         telefono,
    #         contacto_emergencia_nombre, 
    #         contacto_emergencia_telefono,
    #         observaciones 
    #         )
    #         VALUES ('1212121', 'CC', 'Pruebin Pruebas', '1990-01-01', 'M', 'Unión Libre', 'Pendejo', 'Sura', 'Calle falsa', 'lejozapata@gmail.com', '57', '3217769952', '', '', '');
    #         """
    #     )

    #     conn.commit()
    #     conn.close()
    #     print("Datos de prueba insertados.")
    # except Exception as e:
    #     print(f"No se pudieron insertar datos de prueba: {e}")
