"""Limit a tenant to one pending enquiry per listing."""

from alembic import op
import sqlalchemy as sa


revision = "20261124_24"
down_revision = "20261124_23"
branch_labels = None
depends_on = None


_INDEX_NAME = "contact_requests_one_pending_per_tenant_listing_idx"
_PREDICATE = sa.text("status = 'pending'")


def upgrade() -> None:
    duplicate = op.get_bind().execute(
        sa.text(
            """
            SELECT tenant_id, listing_id
            FROM contact_requests
            WHERE status = 'pending'
            GROUP BY tenant_id, listing_id
            HAVING COUNT(*) > 1
            LIMIT 1
            """,
        ),
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot add the pending contact-request constraint while "
            f"tenant {duplicate.tenant_id} has multiple pending requests "
            f"for listing {duplicate.listing_id}. Resolve duplicates first.",
        )

    op.create_index(
        _INDEX_NAME,
        "contact_requests",
        ["tenant_id", "listing_id"],
        unique=True,
        postgresql_where=_PREDICATE,
        sqlite_where=_PREDICATE,
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="contact_requests")
