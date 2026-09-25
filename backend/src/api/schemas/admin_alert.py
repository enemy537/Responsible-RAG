"""
schemas/admin_alert.py — Admin alert models
=============================================
Used by the admin dashboard to surface system alerts such as embedding
API quota cooldowns.
"""


from pydantic import BaseModel, Field


class AdminAlertResponse(BaseModel):
    """A single system alert visible in the admin dashboard."""

    id: str = Field("", description="Alert ID (MongoDB ObjectId or index).")
    type: str = Field("", description="Alert type, e.g. 'system_error'.")
    severity: str = Field("info", description="'info', 'warning', or 'critical'.")
    title: str = Field("", description="Short alert title.")
    message: str = Field("", description="Detailed alert message.")
    cooldown_until: str | None = Field(None, description="ISO-8601 timestamp of cooldown expiry.")
    timestamp: str = Field("", description="ISO-8601 timestamp when the alert was created.")
    resolved: str = Field("false", description="'true' if the alert has been dismissed.")


class AdminAlertListResponse(BaseModel):
    """Paginated list of admin alerts."""

    alerts: list[AdminAlertResponse] = Field(default_factory=list)
    total: int = Field(0)
    unresolved_count: int = Field(0)
