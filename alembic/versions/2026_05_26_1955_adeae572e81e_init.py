"""init

Revision ID: adeae572e81e
Revises:
Create Date: 2026-05-26 19:55:38.567320+00:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'adeae572e81e'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS books (
  id         UUID PRIMARY KEY,
  title      TEXT,
  file_path  TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chunks (
  id            UUID PRIMARY KEY,
  book_id       UUID REFERENCES books(id),
  text          TEXT NOT NULL,
  page_start    INT,
  page_end      INT,
  section_path  TEXT[],
  section_title TEXT,
  section_level INT,
  chunk_index   INT NOT NULL,
  token_count   INT,
  created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
  chunk_id        UUID PRIMARY KEY REFERENCES chunks(id),
  embedding       vector(1536) NOT NULL,
  embedding_model TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS chunk_embedding_idx
  ON chunk_embeddings USING hnsw (embedding vector_cosine_ops);
"""


def upgrade() -> None:
    op.execute(SCHEMA_SQL)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunk_embedding_idx")
    op.execute("DROP TABLE IF EXISTS chunk_embeddings")
    op.execute("DROP TABLE IF EXISTS chunks")
    op.execute("DROP TABLE IF EXISTS books")
    op.execute("DROP EXTENSION IF EXISTS vector")
