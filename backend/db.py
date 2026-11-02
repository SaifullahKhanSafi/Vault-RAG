"""Short transactions with an authenticated identity for PostgreSQL row policies."""
import os
from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("RAW_DATABASE_URL", "postgresql://rag_app@localhost:5432/rag_db")

@contextmanager
def connect(user_id=None):
    with psycopg.connect(DATABASE_URL, connect_timeout=5, row_factory=dict_row) as conn:
        conn.execute("SELECT set_config('app.user_id', %s, true)", (str(user_id or ""),))
        yield conn

def audit(conn, user, workspace, action, target=None):
    from psycopg.types.json import Jsonb
    conn.execute("INSERT INTO rag_audit (workspace_id,user_id,action,target) VALUES (%s,%s,%s,%s)",
                 (workspace, user, action, str(target) if target else None))
