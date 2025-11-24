import sqlite3
from pathlib import Path
from typing import Dict, List, Any


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


# --------- Antecedentes médicos / psicológicos ---------


def crear_antecedente_medico(documento_paciente: str, descripcion: str) -> None:
    """Inserta un antecedente médico para un paciente."""
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
    """Inserta un antecedente psicológico para un paciente."""
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
    """Lista antecedentes médicos de un paciente."""
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
    """Lista antecedentes psicológicos de un paciente."""
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
    # Pequeña prueba cuando se ejecuta este archivo directamente
    print(f"Inicializando base de datos en: {DB_PATH}")
    init_db()
    print("Tablas creadas (si no existían).")

    # Insertar un paciente de prueba solo si no existe
    ejemplo_doc = "123456789"

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(1) FROM pacientes WHERE documento = ?;",
        (ejemplo_doc,),
    )
    existe = cur.fetchone()[0] > 0
    conn.close()

    if not existe:
        crear_paciente(
            {
                "documento": ejemplo_doc,
                "tipo_documento": "CC",
                "nombre_completo": "Paciente de Prueba",
                "fecha_nacimiento": "1990-01-01",
                "sexo": "F",
                "estado_civil": "Soltera",
                "escolaridad": "Universitaria",
                "eps": "EPS Prueba",
                "direccion": "Calle 123 #45-67",
                "email": "prueba@example.com",
                "telefono": "3001234567",
                "contacto_emergencia_nombre": "Contacto Prueba",
                "contacto_emergencia_telefono": "3017654321",
                "observaciones": "Paciente creada automáticamente para pruebas.",
            }
        )
        print("Paciente de prueba insertado.")
    else:
        print("Paciente de prueba ya existe.")

    # Insertar antecedentes de prueba
    crear_antecedente_medico(
        ejemplo_doc,
        "Antecedente médico de prueba: alergia a penicilina."
    )
    crear_antecedente_psicologico(
        ejemplo_doc,
        "Antecedente psicológico de prueba: episodio de ansiedad en 2018."
    )

    # Listar pacientes
    pacientes = listar_pacientes()
    print("Pacientes en la base de datos:")
    for p in pacientes:
        print(dict(p))

    # Listar antecedentes de prueba
    print("Antecedentes médicos del paciente de prueba:")
    for a in listar_antecedentes_medicos(ejemplo_doc):
        print(dict(a))

    print("Antecedentes psicológicos del paciente de prueba:")
    for a in listar_antecedentes_psicologicos(ejemplo_doc):
        print(dict(a))

def obtener_paciente(documento: str) -> sqlite3.Row | None:
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
    """Actualiza los datos de un paciente existente (menos el documento)."""
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