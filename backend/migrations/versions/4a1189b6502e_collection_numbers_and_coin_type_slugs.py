"""collection numbers and coin type slugs

Revision ID: 4a1189b6502e
Revises: 88e93766aa6a
Create Date: 2026-10-16 23:52:27.203516

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a1189b6502e'
down_revision: Union[str, Sequence[str], None] = '88e93766aa6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Number collections per (user, coin type) and use URL-style coin type slugs."""
    with op.batch_alter_table("inventory_counters") as b:
        b.add_column(sa.Column("next_collection_seq", sa.Integer(), nullable=False, server_default="1"))
    with op.batch_alter_table("collections") as b:
        b.add_column(sa.Column("number", sa.Integer(), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, user_id, coin_type_id FROM collections ORDER BY id")).fetchall()
    seq: dict[tuple[int, int], int] = {}
    for cid, uid, tid in rows:
        n = seq.get((uid, tid), 0) + 1
        seq[(uid, tid)] = n
        conn.execute(sa.text("UPDATE collections SET number = :n WHERE id = :id"), {"n": n, "id": cid})
    for (uid, tid), n in seq.items():
        exists = conn.execute(
            sa.text("SELECT 1 FROM inventory_counters WHERE user_id = :u AND coin_type_id = :t"), {"u": uid, "t": tid}
        ).first()
        if exists:
            conn.execute(
                sa.text("UPDATE inventory_counters SET next_collection_seq = :n WHERE user_id = :u AND coin_type_id = :t"),
                {"n": n + 1, "u": uid, "t": tid},
            )
        else:
            conn.execute(
                sa.text(
                    "INSERT INTO inventory_counters (user_id, coin_type_id, next_seq, next_collection_seq) "
                    "VALUES (:u, :t, 1, :n)"
                ),
                {"n": n + 1, "u": uid, "t": tid},
            )

    with op.batch_alter_table("collections") as b:
        b.alter_column("number", existing_type=sa.Integer(), nullable=False)
        b.create_unique_constraint("uq_collections_user_type_number", ["user_id", "coin_type_id", "number"])

    conn.execute(sa.text("UPDATE coin_types SET slug = 'morgan-dollars' WHERE slug = 'morgan'"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE coin_types SET slug = 'morgan' WHERE slug = 'morgan-dollars'"))
    with op.batch_alter_table("collections") as b:
        b.drop_constraint("uq_collections_user_type_number", type_="unique")
        b.drop_column("number")
    with op.batch_alter_table("inventory_counters") as b:
        b.drop_column("next_collection_seq")
