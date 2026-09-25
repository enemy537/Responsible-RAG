"""Consent collection access."""

from datetime import UTC, datetime

from src.api.db.repositories.base import MongoRepository


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ConsentRepository(MongoRepository):
    """CRUD access to the ``consent`` collection (keyed by user email)."""

    collection_name = "consent"

    def get(self, user_id: str) -> dict | None:
        return self.collection.find_one({"user_id": user_id})

    def has_research_consent(self, user_id: str) -> bool:
        doc = self.get(user_id) or {}
        return bool(doc.get("research_data_consent", False))

    def has_chat_history_consent(self, user_id: str, default: bool = True) -> bool:
        """Whether the user allows their conversations to be stored.

        Records written before this flag existed have no value for it and fall
        back to *default*, so existing history keeps working unchanged.
        """
        doc = self.get(user_id) or {}
        value = doc.get("chat_history_consent")
        return default if value is None else bool(value)

    def upsert(self, user_id: str, data: dict) -> dict:
        """Merge *data* into the user's consent record, creating it when absent."""
        now = _now()
        if self.collection.find_one({"user_id": user_id}):
            self.collection.update_one({"user_id": user_id}, {"$set": {**data, "updated_at": now}})
        else:
            self.collection.insert_one(
                {
                    **data,
                    "user_id": user_id,
                    "has_consented": True,
                    "consented_at": now,
                    "updated_at": now,
                }
            )
        return self.collection.find_one({"user_id": user_id})

    def delete(self, user_id: str) -> int:
        return self.collection.delete_many({"user_id": user_id}).deleted_count

    def count(self, query: dict | None = None) -> int:
        return self.collection.count_documents(query or {})
