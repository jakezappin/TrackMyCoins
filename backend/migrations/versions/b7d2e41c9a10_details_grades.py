"""Details (problem) grades: a flag, the problem, and the share of straight-grade CPG they're valued at.

Revision ID: b7d2e41c9a10
Revises: 9ff7095acbe9
Create Date: 2026-10-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d2e41c9a10"
down_revision: Union[str, Sequence[str], None] = "9ff7095acbe9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("coins") as b:
        b.add_column(sa.Column("details", sa.Boolean(), nullable=False, server_default="0"))
        b.add_column(sa.Column("details_problem", sa.String(40), nullable=True))
        b.add_column(sa.Column("details_pct", sa.Integer(), nullable=True))
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("details_pct", sa.Integer(), nullable=False, server_default="70"))
    # Coins whose PCGS lookup said Details / Genuine were saved as straight grades; flag them (problem left blank
    # for the owner to fill in).
    op.execute(
        "UPDATE coins SET details = 1 WHERE lookup_raw IS NOT NULL AND ("
        "upper(json_extract(lookup_raw, '$.Grade')) LIKE '%DETAIL%' OR "
        "upper(json_extract(lookup_raw, '$.Grade')) LIKE '%GENUINE%')"
    )


def downgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.drop_column("details_pct")
    with op.batch_alter_table("coins") as b:
        b.drop_column("details_pct")
        b.drop_column("details_problem")
        b.drop_column("details")
