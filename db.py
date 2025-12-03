import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional


# ----------------- Reglas de negocio de citas -----------------

# Precios por modalidad (puedes ajustar estos valores cuando quieras)
PRECIOS_MODALIDAD: Dict[str, int] = {
    "virtual": 0,               # TODO: poner valor real, ej. 120000
    "presencial": 0,           # TODO: valor real
    "convenio_empresarial": 0, # TODO: valor real
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
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "sara_psico.db"


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
            telefono TEXT,
            contacto_emergencia_nombre TEXT,
            contacto_emergencia_telefono TEXT,
            observaciones TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        """
    )

      # Tabla de citas
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS citas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento_paciente TEXT NOT NULL,
            fecha_hora TEXT NOT NULL,
            modalidad TEXT CHECK (modalidad IN ('presencial', 'virtual', 'convenio_empresarial')),
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

        # Tabla de servicios / modalidades de cita
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS servicios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,                -- Ej: "Consulta psicológica", "Convenio Empresa X"
            tipo TEXT NOT NULL CHECK (tipo IN ('presencial','virtual','convenio_empresarial')),
            precio REAL NOT NULL,
            empresa TEXT,                        -- Solo aplica si es convenio_empresarial (puede ser NULL)
            activo INTEGER NOT NULL DEFAULT 1    -- 1=activo, 0=inactivo
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
            fecha_hora TEXT NOT NULL    -- 'YYYY-MM-DD HH:MM'
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
            :telefono,
            :contacto_emergencia_nombre,
            :contacto_emergencia_telefono,
            :observaciones
        );
        """,
        paciente,
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

    cur.execute(
        """
        INSERT INTO citas (
            documento_paciente,
            fecha_hora,
            modalidad,
            motivo,
            notas,
            estado,
            precio,
            pagado
        ) VALUES (
            :documento_paciente,
            :fecha_hora,
            :modalidad,
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

def eliminar_cita(cita_id: int) -> None:
    """Elimina una cita de la base de datos."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM citas WHERE id = ?;", (cita_id,))

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
            fecha_hora
        ) VALUES (
            :motivo,
            :fecha_hora
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
        WHERE fecha_hora >= ? AND fecha_hora <= ?
        ORDER BY fecha_hora;
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
            fecha_hora = :fecha_hora
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


def existe_bloqueo_en_fecha(fecha_hora: str, bloqueo_id_excluir: Optional[int] = None) -> bool:
    """
    Devuelve True si ya existe un bloqueo exactamente en esa fecha_hora.
    Si bloqueo_id_excluir no es None, se excluye ese id (útil en edición).
    """
    conn = get_connection()
    cur = conn.cursor()

    if bloqueo_id_excluir is None:
        cur.execute(
            "SELECT COUNT(*) FROM bloqueos_agenda WHERE fecha_hora = ?;",
            (fecha_hora,),
        )
    else:
        cur.execute(
            "SELECT COUNT(*) FROM bloqueos_agenda WHERE fecha_hora = ? AND id != ?;",
            (fecha_hora, bloqueo_id_excluir),
        )

    count = cur.fetchone()[0]
    conn.close()
    return count > 0

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


def obtener_horarios_atencion() -> list[dict]:
    """
    Devuelve una lista de 7 dicts (0=Lunes .. 6=Domingo) con:
      dia, habilitado (bool), hora_inicio (str "HH:MM"), hora_fin (str "HH:MM")
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT dia, habilitado, hora_inicio, hora_fin
        FROM horarios_atencion
        ORDER BY dia;
        """
    )
    filas = cur.fetchall()
    conn.close()

    horarios = []
    for row in filas:
        horarios.append(
            {
                "dia": row["dia"],
                "habilitado": bool(row["habilitado"]),
                "hora_inicio": row["hora_inicio"],
                "hora_fin": row["hora_fin"],
            }
        )

    return horarios


def guardar_horarios_atencion(horarios: list[dict]) -> None:
    """
    Recibe lista de dicts con claves:
      dia (int 0-6), habilitado (bool/int), hora_inicio, hora_fin
    y los guarda en la tabla horarios_atencion.
    """
    conn = get_connection()
    cur = conn.cursor()

    for h in horarios:
        cur.execute(
            """
            UPDATE horarios_atencion
            SET habilitado = ?, hora_inicio = ?, hora_fin = ?
            WHERE dia = ?;
            """,
            (
                1 if h.get("habilitado") else 0,
                h.get("hora_inicio"),
                h.get("hora_fin"),
                h.get("dia"),
            ),
        )

    conn.commit()
    conn.close()

# ------------ SERVICIOS / MODALIDADES -------------


def listar_servicios() -> list[sqlite3.Row]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM servicios
        ORDER BY activo DESC, nombre COLLATE NOCASE;
        """
    )

    filas = cur.fetchall()
    conn.close()
    return filas


def crear_servicio(nombre: str, tipo: str, precio: float, empresa: str | None = None) -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO servicios (nombre, tipo, precio, empresa)
        VALUES (?, ?, ?, ?);
        """,
        (nombre, tipo, precio, empresa),
    )

    conn.commit()
    conn.close()


def actualizar_servicio(
    servicio_id: int,
    nombre: str,
    tipo: str,
    precio: float,
    empresa: str | None,
    activo: bool,
) -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE servicios
        SET nombre = ?, tipo = ?, precio = ?, empresa = ?, activo = ?
        WHERE id = ?;
        """,
        (nombre, tipo, precio, empresa, 1 if activo else 0, servicio_id),
    )

    conn.commit()
    conn.close()


def eliminar_servicio(servicio_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM servicios WHERE id = ?;", (servicio_id,))
    conn.commit()
    conn.close()

# ------------ FIN -------------


if __name__ == "__main__":
    print(f"Inicializando base de datos en: {DB_PATH}")
    init_db()
    print("Tablas listas.")
