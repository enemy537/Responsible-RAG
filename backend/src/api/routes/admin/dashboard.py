"""Admin dashboard statistics."""

from fastapi import APIRouter, Depends

from src.api.db.repositories import AlertRepository
from src.api.deps import get_optional_alert_repository, get_source_service
from src.api.schemas.common import StatsResponse
from src.api.security import require_admin
from src.api.services.source_service import SourceService

router = APIRouter()


@router.get("/stats", response_model=StatsResponse)
def get_dashboard_stats(
    service: SourceService = Depends(get_source_service),
    alerts: AlertRepository | None = Depends(get_optional_alert_repository),
    admin: dict = Depends(require_admin),
):
    """Aggregate platform statistics for the dashboard.

    Source counts come from Qdrant, so the endpoint still responds when
    MongoDB is unavailable.
    """
    stats = service.get_stats()
    try:
        stats["unresolved_alerts"] = alerts.count_unresolved() if alerts else 0
    except Exception:
        stats["unresolved_alerts"] = 0
    return StatsResponse(**stats)
