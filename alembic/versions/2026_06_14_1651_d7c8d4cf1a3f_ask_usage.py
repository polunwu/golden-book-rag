"""ask_usage

Revision ID: d7c8d4cf1a3f
Revises: 6f01c766ea52
Create Date: 2026-06-14 16:51:37.573137+00:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd7c8d4cf1a3f'
down_revision: Union[str, Sequence[str], None] = '6f01c766ea52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Per-(bucket, day) usage counters for the guest daily cap. `bucket` is a
    # counter name, not a user: 'global:<kind>' rows are enforced, 'guest:<gid>:
    # <kind>' rows are record-only. Composite PK is what check_and_increment's
    # ON CONFLICT upsert targets.
    op.execute(
        "CREATE TABLE ask_usage ("
        "  bucket TEXT NOT NULL, "
        "  day    DATE NOT NULL, "
        "  count  INT  NOT NULL DEFAULT 0, "
        "  PRIMARY KEY (bucket, day)"
        ")"
    )


def downgrade() -> None:
    op.execute("DROP TABLE ask_usage")
