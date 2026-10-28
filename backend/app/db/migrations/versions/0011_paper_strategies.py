"""Paper trades per strategy: Quick 2×, Runner and Moon bag on every alert.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLite leaves 0010's unique(alert_id) unnamed; batch mode names it by this convention.
NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def _alert_id_unique() -> str:
    for uq in sa.inspect(op.get_bind()).get_unique_constraints("paper_trades"):
        if uq["column_names"] == ["alert_id"] and uq.get("name"):
            return uq["name"]  # Postgres: paper_trades_alert_id_key
    return "uq_paper_trades_alert_id"


def upgrade() -> None:
    old = _alert_id_unique()
    with op.batch_alter_table("paper_trades", naming_convention=NAMING) as b:
        b.add_column(sa.Column("strategy", sa.String(16), nullable=False, server_default="quick"))
        b.add_column(sa.Column("held", sa.Float(), nullable=False, server_default="1"))
        b.add_column(sa.Column("proceeds_usd", sa.Float(), nullable=False, server_default="0"))
        b.add_column(sa.Column("rungs", sa.Integer(), nullable=False, server_default="0"))
        b.drop_constraint(old, type_="unique")
        b.create_unique_constraint("uq_paper_trades_strategy", ["alert_id", "strategy"])
    # The existing trades are all Quick 2× ones; a closed one has sold everything.
    op.execute(
        "UPDATE paper_trades SET held = 0, proceeds_usd = pnl_usd + stake_usd, "
        "rungs = CASE WHEN exit_reason = 'take_profit' THEN 1 ELSE 0 END "
        "WHERE closed_at IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DELETE FROM paper_trades WHERE strategy <> 'quick'")
    with op.batch_alter_table("paper_trades", naming_convention=NAMING) as b:
        b.drop_constraint("uq_paper_trades_strategy", type_="unique")
        b.create_unique_constraint("uq_paper_trades_alert_id", ["alert_id"])
        b.drop_column("rungs")
        b.drop_column("proceeds_usd")
        b.drop_column("held")
        b.drop_column("strategy")
