"""Add listing availability and update timestamps for landlord dashboard."""

from alembic import op
import sqlalchemy as sa


revision = "20261124_21"
down_revision = "20261111_20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("listings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "availability_status",
                sa.String(length=16),
                server_default="available",
                nullable=False,
            ),
        )
        batch_op.add_column(
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        batch_op.create_check_constraint(
            "listings_availability_status_check",
            "availability_status IN ('available', 'reserved', 'occupied')",
        )

    op.execute(
        "UPDATE listings SET availability_status = 'occupied' "
        "WHERE status = 'taken'",
    )
    op.execute("UPDATE listings SET updated_at = created_at")

    with op.batch_alter_table("listings") as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        )


def downgrade() -> None:
    with op.batch_alter_table("listings") as batch_op:
        batch_op.drop_constraint(
            "listings_availability_status_check",
            type_="check",
        )
        batch_op.drop_column("updated_at")
        batch_op.drop_column("availability_status")
