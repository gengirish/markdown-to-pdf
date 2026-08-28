"""add templates.config and templates.updated_at

Templates can now be authored two ways: hand-written HTML, or a guided form.
`config` stores the guided settings so the form can be reopened; it is NULL for
hand-written HTML, and is set back to NULL the moment someone edits the HTML
directly. That NULL is load-bearing — it is how the API knows regenerating would
discard an author's edit.

Both columns are nullable with no backfill. Every existing template is
hand-authored or seeded, so NULL config is the correct and honest value for all
of them, and updated_at is genuinely unknown rather than "now".

Revision ID: f7b04c2e91da
Revises: e5a2c9d14f3b
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f7b04c2e91da"
down_revision: Union[str, Sequence[str], None] = "e5a2c9d14f3b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("templates", sa.Column("config", sa.JSON(), nullable=True))
    op.add_column(
        "templates", sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("templates", "updated_at")
    op.drop_column("templates", "config")
