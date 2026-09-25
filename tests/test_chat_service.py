"""Tests for chat turn orchestration (conversation, message, and memory writes)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from src.api.services.chat_service import ChatService
from src.core.memory import init_memory


class StubConversations:
    """Minimal in-memory stand-in for ``ConversationRepository``."""

    def __init__(self, conversation: dict) -> None:
        self._conversation = conversation
        self.recorded: list[tuple[str, dict, str]] = []

    def require_owned(self, conversation_id: str, user_id: str) -> dict:
        return {**self._conversation, "_id": conversation_id}

    def create(self, doc: dict) -> dict:
        self._conversation = doc
        return {**doc, "_id": "conv-1"}

    def record_turn(self, conversation_id: str, *, memory: dict, last_message: str) -> None:
        self.recorded.append((conversation_id, memory, last_message))


class StubMessages:
    """Minimal in-memory stand-in for ``MessageRepository``."""

    def __init__(self) -> None:
        self.messages: list[dict] = []

    def add(self, doc: dict) -> str:
        self.messages.append(doc)
        return f"msg-{len(self.messages)}"

    def recent_for_conversation(self, conversation_id: str, limit: int = 8) -> list[dict]:
        return self.messages[-limit:]


class StubProfiles:
    def get(self, user_id: str) -> dict | None:
        return None


class StubMemoryAgent:
    """Stands in for ``MemoryAgent`` without touching an LLM."""

    def summarise(self, existing_summary: str, transcript: str) -> str:
        return "summary"

    def extract_facts(self, transcript: str) -> list[str]:
        return ["Goal: test"]


@pytest.fixture()
def service() -> tuple[ChatService, StubConversations, StubMessages]:
    return build_service()


def build_service(**kwargs) -> tuple[ChatService, StubConversations, StubMessages]:
    conversations = StubConversations(
        {"title": "Existing", "memory": init_memory("2026-01-01T00:00:00+00:00")}
    )
    messages = StubMessages()
    return (
        ChatService(
            conversations=conversations,
            messages=messages,
            profiles=StubProfiles(),
            memory_agent=StubMemoryAgent(),
            **kwargs,
        ),
        conversations,
        messages,
    )


def test_begin_turn_stores_question_and_builds_context(service):
    chat, _, messages = service

    turn = chat.begin_turn(
        "user@test.com", question="Hello?", profile_key=None, conversation_id="conv-1"
    )

    assert turn.conversation_id == "conv-1"
    assert turn.prior_message_count == 0
    assert messages.messages[0]["role"] == "user"
    assert messages.messages[0]["content"] == "Hello?"


def test_finish_turn_always_persists_conversation(service):
    """Regression: the turn was previously persisted only on one branch."""
    chat, conversations, _ = service
    turn = chat.begin_turn(
        "user@test.com", question="Hello?", profile_key=None, conversation_id="conv-1"
    )

    message_id = chat.finish_turn(
        turn, question="Hello?", answer="Hi there, this is a long answer", citations=[]
    )

    assert message_id == "msg-2"
    assert len(conversations.recorded) == 1
    _, memory, preview = conversations.recorded[0]
    assert preview == "Hi there, this is a long answer"
    assert memory["window_tokens"] > 0
    assert len(memory["recent_turns"]) == 2


def test_window_overflow_rolls_and_summarises():
    chat, conversations, _ = build_service(memory_window_tokens=1, history_limit=10)
    turn = chat.begin_turn(
        "user@test.com", question="Hello?", profile_key=None, conversation_id="conv-1"
    )

    chat.finish_turn(turn, question="Hello?", answer="An answer", citations=[])

    _, memory, _ = conversations.recorded[0]
    assert memory["summary"] == "summary"
    assert memory["facts"] == ["Goal: test"]
    assert memory["last_refreshed_turn_count"] == 2
    assert len(memory["recent_turns"]) < 2


def test_begin_turn_creates_conversation_when_missing(service):
    chat, _, _ = service

    turn = chat.begin_turn(
        "user@test.com", question="A brand new question", profile_key="senior",
        conversation_id=None,
    )

    assert turn.conversation_id == "conv-1"
    assert turn.memory["enabled"] is True
