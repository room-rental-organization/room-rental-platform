import runpy
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


class TrustVerificationMigrationTests(unittest.TestCase):
    @staticmethod
    def load_migration() -> dict[str, object]:
        path = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "versions"
            / "20261124_22_trust_verification.py"
        )
        return runpy.run_path(str(path))

    def test_migration_creates_private_requests_audit_and_active_uniqueness(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        migration = self.load_migration()
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE users (user_id INTEGER PRIMARY KEY)",
                    ),
                )
                connection.execute(
                    text(
                        "CREATE TABLE listings (listing_id INTEGER PRIMARY KEY)",
                    ),
                )
                connection.execute(
                    text(
                        "CREATE TABLE report ("
                        "report_id INTEGER PRIMARY KEY, "
                        "tenant_id INTEGER NOT NULL, "
                        "created_at DATETIME NOT NULL)",
                    ),
                )

                with Operations.context(MigrationContext.configure(connection)):
                    original_execute = migration["op"].execute

                    def execute_without_postgres_enum_changes(
                        statement: object,
                        *args: object,
                        **kwargs: object,
                    ) -> object:
                        if str(statement).startswith("ALTER TYPE"):
                            return None
                        return original_execute(statement, *args, **kwargs)

                    with patch.object(
                        migration["op"],
                        "execute",
                        side_effect=execute_without_postgres_enum_changes,
                    ):
                        migration["upgrade"]()

                columns = {
                    column["name"]
                    for column in inspect(connection).get_columns(
                        "trust_verification_requests",
                    )
                }
                self.assertIn("evidence_statement", columns)
                self.assertIn("phone_verified_at", {
                    column["name"]
                    for column in inspect(connection).get_columns("users")
                })
                connection.execute(
                    text("INSERT INTO users (user_id) VALUES (7)"),
                )
                connection.execute(
                    text(
                        "INSERT INTO trust_verification_requests "
                        "(request_id, user_id, verification_type, status, "
                        "evidence_statement) VALUES "
                        "(1, 7, 'identity', 'pending', 'Private statement')",
                    ),
                )
                with self.assertRaises(IntegrityError):
                    connection.execute(
                        text(
                            "INSERT INTO trust_verification_requests "
                            "(request_id, user_id, verification_type, status, "
                            "evidence_statement) VALUES "
                            "(2, 7, 'identity', 'pending', 'Another statement')",
                        ),
                    )
                connection.execute(
                    text(
                        "UPDATE trust_verification_requests "
                        "SET status = 'rejected' WHERE request_id = 1",
                    ),
                )
                connection.execute(
                    text(
                        "INSERT INTO trust_verification_requests "
                        "(request_id, user_id, verification_type, status, "
                        "evidence_statement) VALUES "
                        "(3, 7, 'identity', 'pending', 'Resubmitted statement')",
                    ),
                )
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
