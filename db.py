import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional


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
            modalidad TEXT CHECK (modalidad IN ('presencial', 'virtual')),
            motivo TEXT,
            notas TEXT,
            estado TEXT,
            FOREIGN KEY (documento_paciente) REFERENCES pacientes (documento)
        );
        """
    )

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

    conn.commit()
    conn.close()


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


if __name__ == "__main__":
    print(f"Inicializando base de datos en: {DB_PATH}")
    init_db()
    print("Tablas listas.")
