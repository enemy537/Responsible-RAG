"""Admin alert collection access."""

from src.api.db.repositories.base import MongoRepository, to_object_id
from src.api.errors import NotFoundError


class AlertRepository(MongoRepository):
    """System alerts raised by background jobs (e.g. embedding quota)."""

    collection_name = "admin_alerts"

    def list_recent(self, limit: int = 100) -> list[dict]:
        return list(self.collection.find().sort("timestamp", -1).limit(limit))

    def resolve(self, alert_id: str) -> None:
        result = self.collection.update_one(
            {"_id": to_object_id(alert_id, label="alert ID")},
            {"$set": {"resolved": "true"}},
        )
        if result.matched_count == 0:
            raise NotFoundError("Alert not found")

    def count_unresolved(self) -> int:
        return self.collection.count_documents({"resolved": "false"})
