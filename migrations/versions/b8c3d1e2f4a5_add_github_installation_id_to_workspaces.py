"""add github_installation_id to workspaces

Revision ID: b8c3d1e2f4a5
Revises: 4663a065fb30
Create Date: 2026-09-13 16:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8c3d1e2f4a5"
down_revision: str | None = "4663a065fb30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("github_installation_id", sa.BigInteger(), nullable=True))
    op.create_index(
        op.f("ix_workspaces_github_installation_id"),
        "workspaces",
        ["github_installation_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_workspaces_github_installation_id"), table_name="workspaces")
    op.drop_column("workspaces", "github_installation_id")
