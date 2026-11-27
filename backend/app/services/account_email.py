"""SMTP transport. Never log recipients, message bodies, credentials or link tokens."""
from email.message import EmailMessage
import smtplib
import ssl
from typing import Protocol
from app.core.config import Settings


class EmailDeliveryError(Exception):
    pass


class AccountEmailSender(Protocol):
    def send_link(self, recipient: str, purpose: str, token: str) -> None: ...


class SMTPAccountEmailSender:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send_link(self, recipient: str, purpose: str, token: str) -> None:
        settings = self.settings
        if not settings.smtp_host or not settings.smtp_from_email:
            raise EmailDeliveryError('Account email delivery is not configured.')
        if settings.smtp_security == 'plain' and settings.smtp_host not in {'localhost', '127.0.0.1'}:
            raise EmailDeliveryError('Unencrypted SMTP is restricted to localhost.')
        verify = purpose == 'verify_email'
        path = 'verify-email' if verify else 'reset-password'
        url = f'{settings.frontend_public_url}/{path}#token={token}'
        minutes = settings.email_verification_expire_minutes if verify else settings.password_reset_expire_minutes
        message = EmailMessage()
        message['From'] = settings.smtp_from_email
        message['To'] = recipient
        message['Subject'] = 'Verify your Room Rentals email' if verify else 'Reset your Room Rentals password'
        message.set_content(
            f"{'Verify your email address' if verify else 'Choose a new password'} using this link:\n\n"
            f'{url}\n\nThis link expires in {minutes} minutes and works once.\n'
            'If you did not request this email, you can ignore it.\n\nRoom Rentals')
        try:
            context = ssl.create_default_context()
            transport = smtplib.SMTP_SSL if settings.smtp_security == 'ssl' else smtplib.SMTP
            options = {'context': context} if settings.smtp_security == 'ssl' else {}
            with transport(settings.smtp_host, settings.smtp_port, timeout=10, **options) as smtp:
                if settings.smtp_security == 'starttls':
                    smtp.starttls(context=context)
                if settings.smtp_username:
                    if settings.smtp_password is None or not settings.smtp_password.get_secret_value():
                        raise EmailDeliveryError('SMTP credentials are incomplete.')
                    smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError, ValueError):
            raise EmailDeliveryError('Account email could not be delivered.') from None
