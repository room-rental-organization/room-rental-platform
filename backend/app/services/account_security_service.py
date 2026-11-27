from datetime import datetime, timedelta, timezone
import hashlib
import logging
import secrets
from typing import Literal
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.core.config import Settings, get_settings
from app.core.security import hash_password
from app.db.session import get_session_factory
from app.models.account_token import AccountToken
from app.repositories.account_token_repository import AccountTokenRepository
from app.repositories.user_repository import UserRepository
from app.services.account_email import AccountEmailSender, EmailDeliveryError, SMTPAccountEmailSender

logger = logging.getLogger(__name__)
Purpose = Literal['verify_email', 'reset_password']


class InvalidAccountTokenError(Exception):
    pass


class AccountSecurityService:
    def __init__(self, db: Session, settings: Settings,
                 sender: AccountEmailSender | None = None) -> None:
        self.db, self.settings = db, settings
        self.tokens = AccountTokenRepository(db)
        self.users = UserRepository(db)
        self.sender = sender or SMTPAccountEmailSender(settings)

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    def send_link(self, email: str, purpose: Purpose) -> None:
        user = self.users.get_by_email(email.casefold())
        if user is None:
            return
        user = self.tokens.lock_user(user.user_id)
        if user is None or (purpose == 'verify_email' and user.email_verified_at is not None):
            return
        if purpose == 'reset_password' and user.password_hash is None:
            return
        now = self.now()
        if not self.tokens.can_issue(user.user_id, purpose, now):
            return
        raw = secrets.token_urlsafe(32)
        minutes = (self.settings.email_verification_expire_minutes if purpose == 'verify_email'
                   else self.settings.password_reset_expire_minutes)
        # Keep previously delivered links valid until used/expired, so an anonymous
        # resend cannot continuously invalidate a user's inbox. Completion revokes all.
        self.db.add(AccountToken(token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            user_id=user.user_id, purpose=purpose, created_at=now,
            expires_at=now + timedelta(minutes=minutes)))
        recipient = user.email
        self.db.commit()
        self.sender.send_link(recipient, purpose, raw)

    def complete(self, raw: str, purpose: Purpose, password: str | None = None) -> None:
        now = self.now()
        digest = hashlib.sha256(raw.encode()).hexdigest()
        candidate = self.tokens.find(digest, purpose, now)
        if candidate is None:
            raise InvalidAccountTokenError('This link is invalid or expired. Request a new email.')
        user = self.tokens.lock_user(candidate.user_id)
        if user is None or not self.tokens.consume(digest, purpose, self.now()):
            raise InvalidAccountTokenError('This link is invalid or expired. Request a new email.')
        try:
            if purpose == 'verify_email':
                user.email_verified_at = now
            else:
                if password is None:
                    raise ValueError('A new password is required.')
                user.password_hash = hash_password(password)
                user.auth_version = (user.auth_version or 0) + 1
                # A recovery link does not bypass the new-account verification gate.
            self.tokens.invalidate(user.user_id, purpose, now)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise


def deliver_account_link(email: str, purpose: Purpose) -> None:
    """Same background path for known/unknown emails; HTTP responses never reveal existence."""
    try:
        with get_session_factory()() as db:
            AccountSecurityService(db, get_settings()).send_link(email, purpose)
    except (EmailDeliveryError, SQLAlchemyError):
        # Never log the exception: provider messages/SQL can contain an email or token.
        logger.error('account_email_delivery_failed purpose=%s', purpose)
