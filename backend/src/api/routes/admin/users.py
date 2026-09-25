"""Admin user management."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.api.deps import get_user_service
from src.api.security import require_admin
from src.api.services.user_service import UserService

router = APIRouter()


class AdminUserUpdate(BaseModel):
    """Partial admin edit of a user account."""

    name: str | None = None
    password: str | None = None
    role: str | None = None
    verified: bool | None = None


@router.get("")
async def list_users(
    search: str | None = Query(None, description="Filter by name or email"),
    service: UserService = Depends(get_user_service),
    admin: dict = Depends(require_admin),
):
    """List users, newest first, with profile/consent/activity aggregates."""
    return service.list_users(search)


@router.get("/stats")
async def get_user_stats(
    service: UserService = Depends(get_user_service),
    admin: dict = Depends(require_admin),
):
    """Aggregate user statistics across the platform."""
    return service.stats()


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    service: UserService = Depends(get_user_service),
    admin: dict = Depends(require_admin),
):
    """Return a single user with aggregates."""
    return service.get_user(user_id)


@router.get("/{user_id}/profile")
async def get_user_profile(
    user_id: str,
    service: UserService = Depends(get_user_service),
    admin: dict = Depends(require_admin),
):
    """Return the user's demographic profile, redacted without consent."""
    return service.get_profile(user_id)


@router.get("/{user_id}/consent")
async def get_user_consent(
    user_id: str,
    service: UserService = Depends(get_user_service),
    admin: dict = Depends(require_admin),
):
    """Return the user's consent preferences."""
    return service.get_consent(user_id)


@router.get("/{user_id}/conversations")
async def get_user_conversations(
    user_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: UserService = Depends(get_user_service),
    admin: dict = Depends(require_admin),
):
    """List a user's conversations (requires research-data consent)."""
    return service.list_conversations(user_id, page, limit)


@router.get("/{user_id}/activity")
async def get_user_activity(
    user_id: str,
    service: UserService = Depends(get_user_service),
    admin: dict = Depends(require_admin),
):
    """Return aggregate activity statistics for a single user."""
    return service.get_activity(user_id)


@router.patch("/{user_id}")
async def update_user(
    user_id: str,
    body: AdminUserUpdate,
    service: UserService = Depends(get_user_service),
    admin: dict = Depends(require_admin),
):
    """Apply an admin edit to a user account."""
    return service.update_user(user_id, body.model_dump())


@router.delete("/{user_id}", status_code=200)
async def delete_user(
    user_id: str,
    service: UserService = Depends(get_user_service),
    admin: dict = Depends(require_admin),
):
    """Delete a user and every record owned by them."""
    service.delete_user(user_id)
    return {"message": "User and all associated data deleted"}
