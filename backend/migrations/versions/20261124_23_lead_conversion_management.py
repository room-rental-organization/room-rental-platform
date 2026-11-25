"""Add lead conversion tracking linked to contact requests and reports."""

from alembic import op
import sqlalchemy as sa


revision = "20261124_23"
down_revision = "20261124_22"
branch_labels = None
depends_on = None


_STAGES = (
    "'NEW', 'CONTACTED', 'VIEWING_SCHEDULED', 'VIEWING_COMPLETED', "
    "'INTERESTED', 'RENTED', 'UNSUCCESSFUL', 'DISPUTED'"
)
_ID_TYPE = sa.Integer().with_variant(sa.BigInteger(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column(
            "lead_id",
            _ID_TYPE,
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("contact_request_id", _ID_TYPE, nullable=False),
        sa.Column("tenant_id", _ID_TYPE, nullable=False),
        sa.Column("landlord_id", _ID_TYPE, nullable=False),
        sa.Column("listing_id", _ID_TYPE, nullable=False),
        sa.Column(
            "stage",
            sa.String(length=24),
            server_default="NEW",
            nullable=False,
        ),
        sa.Column("rented_at", sa.DateTime(), nullable=True),
        sa.Column("unsuccessful_reason", sa.Text(), nullable=True),
        sa.Column(
            "billing_eligible",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"stage IN ({_STAGES})",
            name="leads_stage_check",
        ),
        sa.ForeignKeyConstraint(
            ["contact_request_id"],
            ["contact_requests.request_id"],
            name="leads_contact_request_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["users.user_id"],
            name="leads_tenant_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["landlord_id"],
            ["users.user_id"],
            name="leads_landlord_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.listing_id"],
            name="leads_listing_id_fkey",
        ),
        sa.PrimaryKeyConstraint("lead_id", name="leads_pkey"),
        sa.UniqueConstraint(
            "contact_request_id",
            name="leads_contact_request_id_key",
        ),
    )
    op.create_index(
        "leads_landlord_created_idx",
        "leads",
        ["landlord_id", "created_at", "lead_id"],
    )
    op.create_index(
        "leads_tenant_created_idx",
        "leads",
        ["tenant_id", "created_at", "lead_id"],
    )
    op.create_index(
        "leads_stage_updated_idx",
        "leads",
        ["stage", "updated_at", "lead_id"],
    )
    op.create_table(
        "lead_stage_history",
        sa.Column(
            "history_id",
            _ID_TYPE,
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("lead_id", _ID_TYPE, nullable=False),
        sa.Column("from_stage", sa.String(length=24), nullable=True),
        sa.Column("to_stage", sa.String(length=24), nullable=False),
        sa.Column("actor_user_id", _ID_TYPE, nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            f"from_stage IS NULL OR from_stage IN ({_STAGES})",
            name="lead_stage_history_from_stage_check",
        ),
        sa.CheckConstraint(
            f"to_stage IN ({_STAGES})",
            name="lead_stage_history_to_stage_check",
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"],
            ["leads.lead_id"],
            name="lead_stage_history_lead_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.user_id"],
            name="lead_stage_history_actor_user_id_fkey",
        ),
        sa.PrimaryKeyConstraint("history_id", name="lead_stage_history_pkey"),
    )
    op.create_index(
        "lead_stage_history_lead_changed_idx",
        "lead_stage_history",
        ["lead_id", "changed_at", "history_id"],
    )

    op.execute(
        """
        INSERT INTO leads (
            contact_request_id,
            tenant_id,
            landlord_id,
            listing_id,
            stage,
            billing_eligible,
            created_at,
            updated_at
        )
        SELECT
            contact_requests.request_id,
            contact_requests.tenant_id,
            listings.landlord_id,
            contact_requests.listing_id,
            'NEW',
            false,
            contact_requests.requested_at,
            contact_requests.requested_at
        FROM contact_requests
        JOIN listings
            ON listings.listing_id = contact_requests.listing_id
        """,
    )
    op.execute(
        """
        INSERT INTO lead_stage_history (
            lead_id,
            from_stage,
            to_stage,
            actor_user_id,
            changed_at
        )
        SELECT
            lead_id,
            NULL,
            'NEW',
            tenant_id,
            created_at
        FROM leads
        """,
    )

    with op.batch_alter_table("report") as batch_op:
        batch_op.add_column(sa.Column("lead_id", _ID_TYPE, nullable=True))
        batch_op.create_foreign_key(
            "report_lead_id_fkey",
            "leads",
            ["lead_id"],
            ["lead_id"],
        )
        batch_op.drop_constraint("report_target_check", type_="check")
        batch_op.create_check_constraint(
            "report_target_check",
            "(listing_id IS NOT NULL AND target_user_id IS NULL "
            "AND lead_id IS NULL) OR "
            "(listing_id IS NULL AND target_user_id IS NOT NULL "
            "AND lead_id IS NULL) OR "
            "(listing_id IS NULL AND target_user_id IS NULL "
            "AND lead_id IS NOT NULL)",
        )
    op.create_index(
        "ix_report_lead_tenant_reason_created",
        "report",
        ["lead_id", "tenant_id", "reason", "created_at"],
    )


def downgrade() -> None:
    if op.get_bind().execute(
        sa.text("SELECT 1 FROM report WHERE lead_id IS NOT NULL LIMIT 1"),
    ).first():
        raise RuntimeError(
            "Cannot downgrade lead management while lead-targeted reports exist.",
        )
    op.drop_index(
        "ix_report_lead_tenant_reason_created",
        table_name="report",
    )
    with op.batch_alter_table("report") as batch_op:
        batch_op.drop_constraint("report_target_check", type_="check")
        batch_op.drop_constraint("report_lead_id_fkey", type_="foreignkey")
        batch_op.drop_column("lead_id")
        batch_op.create_check_constraint(
            "report_target_check",
            "listing_id IS NOT NULL OR target_user_id IS NOT NULL",
        )
    op.drop_index(
        "lead_stage_history_lead_changed_idx",
        table_name="lead_stage_history",
    )
    op.drop_table("lead_stage_history")
    op.drop_index("leads_stage_updated_idx", table_name="leads")
    op.drop_index("leads_tenant_created_idx", table_name="leads")
    op.drop_index("leads_landlord_created_idx", table_name="leads")
    op.drop_table("leads")
