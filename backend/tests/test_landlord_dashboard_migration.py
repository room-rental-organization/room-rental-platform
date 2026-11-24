import runpy
import unittest
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


class LandlordDashboardMigrationTests(unittest.TestCase):
    @staticmethod
    def load_migration() -> dict[str, object]:
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "versions"
            / "20261124_21_landlord_business_dashboard.py"
        )
        return runpy.run_path(str(migration_path))

    def test_migration_adds_availability_and_backfills_update_time(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        migration = self.load_migration()

        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE listings ("
                    "listing_id INTEGER PRIMARY KEY, "
                    "status TEXT NOT NULL, "
                    "created_at DATETIME NOT NULL)",
                ),
            )
            connection.execute(
                text(
                    "INSERT INTO listings (listing_id, status, created_at) "
                    "VALUES (1, 'active', '2026-10-01 09:00:00'), "
                    "(2, 'taken', '2026-10-02 09:00:00')",
                ),
            )

            with Operations.context(MigrationContext.configure(connection)):
                migration["upgrade"]()

            inspector = inspect(connection)
            self.assertTrue(
                {"availability_status", "updated_at"}.issubset(
                    {column["name"] for column in inspector.get_columns("listings")},
                ),
            )
            rows = connection.execute(
                text(
                    "SELECT listing_id, availability_status, created_at, "
                    "updated_at FROM listings ORDER BY listing_id",
                ),
            ).all()
            self.assertEqual(
                [(row.availability_status, row.updated_at) for row in rows],
                [
                    ("available", "2026-10-01 09:00:00"),
                    ("occupied", "2026-10-02 09:00:00"),
                ],
            )
            with self.assertRaises(IntegrityError):
                connection.execute(
                    text(
                        "UPDATE listings SET availability_status = 'unknown' "
                        "WHERE listing_id = 1",
                    ),
                )

            with Operations.context(MigrationContext.configure(connection)):
                migration["downgrade"]()
            self.assertNotIn(
                "availability_status",
                {column["name"] for column in inspect(connection).get_columns("listings")},
            )

        engine.dispose()


if __name__ == "__main__":
    unittest.main()
