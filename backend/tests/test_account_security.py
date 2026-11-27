from datetime import datetime, timedelta, timezone
import hashlib
from unittest.mock import Mock, patch
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
import app.main
from app.api.v1.router import api_router
from app.core.config import Settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.base import Base
from app.db.session import get_db
from app.models.account_token import AccountToken
from app.models.user import User
from app.services.account_security_service import AccountSecurityService, InvalidAccountTokenError
from app.services.account_email import SMTPAccountEmailSender, EmailDeliveryError
from app.api.auth_limits import AuthRequestLimiter
from starlette.requests import Request


class AccountSecurityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(user_id=1, full_name='Test User', phone_no='+27829990000',
                         email='account@example.com', password_hash=hash_password('OldPassword123!'),
                         email_verification_required=True)
        self.db.add(self.user)
        self.db.commit()
        self.settings = Settings(database_url='sqlite://', auth_rate_limit_enabled=False,
                                 smtp_host=None, smtp_from_email=None, smtp_username=None, smtp_password=None)
        self.sender = Mock()
        self.service = AccountSecurityService(self.db, self.settings, self.sender)
        self.clock = patch.object(AccountSecurityService, 'now', return_value=datetime(2026, 11, 27, tzinfo=timezone.utc))
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.db.close()
        self.engine.dispose()

    def issue(self, purpose='verify_email'):
        self.service.send_link(self.user.email, purpose)
        return self.sender.send_link.call_args.args[2]

    def test_verification_is_hashed_expiring_single_use_and_wrong_purpose_fails(self):
        raw = self.issue()
        row = self.db.scalar(select(AccountToken))
        assert row.token_hash == hashlib.sha256(raw.encode()).hexdigest()
        assert raw not in repr(row.__dict__)
        with self.assertRaises(InvalidAccountTokenError):
            self.service.complete(raw, 'reset_password', 'NewPassword123!')
        self.service.complete(raw, 'verify_email')
        assert self.user.email_verified_at is not None
        with self.assertRaises(InvalidAccountTokenError):
            self.service.complete(raw, 'verify_email')

    def test_expired_and_unknown_tokens_do_not_change_account(self):
        raw = self.issue()
        with patch.object(self.service, 'now', return_value=datetime(2026, 11, 28, tzinfo=timezone.utc)):
            with self.assertRaises(InvalidAccountTokenError):
                self.service.complete(raw, 'verify_email')
        with self.assertRaises(InvalidAccountTokenError):
            self.service.complete('x' * 43, 'verify_email')
        assert self.user.email_verified_at is None

    def test_reset_changes_password_revokes_sessions_and_all_reset_links(self):
        first = self.issue('reset_password')
        with patch.object(self.service, 'now', return_value=self.service.now() + timedelta(minutes=2)):
            second = self.issue('reset_password')
        self.service.complete(first, 'reset_password', 'NewPassword123!')
        assert verify_password('NewPassword123!', self.user.password_hash)
        assert not verify_password('OldPassword123!', self.user.password_hash)
        assert self.user.auth_version == 1
        assert self.user.email_verified_at is None
        for token in [first, second]:
            with self.assertRaises(InvalidAccountTokenError):
                self.service.complete(token, 'reset_password', 'AnotherPassword123!')

    def test_unknown_email_verified_email_and_cooldown_do_not_send(self):
        self.service.send_link('unknown@example.com', 'verify_email')
        self.sender.send_link.assert_not_called()
        self.issue()
        self.service.send_link(self.user.email, 'verify_email')
        assert self.sender.send_link.call_count == 1
        self.user.email_verified_at = self.service.now()
        self.db.commit()
        with patch.object(self.service, 'now', return_value=self.service.now() + timedelta(minutes=2)):
            self.service.send_link(self.user.email, 'verify_email')
        assert self.sender.send_link.call_count == 1

    def test_hourly_email_quota_is_persistent(self):
        start = self.service.now()
        for minute in range(0, 12, 2):
            with patch.object(self.service, 'now', return_value=start + timedelta(minutes=minute)):
                self.service.send_link(self.user.email, 'reset_password')
        assert self.sender.send_link.call_count == 5

    def test_password_hash_failure_rolls_back_consumption(self):
        raw = self.issue('reset_password')
        with patch('app.services.account_security_service.hash_password', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.service.complete(raw, 'reset_password', 'NewPassword123!')
        self.service.complete(raw, 'reset_password', 'NewPassword123!')
        assert self.user.auth_version == 1

    def test_http_verification_gate_reset_and_legacy_session_compatibility(self):
        app = FastAPI()
        app.include_router(api_router)
        def db():
            with Session(self.engine) as session:
                yield session
        app.dependency_overrides[get_db] = db
        with TestClient(app) as client, patch('app.api.auth_limits.get_settings', return_value=self.settings):
            body = dict(email=self.user.email, password='OldPassword123!')
            blocked = client.post('/api/v1/auth/login', json=body)
            assert blocked.status_code == 403
            assert blocked.json()['detail']['code'] == 'EMAIL_NOT_VERIFIED'
            raw = self.issue()
            assert client.post('/api/v1/auth/verify-email', json={'token': raw}).status_code == 200
            login = client.post('/api/v1/auth/login', json=body)
            assert login.status_code == 200
            headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
            assert client.get('/api/v1/users/me', headers=headers).status_code == 200
            reset = self.issue('reset_password')
            response = client.post('/api/v1/auth/reset-password', json={'token': reset, 'password': 'NewPassword123!'})
            assert response.status_code == 200
            assert client.get('/api/v1/users/me', headers=headers).status_code == 401
            assert client.post('/api/v1/auth/login', json=body).status_code == 401
            assert client.post('/api/v1/auth/login', json={**body, 'password': 'NewPassword123!'}).status_code == 200
            self.db.refresh(self.user)
            self.user.email_verification_required = False
            self.user.email_verified_at = None
            self.user.auth_version = 0
            self.db.commit()
            old_token = create_access_token(self.user.user_id)
            assert client.get('/api/v1/users/me', headers={'Authorization': 'Bearer ' + old_token}).status_code == 200

    def test_email_requests_are_generic_and_never_return_tokens(self):
        app = FastAPI()
        app.include_router(api_router)
        with TestClient(app) as client, patch('app.api.v1.endpoints.auth.deliver_account_link') as deliver, patch(
                'app.api.auth_limits.get_settings', return_value=self.settings):
            for route in ['forgot-password', 'resend-verification']:
                a = client.post('/api/v1/auth/' + route, json={'email': self.user.email})
                b = client.post('/api/v1/auth/' + route, json={'email': 'unknown@example.com'})
                assert a.status_code == b.status_code == 202 and a.json() == b.json()
                assert set(a.json()) == {'message'}
            assert deliver.call_count == 4

    def test_registration_does_not_create_account_without_smtp_configuration(self):
        app = FastAPI()
        app.include_router(api_router)
        app.dependency_overrides[get_db] = lambda: Mock()
        with TestClient(app) as client, patch('app.api.v1.endpoints.auth.get_settings', return_value=self.settings), patch(
                'app.services.auth_service.AuthService.register') as register, patch(
                'app.api.auth_limits.get_settings', return_value=self.settings):
            response = client.post('/api/v1/auth/register', json={'full_name': 'Test User',
                'email': 'new@example.com', 'phone_no': '+27829990001', 'password': 'NewPassword123!', 'role': 'tenant'})
            assert response.status_code == 503
            register.assert_not_called()


class SMTPAndLimitTests(unittest.TestCase):
    def test_smtp_uses_tls_and_fixed_frontend_origin_with_fragment(self):
        settings = Settings(database_url='sqlite://', smtp_host='smtp.example.com', smtp_from_email='noreply@example.com',
                            frontend_public_url='https://rooms.example.com', smtp_username='account', smtp_password='secret')
        with patch('app.services.account_email.smtplib.SMTP') as transport:
            SMTPAccountEmailSender(settings).send_link('account@example.com', 'reset_password', 'token-value')
        smtp = transport.return_value.__enter__.return_value
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with('account', 'secret')
        message = smtp.send_message.call_args.args[0]
        assert 'https://rooms.example.com/reset-password#token=token-value' in message.get_content()

    def test_smtp_missing_config_and_insecure_remote_transport_fail(self):
        for settings in [Settings(database_url='sqlite://', smtp_host=None),
                         Settings(database_url='sqlite://', smtp_host='smtp.example.com', smtp_security='plain', smtp_from_email='noreply@example.com')]:
            with self.assertRaises(EmailDeliveryError):
                SMTPAccountEmailSender(settings).send_link('user@example.com', 'verify_email', 'value')

    def test_smtp_ssl_and_provider_errors_are_sanitized(self):
        import smtplib
        settings = Settings(database_url='sqlite://', smtp_host='smtp.example.com', smtp_from_email='noreply@example.com',
                            smtp_security='ssl', smtp_port=465)
        with patch('app.services.account_email.smtplib.SMTP_SSL') as transport:
            SMTPAccountEmailSender(settings).send_link('user@example.com', 'verify_email', 'secret-token')
            transport.return_value.__enter__.return_value.starttls.assert_not_called()
        with patch('app.services.account_email.smtplib.SMTP_SSL', side_effect=smtplib.SMTPException('secret-token user@example.com')):
            with self.assertRaises(EmailDeliveryError) as error:
                SMTPAccountEmailSender(settings).send_link('user@example.com', 'verify_email', 'secret-token')
            assert 'secret-token' not in str(error.exception) and '@' not in str(error.exception)

    def test_frontend_link_origin_rejects_untrusted_configuration(self):
        from pydantic import ValidationError
        for url in ['http://public.example.com', 'https://user:password@example.com', 'https://example.com?next=evil',
                    'javascript:alert(1)', 'https://example.com#fragment']:
            with self.assertRaises(ValidationError):
                Settings(database_url='sqlite://', frontend_public_url=url)

    def test_rate_limits_and_memory_bounds(self):
        limiter = AuthRequestLimiter()
        request = Request({'type': 'http', 'client': ('127.0.0.1', 1234)})
        with patch('app.api.auth_limits.get_settings', return_value=Settings(database_url='sqlite://', auth_rate_limit_enabled=True)):
            for _ in range(10):
                limiter.check(request, 'login', 'account@example.com')
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as caught:
                limiter.check(request, 'login', 'account@example.com')
            assert caught.exception.status_code == 429
