"""Authentication routes: register, verify, login, reset, Google OAuth."""

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import RedirectResponse

from src.api.db.repositories import UserRepository
from src.api.deps import get_user_repository
from src.api.errors import (
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from src.api.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from src.api.security import get_current_user
from src.api.services.auth_service import (
    create_token,
    create_verification_token,
    decode_token,
    exchange_google_code,
    get_backend_url,
    get_google_auth_url,
    get_google_user,
    hash_password,
    send_reset_email,
    send_verification_email,
    serialize_user,
    verify_password,
)
from src.core.config import get_settings

router = APIRouter()

_ADMIN_USERNAME = "admin"
_ADMIN_TOKEN_TTL_SECONDS = 60 * 60
_RESET_TOKEN_TTL_SECONDS = 60
_RESET_SENT_MESSAGE = "If an account exists, a reset link has been sent."


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _smtp_disabled() -> bool:
    settings = get_settings()
    return not settings.smtp_user or not settings.smtp_password


def _is_admin_credentials(email: str, password: str) -> bool:
    """Admin credentials come from configuration, never from the database."""
    settings = get_settings()
    return password == settings.admin_password and (
        email == settings.admin_email or email.lower() == _ADMIN_USERNAME
    )


def _admin_token() -> TokenResponse:
    return TokenResponse(
        access_token=create_token(
            {"sub": _ADMIN_USERNAME, "role": "admin"},
            expires_delta=_ADMIN_TOKEN_TTL_SECONDS,
        )
    )


@router.post("/register", status_code=201)
async def register(
    body: RegisterRequest,
    background_tasks: BackgroundTasks,
    users: UserRepository = Depends(get_user_repository),
):
    """Create an account and send a verification email."""
    if users.get_by_email(body.email) is not None:
        raise ConflictError("Email already registered")

    users.insert(
        {
            "email": body.email,
            "name": body.name,
            "provider": "email",
            "role": "user",
            "hashed_password": hash_password(body.password),
            "verified": False,
            "onboarding_completed": False,
            "created_at": _now(),
            "google_id": None,
        }
    )

    token = create_verification_token(body.email)
    background_tasks.add_task(send_verification_email, body.email, token)

    response = {"message": "Registered. Check your email to verify your account."}
    if _smtp_disabled():
        response["dev_verify_url"] = f"{get_backend_url()}/auth/verify-email?token={token}"
    return response


@router.get("/verify-email")
async def verify_email(
    token: str,
    users: UserRepository = Depends(get_user_repository),
):
    """Mark the account verified and redirect to the login page."""
    payload = decode_token(token)
    if payload is None or payload.get("purpose") != "verify":
        raise ValidationError("Invalid token")

    result = users.update_by_email(payload["sub"], {"verified": True})
    if result.matched_count == 0:
        raise NotFoundError("User not found")

    return RedirectResponse(f"{get_settings().frontend_url}/login?verified=true")


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    users: UserRepository = Depends(get_user_repository),
):
    """Authenticate a user or the configured admin account."""
    if _is_admin_credentials(body.email, body.password):
        return _admin_token()

    user = users.get_by_email(body.email, provider="email")
    if user is None:
        raise UnauthorizedError("Invalid credentials")
    if not user.get("verified"):
        raise UnauthorizedError("Email not verified. Check your inbox.")
    if not verify_password(body.password, user.get("hashed_password") or ""):
        raise UnauthorizedError("Invalid credentials")

    needs_onboarding = not user.get("onboarding_completed", False)
    return TokenResponse(
        access_token=create_token(
            {
                "sub": user["email"],
                "role": user["role"],
                "onboarding": needs_onboarding,
            }
        )
    )


@router.post("/admin/login", response_model=TokenResponse)
async def admin_login(body: LoginRequest):
    """Authenticate against the environment-configured admin account."""
    if not _is_admin_credentials(body.email, body.password):
        raise UnauthorizedError("Invalid admin credentials")
    return _admin_token()


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    users: UserRepository = Depends(get_user_repository),
):
    """Email a reset link; always reports success to avoid enumeration."""
    if users.get_by_email(body.email, provider="email") is None:
        return {"message": _RESET_SENT_MESSAGE}

    reset_token = create_token(
        {"sub": body.email, "purpose": "reset"},
        expires_delta=_RESET_TOKEN_TTL_SECONDS,
    )
    users.update_by_email(body.email, {"reset_token": reset_token})
    send_reset_email(body.email, reset_token)

    response = {"message": _RESET_SENT_MESSAGE}
    if _smtp_disabled():
        response["dev_reset_url"] = (
            f"{get_settings().frontend_url}/auth/reset-password?token={reset_token}"
        )
    return response


@router.post("/reset-password")
async def reset_password(
    token: str,
    password: str,
    users: UserRepository = Depends(get_user_repository),
):
    """Set a new password using a valid reset token."""
    payload = decode_token(token)
    if (
        payload is None
        or payload.get("purpose") != "reset"
        or users.get_by_email(payload["sub"], reset_token=token) is None
    ):
        raise ValidationError("Invalid or expired reset token")

    users.update_by_email(
        payload["sub"],
        {"hashed_password": hash_password(password), "reset_token": None},
    )
    return {"message": "Password reset successful. You can now sign in."}


@router.get("/google")
async def google_login():
    """Redirect to Google's OAuth consent screen."""
    return RedirectResponse(get_google_auth_url())


@router.get("/google/callback")
async def google_callback(
    code: str,
    users: UserRepository = Depends(get_user_repository),
):
    """Exchange the OAuth code, upsert the user, and redirect with a token."""
    try:
        token_data = await exchange_google_code(code)
        google_user = await get_google_user(token_data["access_token"])
    except Exception as exc:
        raise ValidationError(f"Google OAuth error: {exc}") from exc

    email = google_user["email"]
    existing = users.get_by_email(email)
    if existing:
        role = existing.get("role", "user")
        # Existing accounts that never finished onboarding are treated as new.
        is_new = not existing.get("onboarding_completed", False)
    else:
        users.insert(
            {
                "email": email,
                "name": google_user.get("name", ""),
                "provider": "google",
                "role": "user",
                "hashed_password": None,
                "verified": True,
                "onboarding_completed": False,
                "created_at": _now(),
                "google_id": google_user["id"],
            }
        )
        role, is_new = "user", True

    token = create_token({"sub": email, "role": role, "onboarding": is_new})
    return RedirectResponse(
        f"{get_settings().frontend_url}/auth/callback?token={token}&is_new={str(is_new).lower()}"
    )


@router.post("/onboarding/complete")
async def complete_onboarding(
    users: UserRepository = Depends(get_user_repository),
    current_user: dict = Depends(get_current_user),
):
    """Mark the current user's onboarding as finished."""
    result = users.update_by_email(current_user["sub"], {"onboarding_completed": True})
    if result.matched_count == 0:
        raise NotFoundError("User not found")
    return {"status": "ok"}


@router.get("/me")
async def get_me(
    users: UserRepository = Depends(get_user_repository),
    current_user: dict = Depends(get_current_user),
):
    """Return the authenticated user's public profile."""
    if current_user.get("role") == "admin":
        return {
            "id": _ADMIN_USERNAME,
            "email": current_user["sub"],
            "name": "Admin",
            "role": "admin",
            "verified": True,
        }

    user = users.get_by_email(current_user["sub"])
    if user is None:
        raise NotFoundError("User not found")
    return serialize_user(user)
