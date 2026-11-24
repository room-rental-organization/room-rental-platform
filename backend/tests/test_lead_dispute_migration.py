import runpy
import unittest
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


class LeadDisputeMigrationTests(unittest.TestCase):
    @staticmethod
    def load_migration() -> dict[str, object]:
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "versions"
            / "20261124_25_separate_lead_dispute_state.py"
        )
        return runpy.run_path(str(migration_path))

    @staticmethod
    def create_legacy_schema(connection) -> None:
        connection.execute(
            text(
                "CREATE TABLE leads ("
                "lead_id INTEGER PRIMARY KEY, "
                "contact_request_id INTEGER NOT NULL, "
                "tenant_id INTEGER NOT NULL, "
                "landlord_id INTEGER NOT NULL, "
                "listing_id INTEGER NOT NULL, "
                "stage VARCHAR(24) NOT NULL, "
                "rented_at DATETIME, "
                "unsuccessful_reason TEXT, "
                "billing_eligible BOOLEAN NOT NULL DEFAULT false, "
                "created_at DATETIME NOT NULL, "
                "updated_at DATETIME NOT NULL, "
                "CONSTRAINT leads_stage_check CHECK (stage IN "
                "('NEW', 'CONTACTED', 'VIEWING_SCHEDULED', "
                "'VIEWING_COMPLETED', 'INTERESTED', 'RENTED', "
                "'UNSUCCESSFUL', 'DISPUTED')))",
            ),
        )
        connection.execute(
            text(
                "CREATE TABLE lead_stage_history ("
                "history_id INTEGER PRIMARY KEY, "
                "lead_id INTEGER NOT NULL, "
                "from_stage VARCHAR(24), "
                "to_stage VARCHAR(24) NOT NULL, "
                "actor_user_id INTEGER NOT NULL, "
                "changed_at DATETIME NOT NULL, "
                "note TEXT)",
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
                "lead_id INTEGER, "
                "created_at DATETIME NOT NULL)",
            ),
        )

    def test_migration_restores_conversion_stage_and_preserves_history(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        migration = self.load_migration()

        with engine.begin() as connection:
            self.create_legacy_schema(connection)
            connection.execute(
                text(
                    "INSERT INTO leads (lead_id, contact_request_id, tenant_id, "
                    "landlord_id, listing_id, stage, billing_eligible, "
                    "created_at, updated_at) VALUES "
                    "(1, 11, 7, 8, 12, 'DISPUTED', true, "
                    "'2026-10-30', '2026-10-30'), "
                    "(2, 22, 7, 8, 13, 'DISPUTED', false, "
                    "'2026-10-31', '2026-10-31')",
                ),
            )
            connection.execute(
                text(
                    "INSERT INTO lead_stage_history "
                    "(history_id, lead_id, from_stage, to_stage, actor_user_id, "
                    "changed_at, note) VALUES "
                    "(1, 1, NULL, 'NEW', 7, '2026-10-30', NULL), "
                    "(2, 1, 'NEW', 'CONTACTED', 8, '2026-10-30', 'contacted'), "
                    "(3, 1, 'CONTACTED', 'DISPUTED', 7, '2026-10-30', NULL), "
                    "(4, 2, NULL, 'NEW', 7, '2026-10-31', NULL), "
                    "(5, 2, 'NEW', 'INTERESTED', 8, '2026-10-31', NULL), "
                    "(6, 2, 'INTERESTED', 'DISPUTED', 7, '2026-10-31', NULL)",
                ),
            )
            connection.execute(
                text(
                    "INSERT INTO report "
                    "(report_id, lead_id, tenant_id, reason, status, details, "
                    "created_at) VALUES "
                    "(1, 1, 7, 'inaccurate_info', 'under_review', 'active', "
                    "'2026-10-30'), "
                    "(2, 2, 7, 'inaccurate_info', 'dismissed', 'closed', "
                    "'2026-10-31')",
                ),
            )

            with Operations.context(MigrationContext.configure(connection)):
                migration["upgrade"]()

            leads = connection.execute(
                text(
                    "SELECT lead_id, stage, dispute_status, billing_eligible "
                    "FROM leads ORDER BY lead_id",
                ),
            ).all()
            self.assertEqual(
                [tuple(row) for row in leads],
                [
                    (1, "CONTACTED", "open", 0),
                    (2, "INTERESTED", "dismissed", 0),
                ],
            )
            history = connection.execute(
                text(
                    "SELECT COUNT(*) FROM lead_stage_history",
                ),
            ).scalar_one()
            self.assertEqual(history, 6)
            self.assertIn(
                "leads_open_dispute_not_billable_check",
                {
                    item["name"]
                    for item in inspect(connection).get_check_constraints(
                        "leads",
                    )
                },
            )
            with self.assertRaises(IntegrityError):
                connection.execute(
                    text(
                        "INSERT INTO report "
                        "(report_id, lead_id, tenant_id, reason, status, "
                        "details, created_at) VALUES "
                        "(3, 1, 7, 'inaccurate_info', 'open', 'duplicate', "
                        "'2026-11-01')",
                    ),
                )

            with Operations.context(MigrationContext.configure(connection)):
                with self.assertRaisesRegex(RuntimeError, "dispute state"):
                    migration["downgrade"]()

        engine.dispose()

    def test_migration_refuses_multiple_active_dispute_reports(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        migration = self.load_migration()

        with engine.begin() as connection:
            self.create_legacy_schema(connection)
            connection.execute(
                text(
                    "INSERT INTO leads (lead_id, contact_request_id, tenant_id, "
                    "landlord_id, listing_id, stage, created_at, updated_at) "
                    "VALUES (1, 11, 7, 8, 12, 'NEW', '2026-10-30', '2026-10-30')",
                ),
            )
            connection.execute(
                text(
                    "INSERT INTO report "
                    "(report_id, lead_id, tenant_id, reason, status, created_at) "
                    "VALUES (1, 1, 7, 'inaccurate_info', 'open', '2026-10-30'), "
                    "(2, 1, 7, 'inaccurate_info', 'under_review', '2026-10-30')",
                ),
            )

            with Operations.context(MigrationContext.configure(connection)):
                with self.assertRaisesRegex(RuntimeError, "multiple open"):
                    migration["upgrade"]()

            self.assertNotIn(
                "dispute_status",
                {
                    column["name"]
                    for column in inspect(connection).get_columns("leads")
                },
            )

        engine.dispose()


if __name__ == "__main__":
    unittest.main()
