"""FastAPI dependency providers.

Heavy resources (RAG chain, profile generator, memory agent) are lazy
singletons; repositories are constructed per request from the shared Mongo
client, so route handlers never touch the driver directly.
"""

from functools import lru_cache

from fastapi import Depends
from pymongo.database import Database

from src.api.db.database import get_database
from src.api.db.repositories import (
    AlertRepository,
    ConsentRepository,
    ConversationRepository,
    InMemoryConversationRepository,
    InMemoryMessageRepository,
    MessageRepository,
    ProfileRepository,
    UserRepository,
)
from src.api.errors import DatabaseUnavailableError
from src.api.security import get_current_user
from src.core.config import get_settings

__all__ = [
    "get_db",
    "get_settings",
    "get_alert_repository",
    "get_consent_repository",
    "get_conversation_repository",
    "get_message_repository",
    "get_optional_alert_repository",
    "get_profile_repository",
    "get_user_repository",
    "get_rag_chain",
    "get_profile_generator",
    "get_memory_agent",
    "get_source_service",
    "get_chat_service",
    "get_user_service",
    "get_ephemeral_conversation_repository",
    "get_ephemeral_message_repository",
]


# ── Database & repositories ───────────────────────────────────────────────────


def get_db() -> Database:
    """Provide the MongoDB database, failing fast with a 503 when unavailable."""
    db = get_database()
    if db is None:
        raise DatabaseUnavailableError()
    return db


def get_user_repository(db: Database = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_profile_repository(db: Database = Depends(get_db)) -> ProfileRepository:
    return ProfileRepository(db)


def get_consent_repository(db: Database = Depends(get_db)) -> ConsentRepository:
    return ConsentRepository(db)


def get_conversation_repository(db: Database = Depends(get_db)) -> ConversationRepository:
    return ConversationRepository(db)


def get_message_repository(db: Database = Depends(get_db)) -> MessageRepository:
    return MessageRepository(db)


def get_alert_repository(db: Database = Depends(get_db)) -> AlertRepository:
    return AlertRepository(db)


def get_optional_alert_repository() -> AlertRepository | None:
    """Alerts repository that yields ``None`` when MongoDB is unavailable."""
    db = get_database()
    return AlertRepository(db) if db is not None else None


# ── Lazy singletons ───────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _build_rag_chain():
    from src.core.rag_chain import RAGChain

    return RAGChain(get_settings())


def get_rag_chain():
    """Provide the cached RAG chain, built on first use."""
    return _build_rag_chain()


@lru_cache(maxsize=1)
def _build_profile_generator():
    from src.api.services.profile_generator_service import ProfileGeneratorService

    return ProfileGeneratorService()


def get_profile_generator():
    """Provide the cached profile-generator service, built on first use."""
    return _build_profile_generator()


@lru_cache(maxsize=1)
def get_memory_agent():
    """Provide the cached conversation-memory agent."""
    from src.core.memory import MemoryAgent

    return MemoryAgent()


def get_source_service():
    """Provide a source service bound to the shared knowledge base."""
    from src.api.services.source_service import SourceService

    return SourceService()


@lru_cache(maxsize=1)
def get_ephemeral_conversation_repository() -> InMemoryConversationRepository:
    """Process-wide in-memory conversations for users who declined storage."""
    settings = get_settings()
    return InMemoryConversationRepository(
        ttl_seconds=settings.ephemeral_history_ttl_seconds,
        max_conversations=settings.ephemeral_history_max_conversations,
    )


@lru_cache(maxsize=1)
def get_ephemeral_message_repository() -> InMemoryMessageRepository:
    """Process-wide in-memory messages for users who declined storage."""
    settings = get_settings()
    return InMemoryMessageRepository(
        ttl_seconds=settings.ephemeral_history_ttl_seconds,
        max_conversations=settings.ephemeral_history_max_conversations,
    )


def get_chat_service(
    conversations: ConversationRepository = Depends(get_conversation_repository),
    messages: MessageRepository = Depends(get_message_repository),
    profiles: ProfileRepository = Depends(get_profile_repository),
    consent: ConsentRepository = Depends(get_consent_repository),
    current_user: dict = Depends(get_current_user),
):
    """Provide the chat service, backed by MongoDB or by process memory.

    A user who declined chat-history storage gets in-memory repositories, so
    nothing is written to the database and their conversations disappear when
    the session ends.
    """
    from src.api.services.chat_service import ChatService

    settings = get_settings()
    if consent.has_chat_history_consent(
        current_user.get("sub", ""),
        default=settings.chat_history_default_consent,
    ):
        conversation_store, message_store = conversations, messages
    else:
        conversation_store = get_ephemeral_conversation_repository()
        message_store = get_ephemeral_message_repository()

    return ChatService(
        conversations=conversation_store,
        messages=message_store,
        profiles=profiles,
        memory_agent=get_memory_agent(),
        memory_window_tokens=settings.memory_window_tokens,
        history_limit=settings.memory_history_fetch_limit,
    )


def get_user_service(
    users: UserRepository = Depends(get_user_repository),
    profiles: ProfileRepository = Depends(get_profile_repository),
    consent: ConsentRepository = Depends(get_consent_repository),
    conversations: ConversationRepository = Depends(get_conversation_repository),
    messages: MessageRepository = Depends(get_message_repository),
):
    """Provide the admin user service wired to the request-scoped repositories."""
    from src.api.services.user_service import UserService

    return UserService(
        users=users,
        profiles=profiles,
        consent=consent,
        conversations=conversations,
        messages=messages,
    )
