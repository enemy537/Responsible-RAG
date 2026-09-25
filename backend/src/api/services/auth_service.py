"""Simple auth service — direct MongoDB ops, no classes. Matches fastapi_auth."""

import logging
from datetime import UTC, datetime
from urllib.parse import urlencode

import bcrypt as _bcrypt
import httpx
import jwt as pyjwt

from src.core.config import get_settings

logger = logging.getLogger(__name__)

# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())

# ── JWT ───────────────────────────────────────────────────────────────────────

def _now() -> int:
    return int(datetime.now(UTC).timestamp())

def create_token(data: dict, expires_delta: int | None = None) -> str:
    settings = get_settings()
    to_encode = data.copy()
    expire = _now() + (expires_delta if expires_delta is not None else settings.auth_token_expire_minutes * 60)
    to_encode["exp"] = expire
    return pyjwt.encode(to_encode, settings.auth_secret_key, algorithm=settings.auth_algorithm)

def decode_token(token: str) -> dict | None:
    settings = get_settings()
    try:
        return pyjwt.decode(token, settings.auth_secret_key, algorithms=[settings.auth_algorithm])
    except pyjwt.PyJWTError:
        return None

# ── Google OAuth ──────────────────────────────────────────────────────────────

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

def get_google_auth_url() -> str:
    settings = get_settings()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"

async def exchange_google_code(code: str) -> dict:
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()

async def get_google_user(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()

# ── Email verification ────────────────────────────────────────────────────────

def create_verification_token(email: str) -> str:
    return create_token({"sub": email, "purpose": "verify"}, expires_delta=60 * 24)

def get_backend_url() -> str:
    """Return the backend base URL, preferring the configured domain."""
    s = get_settings()
    if s.domain:
        return f"https://{s.domain}/api/v1"
    return "http://localhost:8000/api/v1"


def send_verification_email(to_email: str, token: str) -> None:
    settings = get_settings()
    verify_url = f"{get_backend_url()}/auth/verify-email?token={token}"

    if not settings.smtp_user or not settings.smtp_password:
        logger.info("SMTP not configured — verification URL for %s: %s", to_email, verify_url)
        return

    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Verify your email — Responsible RAG"
    msg["From"] = settings.smtp_from or "noreply@responsiblerag.com"
    msg["To"] = to_email

    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:0 auto;padding:32px">
      <h2 style="margin:0 0 16px">Verify your email</h2>
      <p style="color:#444;margin:0 0 24px">
        Click below to activate your account. Link expires in 24 hours.
      </p>
      <a href="{verify_url}"
         style="display:inline-block;padding:12px 28px;background:#000;color:#fff;
                text-decoration:none;border-radius:6px;font-weight:600">
        Verify Email
      </a>
      <p style="color:#999;font-size:13px;margin-top:32px">
        If you didn't register, ignore this email.
      </p>
    </div>
    """
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(msg["From"], to_email, msg.as_string())
        logger.info("Verification email sent to %s", to_email)
    except Exception as exc:
        logger.error("Failed to send verification email to %s: %s", to_email, exc)

# ── Serialize ─────────────────────────────────────────────────────────────────

# ── Password reset email ──────────────────────────────────────────────────────

def send_reset_email(to_email: str, token: str) -> None:
    settings = get_settings()
    reset_url = f"{settings.frontend_url}/auth/reset-password?token={token}"

    if not settings.smtp_user or not settings.smtp_password:
        logger.info("SMTP not configured — reset URL for %s: %s", to_email, reset_url)
        return

    import smtplib
    from email.mime.text import MIMEText

    msg = MIMEText(
        f"Click this link to reset your password: {reset_url}\n\nLink expires in 1 hour.",
        "plain",
    )
    msg["Subject"] = "Reset your password — Responsible RAG"
    msg["From"] = settings.smtp_from or "noreply@responsiblerag.com"
    msg["To"] = to_email

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(msg["From"], to_email, msg.as_string())
        logger.info("Reset email sent to %s", to_email)
    except Exception as exc:
        logger.error("Failed to send reset email to %s: %s", to_email, exc)


# ── Serialize ─────────────────────────────────────────────────────────────────

def serialize_user(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    doc.pop("hashed_password", None)
    return doc
