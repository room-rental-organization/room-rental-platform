from datetime import datetime, timedelta
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from app.models.account_token import AccountToken
from app.models.user import User


class AccountTokenRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def lock_user(self, user_id: int) -> User | None:
        return self.db.scalar(select(User).where(User.user_id == user_id)
                              .with_for_update().execution_options(populate_existing=True))

    def find(self, digest: str, purpose: str, now: datetime) -> AccountToken | None:
        return self.db.scalar(select(AccountToken).where(
            AccountToken.token_hash == digest, AccountToken.purpose == purpose,
            AccountToken.used_at.is_(None), AccountToken.expires_at > now))

    def can_issue(self, user_id: int, purpose: str, now: datetime) -> bool:
        count = self.db.scalar(select(func.count()).select_from(AccountToken).where(
            AccountToken.user_id == user_id, AccountToken.purpose == purpose,
            AccountToken.created_at > now - timedelta(hours=1))) or 0
        recent = self.db.scalar(select(AccountToken.token_hash).where(
            AccountToken.user_id == user_id, AccountToken.purpose == purpose,
            AccountToken.created_at > now - timedelta(seconds=60)).limit(1))
        return count < 5 and recent is None

    def consume(self, digest: str, purpose: str, now: datetime) -> bool:
        result = self.db.execute(update(AccountToken).where(
            AccountToken.token_hash == digest, AccountToken.purpose == purpose,
            AccountToken.used_at.is_(None), AccountToken.expires_at > now,
        ).values(used_at=now).execution_options(synchronize_session=False))
        return result.rowcount == 1

    def invalidate(self, user_id: int, purpose: str, now: datetime) -> None:
        self.db.execute(update(AccountToken).where(
            AccountToken.user_id == user_id, AccountToken.purpose == purpose,
            AccountToken.used_at.is_(None)).values(used_at=now).execution_options(synchronize_session=False))
