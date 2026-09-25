"""
schemas/common.py — Shared Pydantic models
============================================
Reusable types used across multiple endpoint groups.
"""

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error payload returned on 4xx/5xx responses."""

    detail: str = Field(
        ..., description="Human-readable error message.",
        example="Email already registered.",
    )
    code: str | None = Field(
        None, description="Machine-readable error code.",
        example="EMAIL_EXISTS",
    )


class PaginationParams(BaseModel):
    """Query parameters for paginated list endpoints."""

    page: int = Field(default=1, ge=1, description="Page number (1-based).")
    limit: int = Field(default=20, ge=1, le=100, description="Items per page (max 100).")
    sort_by: str | None = Field(None, description="Field to sort by.")
    sort_order: str | None = Field("desc", description="'asc' or 'desc'.")


class PaginatedResponse(BaseModel):
    """Wrapper for paginated list responses."""

    items: list[Any] = Field(..., description="List of items for this page.")
    total: int = Field(..., description="Total number of items across all pages.")
    page: int = Field(..., description="Current page number.")
    limit: int = Field(..., description="Items per page.")
    pages: int = Field(..., description="Total number of pages.")


class StatsResponse(BaseModel):
    """Generic key-value stats response (used by admin dashboard)."""

    total_sources: int = Field(0, description="Total documents in knowledge base.")
    indexed_sources: int = Field(0, description="Fully indexed documents.")
    processing_sources: int = Field(0, description="Currently processing.")
    error_sources: int = Field(0, description="Documents with errors.")
    total_conversations: int = Field(0, description="Total conversations across all users.")
    total_users: int = Field(0, description="Total registered users.")
    incomplete_metadata: int = Field(0, description="Sources missing required fields.")
    unresolved_alerts: int = Field(0, description="Number of unresolved system alerts.")
