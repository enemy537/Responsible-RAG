"""MongoDB repositories — one per collection, plus in-memory variants."""

from src.api.db.repositories.alerts import AlertRepository
from src.api.db.repositories.base import MongoRepository, to_object_id
from src.api.db.repositories.consent import ConsentRepository
from src.api.db.repositories.conversations import (
    ConversationRepository,
    MessageRepository,
)
from src.api.db.repositories.memory_repositories import (
    InMemoryConversationRepository,
    InMemoryMessageRepository,
)
from src.api.db.repositories.profiles import ProfileRepository
from src.api.db.repositories.users import UserRepository

__all__ = [
    "AlertRepository",
    "ConsentRepository",
    "ConversationRepository",
    "InMemoryConversationRepository",
    "InMemoryMessageRepository",
    "MessageRepository",
    "MongoRepository",
    "ProfileRepository",
    "UserRepository",
    "to_object_id",
]
