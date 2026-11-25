"""Seed synthetic browser-test data in a dedicated, empty local PostgreSQL DB.

Never uses DATABASE_URL or the application's .env connection as a fallback.
"""

import os
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def seed() -> None:
    url = make_url(os.environ["E2E_DATABASE_URL"])
    if not (
        url.get_backend_name() == "postgresql"
        and url.host == "127.0.0.1"
        and url.port == 55433
        and url.database == "room_rental_frontend_e2e"
    ):
        raise RuntimeError("Browser fixtures require the dedicated local E2E database on port 55433.")
    os.environ["DATABASE_URL"] = str(url.render_as_string(hide_password=False))

    import app.main  # Registers the complete model metadata.
    from app.core.security import hash_password
    from app.db.base import Base
    from app.models.area import Area
    from app.models.listing import Listing
    from app.models.listing_moderation import ListingModeration
    from app.models.role import Role
    from app.models.user import User
    from app.models.user_role import UserRole
    from app.services.contact_request_service import ContactRequestService

    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            if inspect(connection).get_table_names():
                raise RuntimeError("The E2E database must be empty. Use a fresh disposable container.")
            for table in Base.metadata.sorted_tables:
                for column in table.columns:
                    if isinstance(column.type, ENUM):
                        column.type.create(connection, checkfirst=True)
            Base.metadata.create_all(connection)
        with Session(engine, expire_on_commit=False) as db:
            users = {}
            for index, name in enumerate(("tenant", "landlord", "admin"), start=1):
                role = Role(name=name)
                user = User(
                    full_name=f"{name.title()} Example",
                    phone_no=f"+2782000000{index}",
                    email=f"{name}@example.com",
                    password_hash=hash_password("LocalBrowserTest123!"),
                )
                db.add_all([role, user])
                db.flush()
                db.add(UserRole(user_id=user.user_id, role_id=role.role_id))
                users[name] = user
            area = Area(name="Browser test suburb")
            db.add(area)
            db.flush()
            for title in ("Garden room", "Sunny room", "Courtyard room", "Quiet room"):
                listing = Listing(
                    landlord_id=users["landlord"].user_id,
                    area_id=area.area_id,
                    title=title,
                    description="Synthetic room for local browser validation.",
                    room_type="single_room",
                    monthly_rent=2500,
                    deposit_amount=2500,
                    address="Synthetic test address",
                    date_available=date.today(),
                    status="active",
                    availability_status="available",
                )
                db.add(listing)
                db.flush()
                db.add(ListingModeration(listing_id=listing.listing_id, admin_id=users["admin"].user_id, decision="approved"))
            db.commit()
            for listing_id in (1, 2, 3, 4):
                ContactRequestService(db).create_request(users["tenant"].user_id, listing_id)
        print("Seeded four synthetic listings and enquiries in the dedicated local E2E database.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    seed()
