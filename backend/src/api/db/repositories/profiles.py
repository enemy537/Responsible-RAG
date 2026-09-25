"""Profile collection access."""

from datetime import UTC, datetime

from src.api.db.repositories.base import MongoRepository


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ProfileRepository(MongoRepository):
    """CRUD access to the ``profiles`` collection (keyed by user email)."""

    collection_name = "profiles"

    def get(self, user_id: str) -> dict | None:
        return self.collection.find_one({"user_id": user_id})

    def upsert(self, user_id: str, data: dict) -> dict:
        """Merge *data* into the user's profile, creating it when absent."""
        now = _now()
        if self.collection.find_one({"user_id": user_id}):
            self.collection.update_one({"user_id": user_id}, {"$set": {**data, "updated_at": now}})
        else:
            self.collection.insert_one(
                {**data, "user_id": user_id, "created_at": now, "updated_at": now}
            )
        return self.collection.find_one({"user_id": user_id})

    def delete(self, user_id: str) -> int:
        return self.collection.delete_many({"user_id": user_id}).deleted_count

    def count(self, query: dict | None = None) -> int:
        return self.collection.count_documents(query or {})
