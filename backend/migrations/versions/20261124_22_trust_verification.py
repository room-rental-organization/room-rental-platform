"""Add auditable landlord trust and verification requests."""

from alembic import op
import sqlalchemy as sa


revision = "20261124_22"
down_revision = "20261124_21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE report_reason_enum ADD VALUE IF NOT EXISTS 'misleading_price'",
    )
    op.execute(
        "ALTER TYPE report_reason_enum "
        "ADD VALUE IF NOT EXISTS 'incorrect_availability'",
    )
    op.execute(
        "ALTER TYPE report_reason_enum "
        "ADD VALUE IF NOT EXISTS 'unauthorized_property'",
    )
    op.execute(
        "ALTER TYPE report_reason_enum ADD VALUE IF NOT EXISTS 'harassment'",
    )
    op.execute(
        "ALTER TYPE report_reason_enum ADD VALUE IF NOT EXISTS 'fake_account'",
    )
    op.execute(
        "ALTER TYPE report_action_enum ADD VALUE IF NOT EXISTS 'note_added'",
    )
    op.add_column(
        "users",
        sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "trust_verification_requests",
        sa.Column(
            "request_id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("listing_id", sa.BigInteger(), nullable=True),
        sa.Column("verification_type", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("evidence_statement", sa.Text(), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(verification_type = 'identity' AND listing_id IS NULL) OR "
            "(verification_type = 'property_authorization' AND listing_id IS NOT NULL)",
            name="trust_verification_subject_check",
        ),
        sa.CheckConstraint(
            "verification_type IN ('identity', 'property_authorization')",
            name="trust_verification_type_check",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'needs_information', 'approved', 'rejected')",
            name="trust_verification_status_check",
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.listing_id"],
            name="trust_verification_listing_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name="trust_verification_user_id_fkey",
        ),
        sa.PrimaryKeyConstraint(
            "request_id",
            name="trust_verification_requests_pkey",
        ),
    )
    op.create_index(
        "ix_trust_verification_user_submitted",
        "trust_verification_requests",
        ["user_id", "submitted_at"],
    )
    op.create_index(
        "ix_trust_verification_status_submitted",
        "trust_verification_requests",
        ["status", "submitted_at"],
    )
    op.create_index(
        "ix_trust_verification_listing_submitted",
        "trust_verification_requests",
        ["listing_id", "submitted_at"],
    )
    op.create_index(
        "uq_trust_verification_active_profile",
        "trust_verification_requests",
        ["user_id", "verification_type"],
        unique=True,
        postgresql_where=sa.text(
            "listing_id IS NULL AND status IN ('pending', 'needs_information')",
        ),
        sqlite_where=sa.text(
            "listing_id IS NULL AND status IN ('pending', 'needs_information')",
        ),
    )
    op.create_index(
        "uq_trust_verification_active_listing",
        "trust_verification_requests",
        ["user_id", "verification_type", "listing_id"],
        unique=True,
        postgresql_where=sa.text(
            "listing_id IS NOT NULL AND status IN ('pending', 'needs_information')",
        ),
        sqlite_where=sa.text(
            "listing_id IS NOT NULL AND status IN ('pending', 'needs_information')",
        ),
    )
    op.create_table(
        "trust_verification_history",
        sa.Column(
            "history_id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("request_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('submitted', 'resubmitted', 'approved', "
            "'rejected', 'information_requested')",
            name="trust_verification_history_action_check",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.user_id"],
            name="trust_verification_history_actor_user_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["trust_verification_requests.request_id"],
            name="trust_verification_history_request_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "history_id",
            name="trust_verification_history_pkey",
        ),
    )
    op.create_index(
        "ix_trust_verification_history_request",
        "trust_verification_history",
        ["request_id", "created_at"],
    )
    op.create_index(
        "ix_trust_verification_history_action_created",
        "trust_verification_history",
        ["action", "created_at"],
    )
    op.create_index(
        "ix_report_tenant_created",
        "report",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_report_tenant_created", table_name="report")
    op.drop_index(
        "ix_trust_verification_history_action_created",
        table_name="trust_verification_history",
    )
    op.drop_index(
        "ix_trust_verification_history_request",
        table_name="trust_verification_history",
    )
    op.drop_table("trust_verification_history")
    op.drop_index(
        "uq_trust_verification_active_listing",
        table_name="trust_verification_requests",
    )
    op.drop_index(
        "uq_trust_verification_active_profile",
        table_name="trust_verification_requests",
    )
    op.drop_index(
        "ix_trust_verification_listing_submitted",
        table_name="trust_verification_requests",
    )
    op.drop_index(
        "ix_trust_verification_status_submitted",
        table_name="trust_verification_requests",
    )
    op.drop_index(
        "ix_trust_verification_user_submitted",
        table_name="trust_verification_requests",
    )
    op.drop_table("trust_verification_requests")
    op.drop_column("users", "phone_verified_at")
