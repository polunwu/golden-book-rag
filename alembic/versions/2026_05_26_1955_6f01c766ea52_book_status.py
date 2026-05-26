"""book_status

Revision ID: 6f01c766ea52
Revises: 78e07aee7d14
Create Date: 2026-05-26 19:55:50.875414+00:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = '6f01c766ea52'
down_revision: Union[str, Sequence[str], None] = '78e07aee7d14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE book_status AS ENUM ('pending', 'processing', 'ready', 'failed')")
    op.execute(
        "ALTER TABLE books "
        "ADD COLUMN status book_status NOT NULL DEFAULT 'pending', "
        "ADD COLUMN error_message TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE books DROP COLUMN error_message")
    op.execute("ALTER TABLE books DROP COLUMN status")
    op.execute("DROP TYPE book_status")
