import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserResponse
from app.schemas.auth import AccountEmailRequest, AccountTokenRequest, PasswordResetRequest, AccountActionResponse
from app.api.auth_limits import auth_limiter
from app.services.account_security_service import AccountSecurityService, InvalidAccountTokenError, deliver_account_link
from app.services.auth_service import (
    AccountAlreadyExistsError,
    AuthService,
    RoleConfigurationError,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: RegisterRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
    db: Session = Depends(get_db),
) -> UserResponse:
    try:
        auth_limiter.check(http_request, 'register', str(request.email))
        settings = get_settings()
        if not settings.smtp_host or not settings.smtp_from_email or (settings.smtp_username and (
                settings.smtp_password is None or not settings.smtp_password.get_secret_value())):
            logger.error('account_smtp_not_configured')
            raise HTTPException(503, detail='Registration is temporarily unavailable. Please try again later.')
        user = AuthService(db).register(request)
    except AccountAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except RoleConfigurationError as exc:
        logger.exception("Registration is unavailable because a role is missing")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration is temporarily unavailable.",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("Registration failed because of a database error")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration is temporarily unavailable.",
        ) from exc

    background_tasks.add_task(deliver_account_link, str(request.email).casefold(), 'verify_email')
    return UserResponse.model_validate(user).model_copy(
        update={"roles": [request.role]},
    )


@router.post("/login", response_model=TokenResponse)
def login(
    request: LoginRequest,
    http_request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    try:
        auth_limiter.check(http_request, 'login', str(request.email))
        user = AuthService(db).authenticate(request)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if user.email_verification_required and user.email_verified_at is None:
            raise HTTPException(403, detail={'code': 'EMAIL_NOT_VERIFIED',
                'message': 'Verify your email before signing in. You can request another verification email.'})
        access_token = create_access_token(user.user_id, user.auth_version or 0)
    except SQLAlchemyError as exc:
        logger.exception("Login failed because of a database error")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Login is temporarily unavailable.",
        ) from exc
    except RuntimeError as exc:
        logger.exception("Login token configuration is unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Login is temporarily unavailable.",
        ) from exc

    return TokenResponse(
        access_token=access_token,
        expires_in=get_settings().access_token_expire_minutes * 60,
    )


@router.post('/resend-verification', response_model=AccountActionResponse, status_code=202)
def resend_verification(body: AccountEmailRequest, request: Request, background_tasks: BackgroundTasks):
    auth_limiter.check(request, 'verification-email', str(body.email))
    background_tasks.add_task(deliver_account_link, str(body.email).casefold(), 'verify_email')
    return AccountActionResponse(message='If this account needs verification, an email will be sent. Check your inbox and spam folder. Please wait a minute before requesting another.')


@router.post('/forgot-password', response_model=AccountActionResponse, status_code=202)
def forgot_password(body: AccountEmailRequest, request: Request, background_tasks: BackgroundTasks):
    auth_limiter.check(request, 'password-email', str(body.email))
    background_tasks.add_task(deliver_account_link, str(body.email).casefold(), 'reset_password')
    return AccountActionResponse(message='If an account matches this email, a password reset link will be sent. Check your inbox and spam folder. Please wait a minute before requesting another.')


def complete_account_action(token: str, purpose: str, db: Session, password: str | None = None):
    try:
        AccountSecurityService(db, get_settings()).complete(token, purpose, password)
    except InvalidAccountTokenError as exc:
        db.rollback()
        raise HTTPException(400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error('account_security_transaction_failed')
        raise HTTPException(503, detail='This request could not be completed. Please try again.') from exc


@router.post('/verify-email', response_model=AccountActionResponse)
def verify_email(body: AccountTokenRequest, request: Request, db: Session = Depends(get_db)):
    auth_limiter.check(request, 'verify-email')
    complete_account_action(body.token, 'verify_email', db)
    return AccountActionResponse(message='Your email is verified. You can now sign in.')


@router.post('/reset-password', response_model=AccountActionResponse)
def reset_password(body: PasswordResetRequest, request: Request, db: Session = Depends(get_db)):
    auth_limiter.check(request, 'reset-password')
    complete_account_action(body.token, 'reset_password', db, body.password.get_secret_value())
    return AccountActionResponse(message='Your password has changed. Sign in with your new password.')
