import runpy
import unittest
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


class LeadMigrationTests(unittest.TestCase):
    @staticmethod
    def load_migration() -> dict[str, object]:
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "versions"
            / "20261124_23_lead_conversion_management.py"
        )
        return runpy.run_path(str(migration_path))

    def test_migration_backfills_leads_and_adds_report_target(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        migration = self.load_migration()

        with engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE users (user_id INTEGER PRIMARY KEY)"),
            )
            connection.execute(
                text(
                    "CREATE TABLE listings ("
                    "listing_id INTEGER PRIMARY KEY, "
                    "landlord_id INTEGER NOT NULL)",
                ),
            )
            connection.execute(
                text(
                    "CREATE TABLE contact_requests ("
                    "request_id INTEGER PRIMARY KEY, "
                    "listing_id INTEGER NOT NULL, "
                    "tenant_id INTEGER NOT NULL, "
                    "status TEXT NOT NULL, "
                    "requested_at DATETIME NOT NULL)",
                ),
            )
            connection.execute(
                text(
                    "CREATE TABLE report ("
                    "report_id INTEGER PRIMARY KEY, "
                    "listing_id INTEGER, "
                    "target_user_id INTEGER, "
                    "tenant_id INTEGER NOT NULL, "
                    "admin_id INTEGER, "
                    "reason TEXT NOT NULL, "
                    "status TEXT NOT NULL, "
                    "details TEXT, "
                    "created_at DATETIME NOT NULL, "
                    "CONSTRAINT report_target_check CHECK "
                    "(listing_id IS NOT NULL OR target_user_id IS NOT NULL))",
                ),
            )
            connection.execute(
                text(
                    "INSERT INTO users (user_id) VALUES (7), (8)",
                ),
            )
            connection.execute(
                text(
                    "INSERT INTO listings (listing_id, landlord_id) "
                    "VALUES (12, 8)",
                ),
            )
            connection.execute(
                text(
                    "INSERT INTO contact_requests "
                    "(request_id, listing_id, tenant_id, status, requested_at) "
                    "VALUES (5, 12, 7, 'approved', '2026-10-30 08:00:00')",
                ),
            )

            with Operations.context(MigrationContext.configure(connection)):
                migration["upgrade"]()

            lead = connection.execute(
                text(
                    "SELECT contact_request_id, tenant_id, landlord_id, "
                    "listing_id, stage, billing_eligible, created_at "
                    "FROM leads",
                ),
            ).one()
            self.assertEqual(
                tuple(lead),
                (
                    5,
                    7,
                    8,
                    12,
                    "NEW",
                    0,
                    "2026-10-30 08:00:00",
                ),
            )
            history = connection.execute(
                text(
                    "SELECT from_stage, to_stage, actor_user_id, changed_at "
                    "FROM lead_stage_history",
                ),
            ).one()
            self.assertEqual(
                tuple(history),
                (None, "NEW", 7, "2026-10-30 08:00:00"),
            )
            self.assertIn(
                "lead_id",
                {
                    column["name"]
                    for column in inspect(connection).get_columns("report")
                },
            )
            self.assertIn(
                "report_target_check",
                {
                    constraint["name"]
                    for constraint in inspect(connection).get_check_constraints(
                        "report",
                    )
                },
            )
            with self.assertRaises(IntegrityError):
                connection.execute(
                    text(
                        "INSERT INTO leads "
                        "(contact_request_id, tenant_id, landlord_id, "
                        "listing_id, stage, billing_eligible, created_at, "
                        "updated_at) VALUES "
                        "(5, 7, 8, 12, 'NEW', false, "
                        "'2026-10-30 08:00:00', '2026-10-30 08:00:00')",
                    ),
                )

            connection.execute(
                text(
                    "INSERT INTO report "
                    "(report_id, lead_id, tenant_id, reason, status, "
                    "details, created_at) VALUES "
                    "(1, 1, 7, 'inaccurate_info', 'open', "
                    "'Lead stage is inaccurate.', '2026-10-30 08:00:00')",
                ),
            )
            with Operations.context(MigrationContext.configure(connection)):
                with self.assertRaisesRegex(RuntimeError, "lead-targeted"):
                    migration["downgrade"]()
            self.assertTrue(inspect(connection).has_table("leads"))
            connection.execute(text("DELETE FROM report WHERE report_id = 1"))

            with Operations.context(MigrationContext.configure(connection)):
                migration["downgrade"]()
            self.assertFalse(inspect(connection).has_table("leads"))
            self.assertNotIn(
                "lead_id",
                {
                    column["name"]
                    for column in inspect(connection).get_columns("report")
                },
            )

        engine.dispose()


if __name__ == "__main__":
    unittest.main()
