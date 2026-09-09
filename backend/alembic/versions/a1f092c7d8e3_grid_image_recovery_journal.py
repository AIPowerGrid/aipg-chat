"""Add the private Chat image recovery journal.

Revision ID: a1f092c7d8e3
Revises: 01c63968ff8f
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a1f092c7d8e3"
down_revision = "01c63968ff8f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "grid_image_request",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            sa.Integer(),
            sa.ForeignKey("chat_message.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slot", sa.String(128), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("grid_job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("result", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("message_id", "slot", name="uq_grid_image_request_slot"),
        sa.CheckConstraint(
            "state IN ('attempted', 'completed', 'closed')",
            name="ck_grid_image_request_state",
        ),
        sa.CheckConstraint(
            "(state = 'completed' AND result IS NOT NULL AND grid_job_id IS NOT NULL) "
            "OR (state <> 'completed' AND result IS NULL)",
            name="ck_grid_image_request_result",
        ),
    )
    op.create_index(
        "ix_grid_image_request_user_created",
        "grid_image_request",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    # A code rollback must keep paid recovery handles. Destructive removal is
    # only permitted before any request has been recorded.
    if (
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM grid_image_request LIMIT 1"))
        .first()
    ):
        raise RuntimeError("Refusing to remove nonempty Grid image recovery journal")
    op.drop_table("grid_image_request")
