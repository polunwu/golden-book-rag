from typing import Iterator, cast

import psycopg
from psycopg.rows import DictRow

from db.connection import get_pool


def get_conn() -> Iterator[psycopg.Connection[DictRow]]:
    """Yield a pooled connection for the duration of one request.

    The pool is configured with `row_factory=dict_row` (see `db.connection`),
    so every checked-out connection returns dict rows at runtime. The cast
    matches the type to that runtime contract — without it, the default
    `Connection[TupleRow]` generic would force per-query casts in handlers.
    """
    with get_pool().connection() as conn:
        yield cast(psycopg.Connection[DictRow], conn)
