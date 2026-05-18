"""
db_client.py — PostgreSQL connection + schema management
Source of truth สำหรับ Phase A migration จาก Google Sheets → Postgres

Phase A: DB เป็น mirror อ่านอย่างเดียว
Phase B+: DB เป็น primary, Sheet เป็น read-only mirror
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.extras

sys.path.insert(0, str(Path(__file__).parent))

_ENV_LOADED = False


def load_env():
    """โหลด .env + .env.db (DB credentials จาก Neon)"""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    for env_file in [".env", ".env.db"]:
        env_path = Path(__file__).parent.parent / env_file
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    # Strip quotes
                    v = v.strip().strip('"').strip("'")
                    os.environ.setdefault(k.strip(), v)
    _ENV_LOADED = True


def get_dsn() -> str:
    load_env()
    # Try preferred: pooled connection (DATABASE_URL)
    for var in ["DATABASE_URL", "POSTGRES_URL"]:
        v = os.environ.get(var, "").strip().strip('"').strip("'")
        if v:
            return v
    raise RuntimeError("No DATABASE_URL / POSTGRES_URL in env. Run `vercel env pull .env.local`")


@contextmanager
def connect(dict_cursor: bool = False):
    """Context manager — auto-close connection"""
    conn = psycopg2.connect(get_dsn())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def cursor(dict_cursor: bool = True):
    """Convenience: yields (conn, cursor) — auto-commit on success"""
    with connect() as conn:
        cur_factory = psycopg2.extras.RealDictCursor if dict_cursor else None
        with conn.cursor(cursor_factory=cur_factory) as cur:
            yield conn, cur


def fetch_all(query: str, params: tuple = ()) -> list[dict]:
    with cursor() as (_, cur):
        cur.execute(query, params)
        return list(cur.fetchall())


def fetch_one(query: str, params: tuple = ()) -> dict | None:
    with cursor() as (_, cur):
        cur.execute(query, params)
        return cur.fetchone()


def execute(query: str, params: tuple = ()) -> int:
    """Returns rowcount"""
    with cursor() as (_, cur):
        cur.execute(query, params)
        return cur.rowcount


def execute_many(query: str, rows: list[tuple]) -> int:
    if not rows:
        return 0
    with cursor() as (_, cur):
        psycopg2.extras.execute_batch(cur, query, rows, page_size=500)
        return cur.rowcount


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Test connection")
    parser.add_argument("--list-tables", action="store_true")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    if args.test or len(sys.argv) == 1:
        with cursor() as (_, cur):
            cur.execute("SELECT version(), current_database(), current_user")
            row = cur.fetchone()
            print(f"✅ Connected!")
            print(f"  Version: {row['version'][:60]}")
            print(f"  Database: {row['current_database']}")
            print(f"  User: {row['current_user']}")

    if args.list_tables:
        with cursor() as (_, cur):
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' ORDER BY table_name
            """)
            tables = cur.fetchall()
            print(f"\nTables ({len(tables)}):")
            for t in tables:
                print(f"  - {t['table_name']}")
