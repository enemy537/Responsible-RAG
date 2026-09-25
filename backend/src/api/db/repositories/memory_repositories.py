"""In-memory conversation storage for users who declined history storage.

These implement the same surface as the MongoDB repositories, so ``ChatService``
is unaware of which backing store it uses. Everything lives in this worker
process only: conversations are evicted once they have been idle for
``ttl_seconds``, so a session's history is gone when the session ends (or the
process restarts). Nothing is ever written to MongoDB.
"""

import logging
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from src.api.errors import NotFoundError

logger = logging.getLogger(__name__)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class _TtlStore:
    """Small TTL + size-bounded key/value store."""

    def __init__(self, ttl_seconds: int, max_items: int) -> None:
        self._ttl = ttl_seconds
        self._max_items = max_items
        self._items: dict[str, tuple[float, object]] = {}

    def _evict(self) -> None:
        cutoff = monotonic() - self._ttl
        expired = [key for key, (touched, _) in self._items.items() if touched < cutoff]
        for key in expired:
            del self._items[key]
        if expired:
            logger.debug("Evicted %d expired ephemeral records.", len(expired))

        if len(self._items) > self._max_items:
            oldest = sorted(self._items, key=lambda key: self._items[key][0])
            for key in oldest[: len(self._items) - self._max_items]:
                del self._items[key]

    def put(self, key: str, value: object) -> None:
        self._evict()
        self._items[key] = (monotonic(), value)

    def get(self, key: str) -> object | None:
        self._evict()
        entry = self._items.get(key)
        return entry[1] if entry else None

    def touch(self, key: str) -> None:
        entry = self._items.get(key)
        if entry:
            self._items[key] = (monotonic(), entry[1])

    def delete(self, key: str) -> None:
        self._items.pop(key, None)

    def values(self) -> list[object]:
        """All live values, evicting expired entries first."""
        self._evict()
        return [value for _, value in self._items.values()]


class InMemoryConversationRepository:
    """Ephemeral stand-in for ``ConversationRepository``."""

    collection_name = "conversations_ephemeral"

    def __init__(self, *, ttl_seconds: int = 3600, max_conversations: int = 200) -> None:
        self._store = _TtlStore(ttl_seconds, max_conversations)

    def _docs(self) -> list[dict]:
        return [doc for doc in self._store.values() if isinstance(doc, dict)]

    def list_for_user(self, user_id: str, page: int = 1, limit: int = 20) -> list[dict]:
        owned = [doc for doc in self._docs() if doc["user_id"] == user_id]
        owned.sort(key=lambda doc: doc.get("updated_at", ""), reverse=True)
        start = (page - 1) * limit
        return owned[start : start + limit]

    def count_for_user(self, user_id: str) -> int:
        return len([doc for doc in self._docs() if doc["user_id"] == user_id])

    def get_owned(self, conversation_id: str, user_id: str) -> dict | None:
        doc = self._store.get(conversation_id)
        if isinstance(doc, dict) and doc.get("user_id") == user_id:
            return doc
        return None

    def require_owned(self, conversation_id: str, user_id: str) -> dict:
        conversation = self.get_owned(conversation_id, user_id)
        if conversation is None:
            raise NotFoundError("Conversation not found")
        return conversation

    def create(self, doc: dict) -> dict:
        stored = {**doc, "_id": _new_id("eph")}
        self._store.put(stored["_id"], stored)
        return stored

    def rename(self, conversation_id: str, user_id: str, title: str) -> dict:
        conversation = self.require_owned(conversation_id, user_id)
        conversation["title"] = title
        conversation["updated_at"] = _now()
        self._store.touch(conversation_id)
        return conversation

    def delete(self, conversation_id: str, user_id: str) -> bool:
        if self.get_owned(conversation_id, user_id) is None:
            return False
        self._store.delete(conversation_id)
        return True

    def record_turn(self, conversation_id: str, *, memory: dict, last_message: str) -> None:
        conversation = self._store.get(conversation_id)
        if not isinstance(conversation, dict):
            return
        now = _now()
        conversation.update(
            {
                "memory": memory,
                "last_message": last_message,
                "last_message_at": now,
                "updated_at": now,
                "message_count": conversation.get("message_count", 0) + 2,
            }
        )
        self._store.touch(conversation_id)

    def ids_for_user(self, user_id: str) -> list[str]:
        return [doc["_id"] for doc in self._docs() if doc["user_id"] == user_id]

    def last_for_user(self, user_id: str) -> dict | None:
        conversations = self.list_for_user(user_id, limit=1)
        return conversations[0] if conversations else None

    def sum_message_count_for_user(self, user_id: str) -> int:
        return sum(
            doc.get("message_count", 0)
            for doc in self._docs()
            if doc["user_id"] == user_id
        )

    def delete_for_user(self, user_id: str) -> int:
        ids = self.ids_for_user(user_id)
        for conversation_id in ids:
            self._store.delete(conversation_id)
        return len(ids)

    def count_all(self) -> int:
        return len(self._docs())


class InMemoryMessageRepository:
    """Ephemeral stand-in for ``MessageRepository``."""

    collection_name = "messages_ephemeral"

    def __init__(self, *, ttl_seconds: int = 3600, max_conversations: int = 200) -> None:
        self._store = _TtlStore(ttl_seconds, max_conversations * 20)

    def _messages(self, conversation_id: str) -> list[dict]:
        stored = self._store.get(conversation_id)
        return stored if isinstance(stored, list) else []

    def list_for_conversation(
        self, conversation_id: str, page: int = 1, limit: int = 50
    ) -> list[dict]:
        start = (page - 1) * limit
        return self._messages(conversation_id)[start : start + limit]

    def recent_for_conversation(self, conversation_id: str, limit: int = 8) -> list[dict]:
        return self._messages(conversation_id)[-limit:]

    def count_for_conversation(self, conversation_id: str) -> int:
        return len(self._messages(conversation_id))

    def add(self, doc: dict) -> str:
        conversation_id = doc.get("conversation_id", "")
        messages = list(self._messages(conversation_id))
        message_id = _new_id("msg-e")
        messages.append({**doc, "_id": message_id})
        self._store.put(conversation_id, messages)
        return message_id

    def delete_for_conversation(self, conversation_id: str) -> int:
        count = len(self._messages(conversation_id))
        self._store.delete(conversation_id)
        return count

    def delete_for_conversations(self, conversation_ids: list[str]) -> int:
        return sum(self.delete_for_conversation(cid) for cid in conversation_ids)

    def last_for_conversation(self, conversation_id: str) -> dict | None:
        messages = self._messages(conversation_id)
        return messages[-1] if messages else None

    def count_all(self) -> int:
        return sum(
            len(entry) for entry in self._store.values() if isinstance(entry, list)
        )
