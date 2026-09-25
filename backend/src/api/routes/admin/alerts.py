"""Admin system alerts."""

from fastapi import APIRouter, Depends

from src.api.db.repositories import AlertRepository
from src.api.deps import get_alert_repository
from src.api.schemas.admin_alert import AdminAlertListResponse, AdminAlertResponse
from src.api.security import require_admin

router = APIRouter()


@router.get("", response_model=AdminAlertListResponse)
def list_alerts(
    repository: AlertRepository = Depends(get_alert_repository),
    admin: dict = Depends(require_admin),
):
    """Return all system alerts, newest first."""
    alerts = [_doc_to_alert(doc) for doc in repository.list_recent()]
    return AdminAlertListResponse(
        alerts=[AdminAlertResponse(**alert) for alert in alerts],
        total=len(alerts),
        unresolved_count=sum(1 for alert in alerts if alert.get("resolved", "false") == "false"),
    )


@router.post("/resolve")
def resolve_alert(
    alert_id: str,
    repository: AlertRepository = Depends(get_alert_repository),
    admin: dict = Depends(require_admin),
):
    """Mark a specific alert as resolved."""
    repository.resolve(alert_id)
    return {"status": "resolved", "alert_id": alert_id}


def _doc_to_alert(doc: dict) -> dict:
    """Convert a MongoDB document into an ``AdminAlertResponse``-shaped dict."""
    alert = dict(doc)
    alert["id"] = str(alert.pop("_id", ""))
    return alert
