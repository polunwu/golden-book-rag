"""chunks_cascade

Revision ID: 78e07aee7d14
Revises: adeae572e81e
Create Date: 2026-05-26 19:55:46.058434+00:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = '78e07aee7d14'
down_revision: Union[str, Sequence[str], None] = 'adeae572e81e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Default PG-named FK constraints: <table>_<col>_fkey
    op.execute("ALTER TABLE chunks DROP CONSTRAINT chunks_book_id_fkey")
    op.execute(
        "ALTER TABLE chunks ADD CONSTRAINT chunks_book_id_fkey "
        "FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE"
    )
    op.execute("ALTER TABLE chunk_embeddings DROP CONSTRAINT chunk_embeddings_chunk_id_fkey")
    op.execute(
        "ALTER TABLE chunk_embeddings ADD CONSTRAINT chunk_embeddings_chunk_id_fkey "
        "FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chunk_embeddings DROP CONSTRAINT chunk_embeddings_chunk_id_fkey")
    op.execute(
        "ALTER TABLE chunk_embeddings ADD CONSTRAINT chunk_embeddings_chunk_id_fkey "
        "FOREIGN KEY (chunk_id) REFERENCES chunks(id)"
    )
    op.execute("ALTER TABLE chunks DROP CONSTRAINT chunks_book_id_fkey")
    op.execute(
        "ALTER TABLE chunks ADD CONSTRAINT chunks_book_id_fkey "
        "FOREIGN KEY (book_id) REFERENCES books(id)"
    )
