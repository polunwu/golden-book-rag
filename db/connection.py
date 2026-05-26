import os

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

load_dotenv()


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL missing — set in .env or environment")
    return url


def get_connection() -> psycopg.Connection:
    """Open a connection with the pgvector type adapter registered.

    V2 adds get_pool() alongside this for FastAPI handlers; scripts keep using
    get_connection() (single conn, no pool).
    """
    conn = psycopg.connect(_database_url())
    register_vector(conn)
    return conn
