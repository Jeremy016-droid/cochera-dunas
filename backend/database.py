"""
database.py — Conexión SQLite + helper de sesión para FastAPI
"""
import sqlite3, pathlib
from contextlib import contextmanager

DB_PATH = pathlib.Path(__file__).parent.parent / "db" / "cochera.db"

def get_con() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

@contextmanager
def db_session():
    con = get_con()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
