import os
from typing import Optional

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

load_dotenv()


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL missing — set in .env or environment")
    return url


_pool: Optional[ConnectionPool] = None


def get_pool() -> ConnectionPool:
    """Lazy module-level pool. Every checked-out connection has the pgvector
    adapter registered via `configure=register_vector` (B2.1).

    Lifecycle: `api/main.py`'s lifespan calls `.open()` on startup and `.close()`
    on shutdown. Scripts MUST NOT call get_pool() — they use get_connection().
    """
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=_database_url(),
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            configure=register_vector,
            open=False,
        )
    return _pool


def get_connection() -> psycopg.Connection:
    """Single-connection accessor for scripts."""
    conn = psycopg.connect(_database_url())
    register_vector(conn)
    return conn
