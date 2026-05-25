import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

load_dotenv()

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL missing — set in .env or environment")
    return url


def init_db() -> None:
    """Apply db/schema.sql idempotently (extension, tables, HNSW index).

    Uses a raw connection: the pgvector adapter cannot be registered until the
    `vector` extension exists, which this function itself creates. Run once before
    get_connection(). Not wired into any app lifecycle (Step 5 Hand-off).
    """
    with psycopg.connect(_database_url()) as conn:
        conn.execute(_SCHEMA_PATH.read_text())


def get_connection() -> psycopg.Connection:
    """Open a connection with the pgvector type adapter registered.

    Single accessor for all DB access — Step 5 swaps this for a psycopg_pool pool
    without touching callers (shaping.md Step 5 Hand-off).
    """
    conn = psycopg.connect(_database_url())
    register_vector(conn)
    return conn
