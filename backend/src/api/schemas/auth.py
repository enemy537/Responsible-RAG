"""Authentication request and response schemas."""

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """Register a new account."""

    email: EmailStr = Field(..., description="User's email address.")
    password: str = Field(..., description="Account password.")
    name: str = Field(..., min_length=1, max_length=50, description="Display name.")


class LoginRequest(BaseModel):
    """Authenticate with an email address (or the literal ``admin``)."""

    email: str = Field(..., description="Registered email or admin username.")
    password: str = Field(..., description="Account password.")


class ForgotPasswordRequest(BaseModel):
    """Request a password-reset email."""

    email: EmailStr = Field(..., description="Email of the account to reset.")


class TokenResponse(BaseModel):
    """JWT access token returned after authentication."""

    access_token: str = Field(..., description="JWT access token.")
    token_type: str = Field("bearer", description="Token type.")
