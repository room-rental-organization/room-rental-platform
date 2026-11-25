"""Separate lead disputes from conversion stages."""

from alembic import op
import sqlalchemy as sa


revision = "20261124_25"
down_revision = "20261124_24"
branch_labels = None
depends_on = None


_ACTIVE_DISPUTE_PREDICATE = sa.text(
    "lead_id IS NOT NULL AND status IN ('open', 'under_review')",
)
_CONVERSION_STAGES = (
    "'NEW', 'CONTACTED', 'VIEWING_SCHEDULED', 'VIEWING_COMPLETED', "
    "'INTERESTED', 'RENTED', 'UNSUCCESSFUL'"
)


def upgrade() -> None:
    connection = op.get_bind()
    duplicate = connection.execute(
        sa.text(
            """
            SELECT lead_id
            FROM report
            WHERE lead_id IS NOT NULL
                AND status IN ('open', 'under_review')
            GROUP BY lead_id
            HAVING COUNT(*) > 1
            LIMIT 1
            """,
        ),
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot add the active lead-dispute constraint while lead "
            f"{duplicate.lead_id} has multiple open dispute reports.",
        )

    unrecoverable = connection.execute(
        sa.text(
            """
            SELECT leads.lead_id
            FROM leads
            WHERE leads.stage = 'DISPUTED'
                AND (
                    NOT EXISTS (
                        SELECT 1
                        FROM lead_stage_history
                        WHERE lead_stage_history.lead_id = leads.lead_id
                            AND lead_stage_history.to_stage = 'DISPUTED'
                            AND lead_stage_history.from_stage IS NOT NULL
                    )
                    OR NOT EXISTS (
                        SELECT 1
                        FROM report
                        WHERE report.lead_id = leads.lead_id
                    )
                )
            LIMIT 1
            """,
        ),
    ).first()
    if unrecoverable is not None:
        raise RuntimeError(
            "Cannot restore the conversion stage for disputed lead "
            f"{unrecoverable.lead_id}; its prior stage or report is missing.",
        )

    op.add_column(
        "leads",
        sa.Column(
            "dispute_status",
            sa.String(length=16),
            server_default="none",
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE leads
        SET stage = (
            SELECT lead_stage_history.from_stage
            FROM lead_stage_history
            WHERE lead_stage_history.lead_id = leads.lead_id
                AND lead_stage_history.to_stage = 'DISPUTED'
                AND lead_stage_history.from_stage IS NOT NULL
            ORDER BY lead_stage_history.changed_at DESC,
                lead_stage_history.history_id DESC
            LIMIT 1
        )
        WHERE leads.stage = 'DISPUTED'
        """,
    )
    op.execute(
        """
        UPDATE leads
        SET dispute_status = COALESCE(
            (
                SELECT CASE report.status
                    WHEN 'open' THEN 'open'
                    WHEN 'under_review' THEN 'open'
                    WHEN 'resolved' THEN 'resolved'
                    WHEN 'dismissed' THEN 'dismissed'
                    ELSE 'none'
                END
                FROM report
                WHERE report.lead_id = leads.lead_id
                ORDER BY report.created_at DESC, report.report_id DESC
                LIMIT 1
            ),
            'none'
        )
        """,
    )
    op.execute(
        """
        UPDATE leads
        SET billing_eligible = false
        WHERE dispute_status = 'open'
        """,
    )

    with op.batch_alter_table("leads") as batch_op:
        batch_op.drop_constraint("leads_stage_check", type_="check")
        batch_op.create_check_constraint(
            "leads_stage_check",
            f"stage IN ({_CONVERSION_STAGES})",
        )
        batch_op.create_check_constraint(
            "leads_dispute_status_check",
            "dispute_status IN ('none', 'open', 'resolved', 'dismissed')",
        )
        batch_op.create_check_constraint(
            "leads_open_dispute_not_billable_check",
            "dispute_status != 'open' OR billing_eligible = false",
        )

    op.create_index(
        "leads_dispute_updated_idx",
        "leads",
        ["dispute_status", "updated_at", "lead_id"],
    )
    op.create_index(
        "report_one_active_lead_dispute_idx",
        "report",
        ["lead_id"],
        unique=True,
        postgresql_where=_ACTIVE_DISPUTE_PREDICATE,
        sqlite_where=_ACTIVE_DISPUTE_PREDICATE,
    )


def downgrade() -> None:
    active_dispute = op.get_bind().execute(
        sa.text(
            "SELECT lead_id FROM leads "
            "WHERE dispute_status != 'none' LIMIT 1",
        ),
    ).first()
    if active_dispute is not None:
        raise RuntimeError(
            "Cannot downgrade while lead dispute state exists; resolving "
            "it back into a conversion stage would discard the separation.",
        )

    op.drop_index(
        "report_one_active_lead_dispute_idx",
        table_name="report",
    )
    op.drop_index("leads_dispute_updated_idx", table_name="leads")
    with op.batch_alter_table("leads") as batch_op:
        batch_op.drop_constraint(
            "leads_open_dispute_not_billable_check",
            type_="check",
        )
        batch_op.drop_constraint(
            "leads_dispute_status_check",
            type_="check",
        )
        batch_op.drop_constraint("leads_stage_check", type_="check")
        batch_op.create_check_constraint(
            "leads_stage_check",
            "stage IN ('NEW', 'CONTACTED', 'VIEWING_SCHEDULED', "
            "'VIEWING_COMPLETED', 'INTERESTED', 'RENTED', "
            "'UNSUCCESSFUL', 'DISPUTED')",
        )
        batch_op.drop_column("dispute_status")

