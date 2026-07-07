"""
database.py — Conexión PostgreSQL (Supabase) para FastAPI
"""
import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager

DATABASE_URL = os.environ.get("DATABASE_URL", "")

__all__ = ["DATABASE_URL", "db_session", "get_con"]


def get_con():
    con = psycopg2.connect(DATABASE_URL)
    con.autocommit = False
    return con


@contextmanager
def db_session():
    con = get_con()
    cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield cur, con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        cur.close()
        con.close()
