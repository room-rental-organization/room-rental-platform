import runpy
import unittest
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


class ContactRequestPendingMigrationTests(unittest.TestCase):
    @staticmethod
    def load_migration() -> dict[str, object]:
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "versions"
            / "20261124_24_one_pending_contact_request.py"
        )
        return runpy.run_path(str(migration_path))

    @staticmethod
    def create_contact_requests(connection: object) -> None:
        connection.execute(
            text(
                "CREATE TABLE contact_requests ("
                "request_id INTEGER PRIMARY KEY, "
                "listing_id INTEGER NOT NULL, "
                "tenant_id INTEGER NOT NULL, "
                "status TEXT NOT NULL)",
            ),
        )

    def test_partial_unique_index_blocks_second_pending_request(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        migration = self.load_migration()

        with engine.begin() as connection:
            self.create_contact_requests(connection)
            connection.execute(
                text(
                    "INSERT INTO contact_requests "
                    "(request_id, listing_id, tenant_id, status) "
                    "VALUES (1, 14, 7, 'approved')",
                ),
            )
            with Operations.context(MigrationContext.configure(connection)):
                migration["upgrade"]()

            connection.execute(
                text(
                    "INSERT INTO contact_requests "
                    "(request_id, listing_id, tenant_id, status) "
                    "VALUES (2, 14, 7, 'pending')",
                ),
            )
            with self.assertRaises(IntegrityError):
                connection.execute(
                    text(
                        "INSERT INTO contact_requests "
                        "(request_id, listing_id, tenant_id, status) "
                        "VALUES (3, 14, 7, 'pending')",
                    ),
                )

            connection.execute(
                text(
                    "UPDATE contact_requests SET status = 'rejected' "
                    "WHERE request_id = 2",
                ),
            )
            connection.execute(
                text(
                    "INSERT INTO contact_requests "
                    "(request_id, listing_id, tenant_id, status) "
                    "VALUES (4, 14, 7, 'pending')",
                ),
            )
            with Operations.context(MigrationContext.configure(connection)):
                migration["downgrade"]()
            self.assertNotIn(
                "contact_requests_one_pending_per_tenant_listing_idx",
                {
                    index["name"]
                    for index in inspect(connection).get_indexes(
                        "contact_requests",
                    )
                },
            )

        engine.dispose()

    def test_migration_refuses_existing_pending_duplicates(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        migration = self.load_migration()

        with engine.begin() as connection:
            self.create_contact_requests(connection)
            connection.execute(
                text(
                    "INSERT INTO contact_requests "
                    "(request_id, listing_id, tenant_id, status) VALUES "
                    "(1, 14, 7, 'pending'), "
                    "(2, 14, 7, 'pending')",
                ),
            )
            with Operations.context(MigrationContext.configure(connection)):
                with self.assertRaisesRegex(RuntimeError, "Resolve duplicates"):
                    migration["upgrade"]()

            self.assertNotIn(
                "contact_requests_one_pending_per_tenant_listing_idx",
                {
                    index["name"]
                    for index in inspect(connection).get_indexes(
                        "contact_requests",
                    )
                },
            )

        engine.dispose()


if __name__ == "__main__":
    unittest.main()
