"""Conversation CRUD and per-turn memory orchestration for the chat route."""

from dataclasses import dataclass
from datetime import UTC, datetime

from src.api.db.repositories import (
    ConversationRepository,
    MessageRepository,
    ProfileRepository,
)
from src.api.errors import NotFoundError
from src.api.mappers.chat import (
    conversation_to_list_item,
    conversation_to_response,
    message_to_response,
)
from src.core.memory import (
    DEFAULT_WINDOW_TOKENS,
    MemoryAgent,
    build_memory_context,
    init_memory,
    roll_window,
    update_memory_window,
)

TITLE_FROM_QUESTION_LENGTH = 80
LAST_MESSAGE_PREVIEW_LENGTH = 100
DEFAULT_HISTORY_LIMIT = 60


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ChatTurn:
    """State captured before invoking the RAG chain for one exchange."""

    conversation_id: str
    memory: dict
    memory_context: str
    prior_message_count: int


class ChatService:
    """Owns conversation lifecycle, message persistence, and memory refresh."""

    def __init__(
        self,
        *,
        conversations: ConversationRepository,
        messages: MessageRepository,
        profiles: ProfileRepository,
        memory_agent: MemoryAgent,
        memory_window_tokens: int = DEFAULT_WINDOW_TOKENS,
        history_limit: int = DEFAULT_HISTORY_LIMIT,
    ) -> None:
        self._conversations = conversations
        self._messages = messages
        self._profiles = profiles
        self._memory_agent = memory_agent
        self._memory_window_tokens = memory_window_tokens
        self._history_limit = history_limit

    # ── Conversations ─────────────────────────────────────────────────────────

    def list_conversations(self, user_id: str, page: int = 1, limit: int = 20) -> dict:
        return {
            "conversations": [
                conversation_to_list_item(doc)
                for doc in self._conversations.list_for_user(user_id, page, limit)
            ],
            "total": self._conversations.count_for_user(user_id),
            "page": page,
            "limit": limit,
        }

    def create_conversation(self, user_id: str, title: str | None, profile_key: str | None) -> dict:
        now = _now()
        doc = {
            "user_id": user_id,
            "title": title or "New conversation",
            "profile_key": profile_key,
            "message_count": 0,
            "last_message": None,
            "last_message_at": None,
            "created_at": now,
            "updated_at": now,
        }
        return conversation_to_response(self._conversations.create(doc))

    def get_conversation(self, user_id: str, conversation_id: str) -> dict:
        conversation = self._conversations.require_owned(conversation_id, user_id)
        messages = self._messages.list_for_conversation(conversation_id)
        return conversation_to_response(conversation, messages)

    def rename_conversation(self, user_id: str, conversation_id: str, title: str) -> dict:
        return conversation_to_response(self._conversations.rename(conversation_id, user_id, title))

    def delete_conversation(self, user_id: str, conversation_id: str) -> None:
        if not self._conversations.delete(conversation_id, user_id):
            raise NotFoundError("Conversation not found")
        self._messages.delete_for_conversation(conversation_id)

    def list_messages(
        self, user_id: str, conversation_id: str, page: int = 1, limit: int = 50
    ) -> list[dict]:
        self._conversations.require_owned(conversation_id, user_id)
        return [
            message_to_response(doc)
            for doc in self._messages.list_for_conversation(conversation_id, page, limit)
        ]

    def profile_doc(self, user_id: str) -> dict | None:
        return self._profiles.get(user_id)

    # ── Turn lifecycle ────────────────────────────────────────────────────────

    def begin_turn(
        self,
        user_id: str,
        *,
        question: str,
        profile_key: str | None,
        conversation_id: str | None,
    ) -> ChatTurn:
        """Resolve the conversation, persist the question, and build memory context."""
        now = _now()
        if conversation_id:
            conversation = self._conversations.require_owned(conversation_id, user_id)
        else:
            conversation = self._conversations.create(
                self._new_conversation_doc(user_id, question, profile_key, now)
            )

        resolved_id = str(conversation["_id"])
        self._messages.add(
            {
                "conversation_id": resolved_id,
                "role": "user",
                "content": question,
                "citations": [],
                "is_streaming": False,
                "created_at": now,
            }
        )

        memory = conversation.get("memory") or init_memory(now)
        # Render the current token window for the prompt. Overflow is folded
        # into the summary at the end of the turn, once the answer exists.
        window, _, _ = roll_window(
            self._messages.recent_for_conversation(resolved_id, self._history_limit),
            self._memory_window_tokens,
        )
        return ChatTurn(
            conversation_id=resolved_id,
            memory=memory,
            memory_context=build_memory_context(memory, window),
            # Read from the conversation document (indexed by _id) rather than
            # counting messages, which would scan an unindexed collection.
            prior_message_count=conversation.get("message_count", 0),
        )

    def finish_turn(
        self,
        turn: ChatTurn,
        *,
        question: str,
        answer: str,
        citations: list[dict],
    ) -> str:
        """Persist the answer, roll the memory window, and return the message id."""
        message_id = self._messages.add(
            {
                "conversation_id": turn.conversation_id,
                "role": "assistant",
                "content": answer,
                "citations": citations,
                "is_streaming": False,
                "created_at": _now(),
            }
        )

        # +2 for the question and answer of this turn, which are not yet counted.
        total_turns = turn.prior_message_count + 2
        memory, _ = update_memory_window(
            self._messages.recent_for_conversation(turn.conversation_id, self._history_limit),
            turn.memory,
            agent=self._memory_agent,
            now=_now(),
            total_turn_count=total_turns,
            max_tokens=self._memory_window_tokens,
        )

        self._conversations.record_turn(
            turn.conversation_id,
            memory=memory,
            last_message=answer[:LAST_MESSAGE_PREVIEW_LENGTH],
        )
        return message_id

    @staticmethod
    def _new_conversation_doc(
        user_id: str, question: str, profile_key: str | None, now: str
    ) -> dict:
        title = question[:TITLE_FROM_QUESTION_LENGTH]
        if len(question) > TITLE_FROM_QUESTION_LENGTH:
            title += "..."
        return {
            "user_id": user_id,
            "title": title,
            "profile_key": profile_key,
            "message_count": 0,
            "last_message": None,
            "last_message_at": None,
            "created_at": now,
            "updated_at": now,
            "memory": init_memory(now),
        }
