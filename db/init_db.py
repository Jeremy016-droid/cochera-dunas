"""
init_db.py — Crea e inicializa cochera.db desde schema.sql
Uso:  python init_db.py
"""
import sqlite3, pathlib, hashlib

BASE = pathlib.Path(__file__).parent
DB   = BASE / "cochera.db"
SQL  = BASE / "schema.sql"

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

def init():
    con = sqlite3.connect(DB)
    con.executescript(SQL.read_text(encoding="utf-8"))

    # Usuarios de prueba (cambiar contraseñas en producción)
    con.execute("""
        INSERT OR IGNORE INTO USUARIO (nombre, username, passwordHash, rol)
        VALUES
            ('Operador 1',   'operador',   ?, 'operador'),
            ('Presidenta',   'presidenta', ?, 'presidenta')
    """, (sha256("operador123"), sha256("presidenta123")))

    con.commit()
    con.close()
    print(f"Base de datos lista: {DB}")

if __name__ == "__main__":
    init()
