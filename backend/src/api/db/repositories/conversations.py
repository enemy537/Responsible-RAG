"""Conversation and message collection access."""

from datetime import UTC, datetime

from src.api.db.repositories.base import MongoRepository, to_object_id
from src.api.errors import NotFoundError


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ConversationRepository(MongoRepository):
    """Conversation documents, always scoped to their owning user."""

    collection_name = "conversations"

    def list_for_user(self, user_id: str, page: int = 1, limit: int = 20) -> list[dict]:
        return list(
            self.collection.find({"user_id": user_id})
            .sort("updated_at", -1)
            .skip((page - 1) * limit)
            .limit(limit)
        )

    def count_for_user(self, user_id: str) -> int:
        return self.collection.count_documents({"user_id": user_id})

    def get_owned(self, conversation_id: str, user_id: str) -> dict | None:
        return self.collection.find_one(
            {
                "_id": to_object_id(conversation_id, label="conversation ID"),
                "user_id": user_id,
            }
        )

    def require_owned(self, conversation_id: str, user_id: str) -> dict:
        conversation = self.get_owned(conversation_id, user_id)
        if conversation is None:
            raise NotFoundError("Conversation not found")
        return conversation

    def create(self, doc: dict) -> dict:
        doc["_id"] = self.collection.insert_one(doc).inserted_id
        return doc

    def rename(self, conversation_id: str, user_id: str, title: str) -> dict:
        oid = to_object_id(conversation_id, label="conversation ID")
        result = self.collection.update_one(
            {"_id": oid, "user_id": user_id},
            {"$set": {"title": title, "updated_at": _now()}},
        )
        if result.matched_count == 0:
            raise NotFoundError("Conversation not found")
        return self.collection.find_one({"_id": oid})

    def delete(self, conversation_id: str, user_id: str) -> bool:
        result = self.collection.delete_one(
            {
                "_id": to_object_id(conversation_id, label="conversation ID"),
                "user_id": user_id,
            }
        )
        return result.deleted_count > 0

    def record_turn(self, conversation_id: str, *, memory: dict, last_message: str) -> None:
        """Persist memory, preview text and the message-count bump for one turn."""
        now = _now()
        self.collection.update_one(
            {"_id": to_object_id(conversation_id, label="conversation ID")},
            {
                "$set": {
                    "memory": memory,
                    "last_message": last_message,
                    "last_message_at": now,
                    "updated_at": now,
                },
                "$inc": {"message_count": 2},
            },
        )

    def last_for_user(self, user_id: str) -> dict | None:
        """Return the user's most recently updated conversation."""
        return self.collection.find_one({"user_id": user_id}, sort=[("updated_at", -1)])

    def ids_for_user(self, user_id: str) -> list[str]:
        return [str(doc["_id"]) for doc in self.collection.find({"user_id": user_id}, {"_id": 1})]

    def sum_message_count_for_user(self, user_id: str) -> int:
        """Total messages recorded across a user's conversations."""
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": None, "total": {"$sum": "$message_count"}}},
        ]
        result = list(self.collection.aggregate(pipeline))
        return result[0]["total"] if result else 0

    def delete_for_user(self, user_id: str) -> int:
        return self.collection.delete_many({"user_id": user_id}).deleted_count

    def count_all(self) -> int:
        return self.collection.count_documents({})


class MessageRepository(MongoRepository):
    """Messages belonging to conversations."""

    collection_name = "messages"

    def list_for_conversation(
        self, conversation_id: str, page: int = 1, limit: int = 50
    ) -> list[dict]:
        return list(
            self.collection.find({"conversation_id": conversation_id})
            .sort("created_at", 1)
            .skip((page - 1) * limit)
            .limit(limit)
        )

    def recent_for_conversation(self, conversation_id: str, limit: int = 8) -> list[dict]:
        """Return the *limit* most recent messages, oldest first."""
        cursor = (
            self.collection.find({"conversation_id": conversation_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        return list(reversed(list(cursor)))

    def count_for_conversation(self, conversation_id: str) -> int:
        return self.collection.count_documents({"conversation_id": conversation_id})

    def add(self, doc: dict) -> str:
        """Insert a message and return its generated id."""
        return str(self.collection.insert_one(doc).inserted_id)

    def delete_for_conversation(self, conversation_id: str) -> int:
        return self.collection.delete_many({"conversation_id": conversation_id}).deleted_count

    def delete_for_conversations(self, conversation_ids: list[str]) -> int:
        return self.collection.delete_many(
            {"conversation_id": {"$in": conversation_ids}}
        ).deleted_count

    def last_for_conversation(self, conversation_id: str) -> dict | None:
        """Return the most recent message in a conversation."""
        return self.collection.find_one(
            {"conversation_id": conversation_id}, sort=[("created_at", -1)]
        )

    def count_all(self) -> int:
        return self.collection.count_documents({})
