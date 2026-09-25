"""Tests for chat-history consent and the ephemeral (in-memory) store.

Covers the rule that conversations are only written to MongoDB when the user
allows it; otherwise they live in the worker's memory and expire with the
session.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from src.api.db.repositories import (
    ConsentRepository,
    ConversationRepository,
    InMemoryConversationRepository,
    InMemoryMessageRepository,
    MessageRepository,
    ProfileRepository,
)
from src.api.deps import get_chat_service
from src.api.errors import NotFoundError


class FakeCollection:
    def __init__(self, docs: list[dict] | None = None) -> None:
        self.docs = docs or []
        self.inserted: list[dict] = []
        self.updates: list[dict] = []

    def find_one(self, query=None, *args, **kwargs):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in (query or {}).items()):
                return doc
        return None

    def insert_one(self, doc):
        self.inserted.append(doc)
        return type("Result", (), {"inserted_id": "fake"})()

    def update_one(self, *args, **kwargs):
        self.updates.append({"args": args, "kwargs": kwargs})
        return type("Result", (), {"matched_count": 1, "modified_count": 1})()


class FakeDatabase:
    """Minimal Mongo stand-in that records writes."""

    def __init__(self, consent_doc: dict | None = None) -> None:
        self.collections: dict[str, FakeCollection] = {}
        if consent_doc:
            self.collections["consent"] = FakeCollection([consent_doc])

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())

    def written_documents(self) -> list[dict]:
        return [
            doc
            for collection in self.collections.values()
            for doc in collection.inserted
        ]


def build_service(db, email: str):
    return get_chat_service(
        conversations=ConversationRepository(db),
        messages=MessageRepository(db),
        profiles=ProfileRepository(db),
        consent=ConsentRepository(db),
        current_user={"sub": email},
    )


class TestChatHistoryConsentFlag:
    def test_defaults_to_allowed_when_the_flag_is_absent(self):
        db = FakeDatabase({"user_id": "legacy@example.com", "profile_mode": "full"})

        assert ConsentRepository(db).has_chat_history_consent("legacy@example.com") is True

    def test_respects_an_explicit_denial(self):
        db = FakeDatabase({"user_id": "private@example.com", "chat_history_consent": False})

        assert (
            ConsentRepository(db).has_chat_history_consent("private@example.com") is False
        )

    def test_default_can_be_overridden(self):
        db = FakeDatabase({"user_id": "new@example.com"})

        assert (
            ConsentRepository(db).has_chat_history_consent("new@example.com", default=False)
            is False
        )

    def test_missing_consent_record_uses_the_default(self):
        assert ConsentRepository(FakeDatabase()).has_chat_history_consent("nobody@example.com")


class TestStorageSelection:
    def test_consent_off_selects_the_in_memory_store(self):
        db = FakeDatabase({"user_id": "private@example.com", "chat_history_consent": False})

        service = build_service(db, "private@example.com")

        assert isinstance(service._conversations, InMemoryConversationRepository)
        assert isinstance(service._messages, InMemoryMessageRepository)

    def test_consent_on_selects_the_mongo_store(self):
        db = FakeDatabase({"user_id": "open@example.com", "chat_history_consent": True})

        service = build_service(db, "open@example.com")

        assert isinstance(service._conversations, ConversationRepository)
        assert isinstance(service._messages, MessageRepository)

    def test_declined_history_is_never_written_to_the_database(self):
        email = "private@example.com"
        db = FakeDatabase({"user_id": email, "chat_history_consent": False})
        service = build_service(db, email)

        turn = service.begin_turn(
            email, question="A private question", profile_key=None, conversation_id=None
        )
        service.finish_turn(
            turn, question="A private question", answer="A private answer", citations=[]
        )

        assert db.written_documents() == []
        assert service.list_conversations(email)["total"] == 1
        conversation = service.get_conversation(email, turn.conversation_id)
        assert conversation["title"] == "A private question"
        assert len(conversation["messages"]) == 2

    def test_ephemeral_history_still_supports_a_second_turn(self):
        email = "private2@example.com"
        db = FakeDatabase({"user_id": email, "chat_history_consent": False})
        service = build_service(db, email)

        first = service.begin_turn(
            email, question="First", profile_key=None, conversation_id=None
        )
        service.finish_turn(first, question="First", answer="One", citations=[])

        second = service.begin_turn(
            email,
            question="Second",
            profile_key=None,
            conversation_id=first.conversation_id,
        )
        service.finish_turn(second, question="Second", answer="Two", citations=[])

        assert second.conversation_id == first.conversation_id
        assert second.prior_message_count == 2
        assert len(service.list_messages(email, first.conversation_id)) == 4
        assert db.written_documents() == []

    def test_users_cannot_see_each_others_ephemeral_conversations(self):
        db = FakeDatabase({"user_id": "owner@example.com", "chat_history_consent": False})
        db["consent"].docs.append(
            {"user_id": "other@example.com", "chat_history_consent": False}
        )
        owner = build_service(db, "owner@example.com")
        turn = owner.begin_turn(
            "owner@example.com", question="Mine", profile_key=None, conversation_id=None
        )
        owner.finish_turn(turn, question="Mine", answer="Answer", citations=[])

        other = build_service(db, "other@example.com")

        assert owner.list_conversations("owner@example.com")["total"] == 1
        assert other.list_conversations("other@example.com")["total"] == 0
        with pytest.raises(NotFoundError):
            other.get_conversation("other@example.com", turn.conversation_id)


class TestInMemoryRepositories:
    def test_conversation_lifecycle(self):
        conversations = InMemoryConversationRepository()
        created = conversations.create({"user_id": "u1", "title": "T", "message_count": 0})

        assert conversations.count_for_user("u1") == 1
        assert conversations.require_owned(created["_id"], "u1")["title"] == "T"

        renamed = conversations.rename(created["_id"], "u1", "New title")
        assert renamed["title"] == "New title"
        assert conversations.list_for_user("u1")[0]["title"] == "New title"

        conversations.record_turn(created["_id"], memory={"summary": "s"}, last_message="hi")
        assert conversations.require_owned(created["_id"], "u1")["message_count"] == 2

        assert conversations.delete(created["_id"], "u1") is True
        assert conversations.count_for_user("u1") == 0

    def test_messages_are_scoped_and_ordered(self):
        messages = InMemoryMessageRepository()
        messages.add({"conversation_id": "c1", "role": "user", "content": "one"})
        messages.add({"conversation_id": "c1", "role": "assistant", "content": "two"})
        messages.add({"conversation_id": "c2", "role": "user", "content": "other"})

        assert messages.count_for_conversation("c1") == 2
        assert [m["content"] for m in messages.list_for_conversation("c1")] == ["one", "two"]
        assert messages.last_for_conversation("c1")["content"] == "two"
        assert messages.recent_for_conversation("c1", limit=1)[0]["content"] == "two"

        assert messages.delete_for_conversation("c1") == 2
        assert messages.count_for_conversation("c1") == 0

    def test_records_expire_after_the_ttl(self):
        conversations = InMemoryConversationRepository(ttl_seconds=0)
        conversations.create({"user_id": "u1", "title": "T"})

        assert conversations.count_for_user("u1") == 0

    def test_oldest_conversation_is_evicted_past_the_cap(self):
        conversations = InMemoryConversationRepository(max_conversations=1)
        conversations.create({"user_id": "u1", "title": "first"})
        conversations.create({"user_id": "u1", "title": "second"})

        titles = [doc["title"] for doc in conversations.list_for_user("u1")]
        assert titles == ["second"]
